# train_model.py
import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import pickle
from db_utils import query_to_dataframe

base_dir = os.path.dirname(os.path.abspath(__file__))

def load_sql(file_name):
    sql_path = os.path.join(base_dir, 'sql', file_name)
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()

def retrain_models():
    sql = load_sql('daily_cuft_sales_cost.sql')
    df = query_to_dataframe(sql)

    # 强制转类型（避免脏数据）
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

    # 日维度聚合
    daily_df = df.groupby('Invoice Date').agg({
        'Total Cuft': 'sum',
        'Sales': 'sum',
        'Cost': 'sum'
    }).reset_index()

    # 特征工程
    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
    daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
    daily_df['day'] = daily_df['Invoice Date'].dt.day
    daily_df['month'] = daily_df['Invoice Date'].dt.month
    daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
    daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
    daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)

    X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]

    # 模型训练：Cuft
    y_cuft = daily_df['Total Cuft']
    X_train, X_test, y_train, y_test = train_test_split(X, y_cuft, test_size=0.2, random_state=42, shuffle=False)
    rf_cuft = RandomForestRegressor(n_estimators=100, random_state=42)
    rf_cuft.fit(X_train, y_train)

    # 模型训练：Sales
    y_sales = daily_df['Sales']
    rf_sales = RandomForestRegressor(n_estimators=100, random_state=42)
    rf_sales.fit(X_train, y_sales.iloc[X_train.index])

    # 模型训练：Cost
    y_cost = daily_df['Cost']
    rf_cost = RandomForestRegressor(n_estimators=100, random_state=42)
    rf_cost.fit(X_train, y_cost.iloc[X_train.index])

    # 保存模型
    with open(os.path.join(base_dir, 'rf_model_cuft.pkl'), 'wb') as f:
        pickle.dump(rf_cuft, f)
    with open(os.path.join(base_dir, 'rf_model_sales.pkl'), 'wb') as f:
        pickle.dump(rf_sales, f)
    with open(os.path.join(base_dir, 'rf_model_cost.pkl'), 'wb') as f:
        pickle.dump(rf_cost, f)

    print("✅ 三个模型训练完毕并已保存：rf_model_cuft.pkl, rf_model_sales.pkl, rf_model_cost.pkl")
