import time
from flask import Flask, render_template, jsonify,request,send_file
from predict_script import predict_inventory
import threading
from gauge_plot import get_current_container, plot_half_gauge
from daily_refresh import run_daily_refresh, generate_apo_data, generate_sales_data
import datetime
import io

app = Flask(__name__)

# 🔒 用线程锁防止并发访问时冲突
forecast_cache = {}
apo_cache = None
sales_cache = None
lock = threading.Lock()

def get_last_update_time():
    path = "last_run.txt"
    if os.path.exists(path):
        with open(path, 'r') as f:
            return f.read().strip()
    return "未更新"


@app.route('/')
def index():
    timestamp = int(time.time())
    last_update = get_last_update_time()
    return render_template('index.html', timestamp=timestamp, last_update=last_update)




# /predict 路由（仅展示更新部分）
from bs4 import BeautifulSoup  # 确保安装：pip install beautifulsoup4
@app.route('/predict')
def predict():
    days = int(request.args.get('days', 30))

    with lock:
        if days in forecast_cache:
            print(f"✅ 从内存缓存读取 {days} 天预测结果")
            df = forecast_cache[days]
        else:
            print(f"⏳ 正在计算 {days} 天预测结果")
            df = predict_inventory(days=days)
            forecast_cache[days] = df

    # 添加列名
    df.columns = ['Date', 'container', 'lower bound', 'upper bound', 'Sales Prediction', 'Cost Prediction']

    # ✅ 渲染表格
    table_html = df.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center',
        border=0
    )
    table_html = table_html.replace(
        '<thead>',
        '<thead style="position: sticky; top: 0; background-color: #fff; z-index: 1;">'
    )

    # ✅ 日志调试
    print("🔁 返回 HTML 表格预览：", table_html[:100])

    return jsonify({
        'table_html': table_html
    })


@app.route('/download')
def download():
    import io
    from flask import send_file
    import pandas as pd

    days = int(request.args.get('days', 30))
    df = forecast_cache.get(days)

    if df is None:
        from predict_script import predict_inventory
        df = predict_inventory(days)
        forecast_cache[days] = df

    df.columns = ['Date', 'container', 'lower bound', 'upper bound', 'Sales Prediction', 'Cost Prediction']

    # 写入内存中的 Excel 文件
    output = io.BytesIO()
    with pd.ExcelWriter(output) as writer:
        df.to_excel(writer, index=False, sheet_name='Forecast')

    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'forecast_{days}_days_NJ.xlsx'
    )


@app.route('/apo')
def apo():
    global apo_cache
    with lock:
        if apo_cache is None:
            print("⚠️ APO 内存无缓存，改为读取 SQL 数据")
            from daily_refresh import generate_apo_data
            apo_cache = generate_apo_data()
            apo_df = apo_cache  # ✅ 放进 if 里面
        else:
            print("✅ 从内存读取 APO 数据")
            apo_df = apo_cache  # ✅ 放进 else 里面

    # 渲染页面
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
    with lock:
        if sales_cache is None:
            print("⚠️ Sales 内存无缓存，改为读取 SQL 数据")
            from daily_refresh import generate_sales_data
            sales_cache = generate_sales_data()
            df_group = sales_cache  # ✅ 写进 if
        else:
            print("✅ 从内存读取 Sales 数据")
            df_group = sales_cache  # ✅ 写进 else

    # 前端展示
    months = df_group['Month'].tolist()
    sales_values = df_group['Sales'].astype(float).round(0).tolist()
    cost_values = df_group['Cost'].astype(float).round(0).tolist()
    cuft_values = df_group['Total Cuft'].astype(float).round(0).tolist()

    table_html = df_group.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center'
    )

    return render_template(
        'sales.html',
        months=months,
        sales_values=sales_values,
        cost_values=cost_values,
        cuft_values=cuft_values,
        table_html=table_html,
        zip=zip
    )




@app.route('/static/gauge.png')
def dynamic_gauge():
    container = get_current_container()
    min_val = 0
    max_val = 220
    title = 'Inventory Level (Containers)'

    # ✅ 用内存 buffer，而不是保存为文件
    buf = io.BytesIO()
    plot_half_gauge(container, min_val, max_val, title, buf)
    buf.seek(0)

    return send_file(buf, mimetype='image/png')

# app.py 中添加



def has_run_today():
    path = "last_run.txt"
    if os.path.exists(path):
        with open(path, 'r') as f:
            last_run = f.read().strip()
        last_date = last_run.split(' ')[0]
        return last_date == datetime.datetime.now().strftime("%Y-%m-%d")
    return False

def mark_run_today():
    with open("last_run.txt", 'w') as f:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        f.write(now_str)

def run_daily_refresh_with_data():
    global apo_cache, sales_cache
    run_daily_refresh()
    apo_cache = generate_apo_data()
    sales_cache = generate_sales_data()

@app.route('/daily-refresh')
def daily_refresh():
    now = datetime.datetime.now()
    force = request.args.get('force') == '1'

    if (3 <= now.hour < 4 and not has_run_today()) or force:
        run_daily_refresh_with_data()
        mark_run_today()
        return '✅ 已训练（强制运行）' if force else '✅ 已训练'
    else:
        return '✅ 今天已训练过 或 尚未到时间'

if __name__ == '__main__':
    import os

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
