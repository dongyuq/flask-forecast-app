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

def retrain_models(warehouse):
    sql_file = f'daily_cuft_sales_cost_{warehouse.lower()}.sql'
    sql = load_sql(sql_file)
    df = query_to_dataframe(sql)

    # 数据清洗与转换
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

    daily_df = df.groupby('Invoice Date').agg({
        'Total Cuft': 'sum',
        'Sales': 'sum',
        'Cost': 'sum'
    }).reset_index()

    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
    daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
    daily_df['day'] = daily_df['Invoice Date'].dt.day
    daily_df['month'] = daily_df['Invoice Date'].dt.month
    daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
    daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
    daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)

    X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]
    y_cuft = daily_df['Total Cuft']
    y_sales = daily_df['Sales']
    y_cost = daily_df['Cost']

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    import pickle

    X_train, _, y_train_cuft, _ = train_test_split(X, y_cuft, test_size=0.2, shuffle=False)
    _, _, y_train_sales, _ = train_test_split(X, y_sales, test_size=0.2, shuffle=False)
    _, _, y_train_cost, _ = train_test_split(X, y_cost, test_size=0.2, shuffle=False)

    rf_cuft = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_cuft)
    rf_sales = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_sales)
    rf_cost = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_cost)

    # 保存模型（区分不同仓库）
    with open(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_cuft, f)
    with open(os.path.join(base_dir, f'rf_model_sales_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_sales, f)
    with open(os.path.join(base_dir, f'rf_model_cost_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_cost, f)

    print(f"✅ {warehouse} 仓库模型训练完毕并已保存")

