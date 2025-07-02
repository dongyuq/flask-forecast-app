# daily_refresh.py
from train_scriptl import retrain_models
from predict_script import predict_inventory

def run_daily_refresh():
    print("⏰ 开始每日模型训练与图表更新")
    retrain_models()
    for days in [30, 60, 90]:
        print(f"📊 生成 {days} 天预测图表")
        predict_inventory(days=days, force=True)
    print("✅ 每日任务完成")
# daily_refresh.py

from db_utils import query_to_dataframe
import pandas as pd
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_apo_data():
    sql_path = os.path.join(BASE_DIR, 'sql', 'daily_apo.sql')
    with open(sql_path, 'r',encoding='utf-8') as f:
        sql = f.read()

    df = query_to_dataframe(sql)
    df['Date'] = pd.to_datetime(df['Date'])

    full_dates = pd.date_range(start=df['Date'].min(), end=df['Date'].max())
    df = df.set_index('Date').reindex(full_dates).fillna(0).rename_axis('Date').reset_index()
    df.columns = ['Date', 'APO']
    df['APO'] = df['APO'].astype(int)
    return df


def generate_sales_data():
    sql_path = os.path.join(BASE_DIR, 'sql', 'daily_cuft_sales_cost.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    df = query_to_dataframe(sql)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')
    df['Month'] = df['Invoice Date'].dt.to_period('M').astype(str)
    df_group = df.groupby('Month').agg({
        'Sales': 'sum',
        'Cost': 'sum',
        'Total Cuft': 'sum'
    }).reset_index()
    return df_group
