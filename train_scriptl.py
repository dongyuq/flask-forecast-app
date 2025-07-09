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


def remove_outliers(series, method='iqr', factor=1.5):
    if method == 'iqr':
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        return series.clip(lower, upper)
    elif method == 'rolling':
        rolling_median = series.rolling(7, min_periods=1, center=True).median()
        return rolling_median


def retrain_models(warehouse):
    import os
    import pandas as pd
    import pickle
    from prophet import Prophet
    from datetime import timedelta
    from pandas.tseries.offsets import BDay

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

    # 限定训练数据时间范围
    start_date = pd.to_datetime('2024-01-01')
    end_date = pd.to_datetime('2025-07-01')
    daily_df = daily_df[(daily_df['Invoice Date'] >= start_date) & (daily_df['Invoice Date'] < end_date)]

    # 去异常值
    daily_df['Sales'] = remove_outliers(daily_df['Sales'], method='iqr')
    daily_df['Cost'] = remove_outliers(daily_df['Cost'], method='iqr')
    daily_df['Total Cuft'] = remove_outliers(daily_df['Total Cuft'], method='iqr')

    # 填补缺失日期
    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()

    # 仅保留最近6个月用于 weekday 均值
    latest_date = daily_df['Invoice Date'].max()
    six_months_ago = latest_date - pd.DateOffset(months=6)
    recent_df = daily_df[daily_df['Invoice Date'] >= six_months_ago]

    weekday_means = recent_df.groupby(recent_df['Invoice Date'].dt.weekday)[['Total Cuft', 'Sales', 'Cost']].mean()

    for i in range(len(daily_df)):
        row = daily_df.iloc[i]
        weekday = row['Invoice Date'].weekday()
        prev_dates = [row['Invoice Date'] - timedelta(weeks=k) for k in range(1, 4)]
        prev_values = daily_df[daily_df['Invoice Date'].isin(prev_dates)]
        prev_values = prev_values[prev_values['Invoice Date'].dt.weekday == weekday]

        for col in ['Total Cuft', 'Sales', 'Cost']:
            threshold = weekday_means.loc[weekday, col] * 0.3
            if row[col] < threshold and not prev_values.empty:
                valid_values = prev_values[col][prev_values[col] > 0]
                if not valid_values.empty:
                    daily_df.at[i, col] = valid_values.mean()

    # 获取节假日
    years = daily_df['Invoice Date'].dt.year.unique()
    holidays = []
    for y in years:
        h = get_company_holidays(int(y))
        holidays.extend(h.tolist())
    holidays = pd.to_datetime(holidays)
    holidays = holidays[(holidays >= daily_df['Invoice Date'].min()) & (holidays < daily_df['Invoice Date'].max())]

    # 合并节假日值到下个工作日
    for holiday in holidays:
        idx = daily_df[daily_df['Invoice Date'] == holiday].index
        if not idx.empty:
            i = idx[0]
            next_workday = holiday + BDay(1)
            j = daily_df[daily_df['Invoice Date'] == next_workday].index
            if not j.empty:
                j = j[0]
                for col in ['Sales', 'Cost', 'Total Cuft']:
                    if daily_df.at[j, col] == 0:
                        daily_df.at[j, col] = daily_df.at[i, col]
                    else:
                        daily_df.at[j, col] += daily_df.at[i, col]
                    daily_df.at[i, col] = 0

    # ✅ Prophet 模型训练与保存
    base_dir = os.path.dirname(os.path.abspath(__file__))
    holidays_df = pd.DataFrame({
        'ds': holidays,
        'holiday': 'company_holiday'
    })

    def train_and_save_prophet(df, target_col, model_name):
        prophet_df = df[['Invoice Date', target_col]].rename(columns={
            'Invoice Date': 'ds',
            target_col: 'y'
        })

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            holidays=holidays_df
        )

        model.fit(prophet_df)

        with open(os.path.join(base_dir, f'prophet_model_{model_name}_{warehouse}.pkl'), 'wb') as f:
            pickle.dump(model, f)

        print(f"✅ Prophet 模型 {model_name} 训练并保存成功")

    train_and_save_prophet(daily_df, 'Total Cuft', 'cuft')
    train_and_save_prophet(daily_df, 'Sales', 'sales')
    train_and_save_prophet(daily_df, 'Cost', 'cost')

    df['weekday'] = df['Invoice Date'].dt.dayofweek
    print("📊 周一数据点数量：", df[df['weekday'] == 0].shape[0])
    print("📊 周一数据点平均 Total Cuft：", df[df['weekday'] == 0]['Total Cuft'].mean())
    print(f"✅ {warehouse} 仓库 Prophet 模型训练完毕并已保存")
