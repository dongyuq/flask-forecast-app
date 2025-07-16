# daily_refresh.py
from train_scriptl import retrain_models
from predict_script import predict_inventory

def run_daily_refresh(warehouse):
    print(f"⏰ 开始每日模型训练与图表更新：{warehouse}")
    retrain_models(warehouse)
    for days in [30, 60, 90]:
        print(f"📊 生成 {warehouse} 仓库的 {days} 天预测图表")
        predict_inventory(warehouse=warehouse, days=days, force=True)
    print(f"✅ 每日任务完成：{warehouse}")

from db_utils import query_to_dataframe
import pandas as pd
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_apo_data(warehouse='NJ'):
    sql_path = os.path.join(BASE_DIR, 'sql', f'daily_apo_{warehouse.lower()}.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    df = query_to_dataframe(sql)
    df['Date'] = pd.to_datetime(df['Date'])

    full_dates = pd.date_range(start=df['Date'].min(), end=df['Date'].max())
    df = df.set_index('Date').reindex(full_dates).fillna(0).rename_axis('Date').reset_index()
    df.columns = ['Date', 'APO']
    df['APO'] = df['APO'].astype(int)
    return df



def generate_sales_data(warehouse='NJ'):
    sql_path = os.path.join(BASE_DIR, 'sql', f'daily_cuft_sales_cost_{warehouse.lower()}.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    df = query_to_dataframe(sql)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')
    df['Month'] = df['Invoice Date'].dt.to_period('M').astype(str)

    # 月度聚合
    df_group = df.groupby('Month').agg({
        'Sales': 'sum',
        'Cost': 'sum',
        'Total Cuft': 'sum'
    }).reset_index()

    # ➕ 添加 Containers 列 = Total Cuft / 2350，保留一位小数
    df_group['Containers'] = (df_group['Total Cuft'] / 2350).round(1)

    # 👉 把 Containers 插入到 Total Cuft 之后
    cuft_index = df_group.columns.get_loc('Total Cuft')
    containers_col = df_group.pop('Containers')
    df_group.insert(cuft_index + 1, 'Containers', containers_col)

    # ➕ 添加 Margin 列
    df_group['Margin'] = ((df_group['Sales'] - df_group['Cost']) / df_group['Sales']).round(4) * 100
    df_group['Margin'] = df_group['Margin'].map(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")

    # 👉 把 Margin 列插入到 Cost 之后
    cost_index = df_group.columns.get_loc('Cost')
    margin_col = df_group.pop('Margin')
    df_group.insert(cost_index + 1, 'Margin %', margin_col)

    # 排序
    df_group['Month_dt'] = pd.to_datetime(df_group['Month'], format='%Y-%m')
    df_group = df_group.sort_values('Month_dt')

    # 添加 MoM 和 YoY（Sales）
    df_group['MoM Sales %'] = df_group['Sales'].pct_change().round(4) * 100
    df_group['YoY Sales %'] = df_group['Sales'].pct_change(periods=12).round(4) * 100

    # 添加 MoM 和 YoY（Cost）
    df_group['MoM Cost %'] = df_group['Cost'].pct_change().round(4) * 100
    df_group['YoY Cost %'] = df_group['Cost'].pct_change(periods=12).round(4) * 100

    # 添加 MoM 和 YoY（Total Cuft）
    df_group['MoM Cuft %'] = df_group['Total Cuft'].pct_change().round(4) * 100
    df_group['YoY Cuft %'] = df_group['Total Cuft'].pct_change(periods=12).round(4) * 100

    # 格式化百分比
    percent_cols = ['MoM Sales %', 'YoY Sales %', 'MoM Cost %', 'YoY Cost %', 'MoM Cuft %', 'YoY Cuft %']
    for col in percent_cols:
        df_group[col] = df_group[col].map(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")

    # 删除辅助列
    df_group.drop(columns=['Month_dt'], inplace=True)

    return df_group




