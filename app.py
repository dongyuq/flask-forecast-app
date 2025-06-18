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

    # ✅ 缓存逻辑（不动你的展示结构）
    with lock:
        if days in forecast_cache:
            print(f"✅ 从内存缓存读取 {days} 天预测结果")
            df = forecast_cache[days]
        else:
            print(f"⏳ 正在计算 {days} 天预测结果")
            df = predict_inventory(days=days)
            forecast_cache[days] = df

    # ✅ 替换列名展示更友好
    df.columns = ['Date', 'container', 'lower bound', 'upper bound', 'Sales Prediction', 'Cost Prediction']

    # ✅ 渲染表格 HTML
    table_html = df.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center',
        border=0
    )
    table_html = table_html.replace('<thead>',
        '<thead style="position: sticky; top: 0; background-color: #fff; z-index: 1;">')

    # ✅ 返回 JSON 格式（不改原结构）
    return jsonify({
        'table_html': table_html,
        'interactive_html': 'static/interactive_forecast.html'
    })


if __name__ == '__main__':
    import os

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)