from flask import Flask, render_template, send_file
import pandas as pd
from flask import request


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

from flask import jsonify

@app.route('/predict')
def predict():
    from flask import request, jsonify
    from predict_script import predict_inventory
    days = int(request.args.get('days', 30))
    df = predict_inventory(days=days)
    df = df[['Date', 'container', 'lower_bound', 'upper_bound']]
    table_html = df.to_html(index=False, classes='table table-bordered table-hover', justify='center')
    return jsonify({
        'table_html': table_html,
        'image': 'static/prediction.png'
    })



if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

