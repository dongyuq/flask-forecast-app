from flask import Flask, render_template, send_file
import pandas as pd
from flask import request


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

from flask import jsonify


# /predict 路由（仅展示更新部分）
@app.route('/predict')
def predict():
    from flask import request, jsonify
    from predict_script import predict_inventory
    days = int(request.args.get('days', 30))
    df = predict_inventory(days=days)

    # ✅ 替换 DataFrame 的列名，去掉下划线
    df.columns = ['Date', 'container', 'lower bound', 'upper bound', 'Sales Prediction', 'Cost Prediction']

    # ✅ to_html: 添加 thead (固定表头在前端可滚动) + classes
    table_html = df.to_html(
        index=False,
        classes='table table-bordered table-hover table-sm text-center',
        justify='center',
        border=0
    )
    table_html = table_html.replace('<thead>',
                                    '<thead style="position: sticky; top: 0; background-color: #fff; z-index: 1;">')

    # 返回包含交互式图表链接（或者 prediction.html 链接）等信息
    return jsonify({
        'table_html': table_html,
        'interactive_html': 'static/interactive_forecast.html'
    })


if __name__ == '__main__':
    app.run(debug=True)

