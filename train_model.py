# train_model.py
import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import pickle

# 🟡 文件路径
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, 'Data')
file_path = os.path.join(data_dir, 'ModelRevenueDetails_test.csv')  # 注意这里是 CSV 文件

# 🟡 读取数据
df = pd.read_csv(file_path)
df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')
df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

# 🟡 日汇总
daily_df = df.groupby('Invoice Date').agg({
    'Total Cuft': 'sum',
    'Sales': 'sum',
    'Cost': 'sum'
}).reset_index()

# 🟡 特征工程
daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
daily_df['day'] = daily_df['Invoice Date'].dt.day
daily_df['month'] = daily_df['Invoice Date'].dt.month
daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)

X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]

# 🟡 分别训练三个模型
# 1️⃣ Total Cuft
y_cuft = daily_df['Total Cuft']
X_train, X_test, y_train, y_test = train_test_split(X, y_cuft, test_size=0.2, random_state=42, shuffle=False)
rf_cuft = RandomForestRegressor(n_estimators=100, random_state=42)
rf_cuft.fit(X_train, y_train)

# 2️⃣ Sales
y_sales = daily_df['Sales']
_, _, y_train_sales, y_test_sales = train_test_split(X, y_sales, test_size=0.2, random_state=42, shuffle=False)
rf_sales = RandomForestRegressor(n_estimators=100, random_state=42)
rf_sales.fit(X_train, y_train_sales)

# 3️⃣ Cost
y_cost = daily_df['Cost']
_, _, y_train_cost, y_test_cost = train_test_split(X, y_cost, test_size=0.2, random_state=42, shuffle=False)
rf_cost = RandomForestRegressor(n_estimators=100, random_state=42)
rf_cost.fit(X_train, y_train_cost)

# 🟡 保存模型
with open(os.path.join(base_dir, 'rf_model_cuft.pkl'), 'wb') as f:
    pickle.dump(rf_cuft, f)

with open(os.path.join(base_dir, 'rf_model_sales.pkl'), 'wb') as f:
    pickle.dump(rf_sales, f)

with open(os.path.join(base_dir, 'rf_model_cost.pkl'), 'wb') as f:
    pickle.dump(rf_cost, f)

print("✅ 三个模型训练完毕并已保存：rf_model_cuft.pkl, rf_model_sales.pkl, rf_model_cost.pkl")
