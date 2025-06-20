import pandas as pd
import os
from flask import Flask, render_template, send_file
from flask import Flask, request, jsonify
from predict_script import predict_inventory
import threading

from train_model import data_dir

app = Flask(__name__)

# 🔒 用线程锁防止并发访问时冲突
forecast_cache = {}
apo_cache = None
sales_cache = None
lock = threading.Lock()

@app.route('/')
def index():
    return render_template('index.html')

from flask import jsonify


# /predict 路由（仅展示更新部分）
@app.route('/predict')
def predict():
    days = int(request.args.get('days', 30))

    # ✅ 缓存预测结果
    with lock:
        if days in forecast_cache:
            print(f"✅ 从内存缓存读取 {days} 天预测结果")
            df = forecast_cache[days]
        else:
            print(f"⏳ 正在计算 {days} 天预测结果")
            df = predict_inventory(days=days)
            forecast_cache[days] = df

    df.columns = ['Date', 'container', 'lower bound', 'upper bound', 'Sales Prediction', 'Cost Prediction']

    table_html = df.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center',
        border=0
    )
    table_html = table_html.replace('<thead>',
        '<thead style="position: sticky; top: 0; background-color: #fff; z-index: 1;">')

    # ✅ 关键修改：返回正确图表路径（前端其实用不上这个字段也没事）
    return jsonify({
        'table_html': table_html,
        'interactive_html': f'static/forecast/container_forecast_{days}.html'
    })

from flask import send_file
import io

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
        download_name=f'forecast_{days}_days.xlsx'
    )

@app.route('/apo')
def apo():
    global apo_cache

    with lock:
        if apo_cache is None:
            print("⏳ 正在加载 APO 数据")
            apo_path = os.path.join(data_dir, 'APO.csv')
            apo_df = pd.read_csv(apo_path, parse_dates=['Date'])
            apo_df.sort_values('Date', inplace=True)
            apo_cache = apo_df
        else:
            print("✅ 从内存读取 APO 数据")
            apo_df = apo_cache

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


DATA_DIR = os.path.join(os.path.dirname(__file__), 'Data')
SALES_PATH = os.path.join(DATA_DIR, 'ModelRevenueDetails_test.csv')

@app.route('/sales')
def sales():
    global sales_cache

    with lock:
        if sales_cache is None:
            print("⏳ 正在加载 Sales 数据")
            df = pd.read_csv(SALES_PATH, parse_dates=['Invoice Date'])
            df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
            df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
            df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')

            df['Month'] = df['Invoice Date'].dt.to_period('M').astype(str)
            df_group = df.groupby('Month').agg({
                'Sales': 'sum',
                'Cost': 'sum',
                'Total Cuft': 'sum'
            }).reset_index()

            sales_cache = df_group
        else:
            print("✅ 从内存读取 Sales 数据")
            df_group = sales_cache

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




if __name__ == '__main__':
    import os

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
