import time
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, jsonify,request,send_file, abort
from predict_script import predict_inventory
import threading
from gauge_plot import get_current_container, plot_half_gauge
from daily_refresh import run_daily_refresh, generate_apo_data, generate_sales_data
from datetime import datetime
from zoneinfo import ZoneInfo
import io
import os

app = Flask(__name__)

# 🔒 用线程锁防止并发访问时冲突
forecast_cache = {}
apo_cache = {}
sales_cache = {}
lock = threading.Lock()

# 设置允许的 IP 白名单（你公司公网 IP）
# 设置允许的 IP 白名单（包括你公司公网 IP + UptimeRobot IP）
ALLOWED_IPS = {
    '127.0.0.1',
    '207.140.24.82',  # 你公司 IP
    '71.24.118.105',  # 你自己用的
    # ✅ UptimeRobot IPs（IPv4 版，建议全部添加）
    '69.162.124.224',
    '69.162.124.225',
    '69.162.124.226',
    '69.162.124.227',
    '69.162.124.228',
    '69.162.124.229',
    '69.162.124.230',
    '69.162.124.231',
    '208.115.199.74',
    '208.115.199.75',
    '208.115.199.76',
    '208.115.199.77',
    '208.115.199.78',
}

IS_PRODUCTION = os.environ.get("ENV") == "production"


@app.before_request
def limit_remote_addr():
    if request.path == "/ping":  # 放行 ping 路径
        return



    # 更安全地获取真实用户 IP（优先使用 Flask 提供的 access_route）
    ip = request.access_route[0] if request.access_route else request.remote_addr

    app.logger.info(f"📡 Real incoming IP: {ip}")

    if ip not in ALLOWED_IPS:
        app.logger.warning(f"Blocked IP: {ip}")
        abort(403)




@app.route("/ping")
def ping():
    return "pong", 200


def get_last_update_time(warehouse='NJ'):
    path = f"last_run_{warehouse.upper()}.txt"
    if os.path.exists(path):
        with open(path, 'r') as f:
            raw_time = f.read().strip()
            try:
                naive_dt = datetime.strptime(raw_time, '%Y-%m-%d %H:%M')
                local_dt = naive_dt.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
                return local_dt.strftime('%Y-%m-%d %H:%M %Z')  # 返回例如：2025-07-03 23:00 PDT
            except Exception:
                return raw_time
    return "未更新"



@app.route('/')
def index():
    global sales_cache
    timestamp = int(time.time())
    last_update = get_last_update_time()

    warehouse = request.args.get('warehouse', 'NJ')

    with lock:
        if sales_cache is None:
            sales_cache = {}

        if warehouse not in sales_cache:
            print(f"⚠️ Sales 缓存缺失，加载 {warehouse}")
            df_group = generate_sales_data(warehouse=warehouse)
            sales_cache[warehouse] = df_group
        else:
            print(f"✅ 从缓存读取 Sales - {warehouse}")
            df_group = sales_cache[warehouse]

    months = df_group['Month'].tolist()
    sales_values = df_group['Sales'].astype(float).round(0).tolist()
    cost_values = df_group['Cost'].astype(float).round(0).tolist()
    cuft_values = df_group['Total Cuft'].astype(float).round(0).tolist()

    return render_template(
        'index.html',
        timestamp=timestamp,
        last_update=last_update,
        months=months,
        sales_values=sales_values,
        cost_values=cost_values,
        cuft_values=cuft_values,
        zip=zip
    )



from bs4 import BeautifulSoup
@app.route('/predict')
def predict():
    days = int(request.args.get('days', 30))
    warehouse = request.args.get('warehouse', 'NJ')

    with lock:
        cache_key = (days, warehouse)
        if cache_key in forecast_cache:
            print(f"✅ 从缓存读取 {days} 天预测 - 仓库：{warehouse}")
            result = forecast_cache[cache_key]
        else:
            print(f"⏳ 正在计算 {days} 天预测 - 仓库：{warehouse}")
            result = predict_inventory(days=days, warehouse=warehouse)
            forecast_cache[cache_key] = result

    df = result['forecast_df']
    monthly = result['monthly_summary']
    df['Date'] = df['Date'].astype(str).str[:10]  # 只保留年月日

    # ✅ 先重命名
    df = df.rename(columns={
        'container': 'Containers',
        'lower_bound': 'Lower bound',
        'upper_bound': 'Upper bound',
        'Sales Prediction': 'Sales Forecast',
        'Cost Prediction': 'Cost Forecast',
        'Total Cuft Prediction': 'Cuft Forecast',
        'Containers Forecast': 'Containers Forecast'
    })

    # 只保留展示列
    df = df[['Date', 'Containers', 'Lower bound', 'Upper bound',
             'Sales Forecast', 'Cost Forecast', 'Cuft Forecast', 'Containers Forecast']]

    # 排除 Total 后求和
    df_no_total = df[df['Date'] != 'Total']

    # 生成一行 Total 行
    total_row = {
        'Date': 'Total',
        'Containers': round(df_no_total['Containers'].sum(), 2),
        'Lower bound': '',
        'Upper bound': '',
        'Sales Forecast': f"${int(df_no_total['Sales Forecast'].sum()):,}",
        'Cost Forecast': f"${int(df_no_total['Cost Forecast'].sum()):,}",
        'Cuft Forecast': round(df_no_total['Cuft Forecast'].sum(), 2),
        'Containers Forecast': round(df_no_total['Containers Forecast'].sum(), 2)
    }

    # 只加一次 total
    df = pd.concat([df_no_total, pd.DataFrame([total_row])], ignore_index=True)

    # ✅ 输出HTML
    table_html = df.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        table_id='salesTable',
        justify='center',
        border=0
    )
    table_html = table_html.replace(
        '<thead>',
        '<thead style="position: sticky; top: 0; background-color: #fff; z-index: 1;">'
    )

    return jsonify({
        'table_html': table_html,
        'monthly_summary': monthly
    })



@app.route('/download')
def download():
    days = int(request.args.get('days', 30))
    warehouse = request.args.get('warehouse', 'NJ')
    cache_key = (days, warehouse)

    result = forecast_cache.get(cache_key)
    if result is None:
        result = predict_inventory(days=days, warehouse=warehouse)
        forecast_cache[cache_key] = result

    df = result['forecast_df']  # ✅ 从字典中取出 DataFrame

    df = df[['Date', 'container', 'lower_bound', 'upper_bound', 'Sales Prediction', 'Cost Prediction',
             'Total Cuft Prediction', 'Containers Forecast']]
    df.columns = ['Date', 'Containers', 'Lower bound', 'Upper bound', 'Sales Forecast', 'Cost Forecast',
                  'Cuft Forecast', 'Containers Forecast']

    output = io.BytesIO()
    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, index=False, sheet_name='Forecast')
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'forecast_{days}_days_{warehouse}.xlsx'
    )



@app.route('/apo')
def apo():
    global apo_cache
    warehouse = request.args.get('warehouse', 'NJ')

    with lock:
        if apo_cache is None:
            apo_cache = {}

        if warehouse not in apo_cache:
            print(f"⚠️ APO 缓存缺失，加载 {warehouse}")
            apo_df = generate_apo_data(warehouse=warehouse)
            apo_cache[warehouse] = apo_df
        else:
            print(f"✅ 从缓存读取 APO - {warehouse}")
            apo_df = apo_cache[warehouse]

    dates = apo_df['Date'].dt.strftime('%Y-%m-%d').tolist()
    values = apo_df['APO'].tolist()

    table_html = apo_df.to_html(
        index=False,
        classes='table table-bordered table-hover table-striped',
        justify='center'
    )

    return render_template(
        'apo.html',
        table_html=table_html,
        dates=dates,
        values=values
    )


@app.route('/sales')
def sales():
    global sales_cache
    warehouse = request.args.get('warehouse', 'NJ')

    last_update = get_last_update_time(warehouse)

    with lock:
        if sales_cache is None:
            sales_cache = {}

        if warehouse not in sales_cache:
            print(f"⚠️ Sales 缓存缺失，加载 {warehouse}")
            df_group = generate_sales_data(warehouse=warehouse)
            sales_cache[warehouse] = df_group
        else:
            print(f"✅ 从缓存读取 Sales - {warehouse}")
            df_group = sales_cache[warehouse]
    # 🔹 提取最后一行的 Sales / Cost / Margin %
    last_row = df_group.iloc[-1]
    monthly_sales = float(last_row['Sales'])
    monthly_cost = float(last_row['Cost'])
    monthly_cuft = float(last_row['Total Cuft'])
    monthly_containers = round(last_row['Total Cuft']/2350,2)

    # 处理 Margin % 字段：去掉 % 并转 float
    margin_raw = last_row['Margin %']
    if isinstance(margin_raw, str) and margin_raw.endswith('%'):
        monthly_margin = float(margin_raw.strip('%'))
    else:
        monthly_margin = float(margin_raw)
    # 提取月份名称
    month_str = last_row['Month']  # e.g., '2025-07'
    month_name = datetime.strptime(month_str, '%Y-%m').strftime('%B')  # 'July'

    if df_group is None or df_group.empty:
        return render_template(
            'sales.html',
            months=[],
            sales_values=[],
            cost_values=[],
            cuft_values=[],
            table_html='',
            zip=zip
        )

    months = df_group['Month'].tolist()
    sales_values = df_group['Sales'].astype(float).round(0).tolist()
    cost_values = df_group['Cost'].astype(float).round(0).tolist()
    cuft_values = df_group['Total Cuft'].astype(float).round(0).tolist()
    container_values = (df_group['Total Cuft'].astype(float) / 2350).round(2).tolist()

    table_html = df_group.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center',
        table_id='salesTable'  #可排序
    )

    return render_template(
        'sales.html',
        months=months,
        sales_values=sales_values,
        cost_values=cost_values,
        cuft_values=cuft_values,
        table_html=table_html,
        zip=zip,
        monthly_sales=monthly_sales,
        monthly_cost=monthly_cost,
        monthly_margin=monthly_margin,
        month_name=month_name,
        monthly_cuft=monthly_cuft,
        monthly_containers = monthly_containers,
        last_update  = last_update,
        container_values=container_values,

    )


@app.route('/static/gauge.png')
def dynamic_gauge():
    warehouse = request.args.get('warehouse', 'NJ').upper()
    container = get_current_container(warehouse)  # ✅ 加入仓库判断

    min_val = 0
    max_val = 220
    title = 'Current Inventory Level (Containers)'

    # ✅ 用内存 buffer，而不是保存为文件
    buf = io.BytesIO()
    plot_half_gauge(container, min_val, max_val, title, buf)
    buf.seek(0)

    return send_file(buf, mimetype='image/png')

def has_run_today(warehouse='NJ'):
    path = f"last_run_{warehouse.upper()}.txt"
    if os.path.exists(path):
        with open(path, 'r') as f:
            last_run = f.read().strip()
        last_date = last_run.split(' ')[0]
        return last_date == datetime.datetime.now().strftime("%Y-%m-%d")
    return False

def mark_run_today(warehouse='NJ'):
    from zoneinfo import ZoneInfo
    path = f"last_run_{warehouse.upper()}.txt"
    now_str = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M")
    with open(path, 'w') as f:
        f.write(now_str)

def run_daily_refresh_with_data(warehouse='NJ'):
    global apo_cache, sales_cache

    if apo_cache is None:
        apo_cache = {}
    if sales_cache is None:
        sales_cache = {}

    run_daily_refresh(warehouse)

    apo_cache[warehouse] = generate_apo_data(warehouse)
    sales_cache[warehouse] = generate_sales_data(warehouse)

def refresh_data_only(warehouse='NJ'):
    global apo_cache, sales_cache

    if apo_cache is None:
        apo_cache = {}
    if sales_cache is None:
        sales_cache = {}

    apo_cache[warehouse] = generate_apo_data(warehouse)
    sales_cache[warehouse] = generate_sales_data(warehouse)

@app.route('/daily-refresh')
def daily_refresh():
    from train_scriptl import retrain_models
    now = datetime.now(ZoneInfo('America/Los_Angeles'))
    force = request.args.get('force') == '1'
    retrain = request.args.get('train') == '1'
    warehouse = request.args.get('warehouse', 'NJ').upper()

    should_run = (3 <= now.hour < 4 and not has_run_today(warehouse)) or force
    if not should_run:
        return jsonify({
            'message': f'✅ Already refreshed today or not scheduled time (Warehouse: {warehouse}, force={force})',
            'last_update': now.strftime('%Y-%m-%d %H:%M')
        })

    if retrain:
        print(f"🚀 Training model: warehouse={warehouse}")
        retrain_models(warehouse)

    print(f"📊 Refreshing data only for warehouse={warehouse}")
    refresh_data_only(warehouse)

    # ✅ 统一预测 90 天，只缓存一份
    print(f"🔁 Predicting 90-day forecast for {warehouse}")
    with lock:
        # 删除所有旧缓存（30、60、90）
        keys_to_remove = [k for k in forecast_cache if k[1] == warehouse]
        for k in keys_to_remove:
            del forecast_cache[k]

        result = predict_inventory(days=90, force=True, warehouse=warehouse)
        forecast_cache[(90, warehouse)] = result

    # ✅ 更新 gauge 图
    container = get_current_container(warehouse)
    plot_half_gauge(container, 0, 220, 'Inventory Level (Containers)', f'static/gauge_{warehouse}.png')
    mark_run_today(warehouse)

    return jsonify({
        'message': f'✅ {"Trained and Predicted" if retrain else "Predicted (no retrain)"} (Warehouse: {warehouse})',
        'last_update': now.strftime('%Y-%m-%d %H:%M')
    })





def run_scheduled_refresh():
    with app.app_context():
        now = datetime.now(ZoneInfo('America/Los_Angeles'))
        warehouse = 'NJ'
        print(f"⏰ 定时刷新启动 at {now} for {warehouse}")

        try:
            # ✅ 刷新 sales + APO 数据
            refresh_data_only(warehouse)

            # ✅ 清除旧缓存
            forecast_cache.pop((30, warehouse), None)

            # ✅ 重新预测
            predict_inventory(days=30, force=True, warehouse=warehouse)

            # ✅ 更新图表
            container = get_current_container(warehouse)
            plot_half_gauge(container, 0, 220, 'Inventory Level (Containers)', f'static/gauge_{warehouse}.png')

            # ✅ 标记今天已刷新
            mark_run_today(warehouse)

            print("✅ 定时刷新成功（未重新训练）")
        except Exception as e:
            print(f"❌ 定时刷新失败: {e}")


if __name__ == '__main__':
    import os

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_refresh, 'cron', hour=3, minute=0, timezone='America/Los_Angeles')
    scheduler.start()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
