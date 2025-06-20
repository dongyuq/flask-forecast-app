from flask import Flask, render_template, send_file
from flask import Flask, request, jsonify
from predict_script import predict_inventory
import threading


app = Flask(__name__)

# 🔒 用线程锁防止并发访问时冲突
forecast_cache = {}
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
        'interactive_html': f'static/container_forecast_{days}.html'
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
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Forecast')

    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'forecast_{days}_days.xlsx'
    )



if __name__ == '__main__':
    import os

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
