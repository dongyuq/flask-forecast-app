# train_model.py
import os
from db_utils import query_to_dataframe


def get_company_holidays(year):
    import pandas as pd

    # 固定日期节假日
    holiday_dates = [
        f'{year}-01-01',  # New Year's Day
        f'{year}-07-04',  # Independence Day
        f'{year}-12-25',  # Christmas
    ]

    # 感恩节：11月第4个星期四
    thanksgiving = pd.date_range(start=f'{year}-11-01', end=f'{year}-11-30', freq='W-THU')[3]

    # Memorial Day：5月最后一个星期一
    memorial_day = pd.date_range(start=f'{year}-05-01', end=f'{year}-05-31', freq='W-MON')[-1]

    # Labor Day：9月第一个星期一
    labor_day = pd.date_range(start=f'{year}-09-01', end=f'{year}-09-30', freq='W-MON')[0]

    holiday_dates.extend([
        memorial_day.strftime('%Y-%m-%d'),
        labor_day.strftime('%Y-%m-%d'),
        thanksgiving.strftime('%Y-%m-%d')
    ])

    return pd.to_datetime(holiday_dates).normalize()


base_dir = os.path.dirname(os.path.abspath(__file__))

def load_sql(file_name):
    sql_path = os.path.join(base_dir, 'sql', file_name)
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()




def retrain_models(warehouse):
    import os
    import pandas as pd
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    import pickle

    sql_file = f'daily_cuft_sales_cost_{warehouse.lower()}.sql'
    sql = load_sql(sql_file)
    df = query_to_dataframe(sql)

    # 数据清洗与转换
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Total Cuft'] = pd.to_numeric(df['Total Cuft'], errors='coerce')

    from zoneinfo import ZoneInfo
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date']).dt.tz_localize('UTC').dt.tz_convert(
        'America/Los_Angeles').dt.tz_localize(None)

    # 聚合按日
    daily_df = df.groupby('Invoice Date').agg({
        'Total Cuft': 'sum',
        'Sales': 'sum',
        'Cost': 'sum'
    }).reset_index()

    # 填补缺失日期
    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()

    # ✅ 正确生成节假日列表并打印
    years = daily_df['Invoice Date'].dt.year.unique()

    holidays = []
    for y in years:
        h = get_company_holidays(int(y))
        holidays.extend(h.tolist())
    holidays = pd.to_datetime(holidays)
    holidays = holidays[(holidays >= daily_df['Invoice Date'].min()) & (holidays < daily_df['Invoice Date'].max())]

    from pandas.tseries.offsets import BDay

    for holiday in holidays:
        idx = daily_df[daily_df['Invoice Date'] == holiday].index
        if not idx.empty:
            i = idx[0]
            next_workday = holiday + BDay(1)
            j = daily_df[daily_df['Invoice Date'] == next_workday].index
            if not j.empty:
                j = j[0]
                for col in ['Sales', 'Cost', 'Total Cuft']:
                    # ✅ 只有目标天没有数据时才合并
                    if daily_df.at[j, col] == 0:
                        daily_df.at[j, col] = daily_df.at[i, col]
                    else:
                        daily_df.at[j, col] += daily_df.at[i, col]
                    daily_df.at[i, col] = 0

    # 时间特征
    daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
    daily_df['day'] = daily_df['Invoice Date'].dt.day
    daily_df['month'] = daily_df['Invoice Date'].dt.month
    daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
    daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
    daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)

    # 模型训练
    X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]
    y_cuft = daily_df['Total Cuft']
    y_sales = daily_df['Sales']
    y_cost = daily_df['Cost']

    X_train, _, y_train_cuft, _ = train_test_split(X, y_cuft, test_size=0.2, shuffle=False)
    _, _, y_train_sales, _ = train_test_split(X, y_sales, test_size=0.2, shuffle=False)
    _, _, y_train_cost, _ = train_test_split(X, y_cost, test_size=0.2, shuffle=False)

    rf_cuft = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_cuft)
    rf_sales = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_sales)
    rf_cost = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_cost)

    # 保存模型
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_cuft, f)
    with open(os.path.join(base_dir, f'rf_model_sales_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_sales, f)
    with open(os.path.join(base_dir, f'rf_model_cost_{warehouse}.pkl'), 'wb') as f:
        pickle.dump(rf_cost, f)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    df['weekday'] = df['Invoice Date'].dt.dayofweek
    print("📊 周一数据点数量：", df[df['weekday'] == 0].shape[0])
    print("📊 周一数据点平均 Total Cuft：", df[df['weekday'] == 0]['Total Cuft'].mean())


    print(f"✅ {warehouse} 仓库模型训练完毕并已保存")


