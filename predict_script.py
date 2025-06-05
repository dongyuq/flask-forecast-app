def predict_inventory(days=30):
    import os
    import matplotlib
    matplotlib.use('Agg')
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    # 🟡 改为相对路径
    base_dir = os.path.dirname(__file__)
    data_dir = os.path.join(base_dir, 'data')
    file_path = os.path.join(data_dir, 'ModelRevenueDetails_test.xlsx')
    apo_path = os.path.join(data_dir, 'APO.xlsx')

    # 读数据
    df = pd.read_excel(file_path, sheet_name='Sheet0')
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    daily_cuft = df.groupby('Invoice Date')['Total Cuft'].sum().reset_index()
    daily_cuft = daily_cuft.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
    daily_cuft['dayofweek'] = daily_cuft['Invoice Date'].dt.dayofweek
    daily_cuft['day'] = daily_cuft['Invoice Date'].dt.day
    daily_cuft['month'] = daily_cuft['Invoice Date'].dt.month
    daily_cuft['lag1'] = daily_cuft['Total Cuft'].shift(1).fillna(0)
    daily_cuft['lag2'] = daily_cuft['Total Cuft'].shift(2).fillna(0)
    daily_cuft['lag7'] = daily_cuft['Total Cuft'].shift(7).fillna(0)

    # 训练模型
    X = daily_cuft[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]
    y = daily_cuft['Total Cuft']
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)
    rf = RandomForestRegressor(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    y_pred = rf.predict(X_test)
    residuals = y_test - y_pred
    residual_std = residuals.std()
    z_score = 1.28  # 80%置信区间

    # 预测未来
    forecast_dates = pd.date_range(start='2025-06-01', periods=days, freq='D')
    future_df = pd.DataFrame({'Invoice Date': forecast_dates})
    future_df['dayofweek'] = future_df['Invoice Date'].dt.dayofweek
    future_df['day'] = future_df['Invoice Date'].dt.day
    future_df['month'] = future_df['Invoice Date'].dt.month

    last_known = daily_cuft.iloc[-1][['lag1', 'lag2', 'lag7']].values.tolist()
    future_preds = []
    for i in range(len(future_df)):
        if future_df.loc[i, 'dayofweek'] in [5, 6]:  # 周末不发货
            future_preds.append(0)
            continue
        if i == 0:
            lag1, lag2, lag7 = last_known
        else:
            lag1 = future_preds[-1]
            lag2 = lag1 if i == 1 else future_preds[-2]
            lag7 = lag1 if i < 7 else future_preds[i - 7]
        features = [[future_df.loc[i, 'dayofweek'], future_df.loc[i, 'day'], future_df.loc[i, 'month'], lag1, lag2, lag7]]
        pred = rf.predict(features)[0]
        future_preds.append(pred)
    future_df['Total Cuft Prediction'] = future_preds
    future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
    future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std
    future_df = future_df.rename(columns={'Invoice Date': 'Date'})

    # 加入 APO 数据
    incoming_df = pd.read_excel(apo_path)
    incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])
    future_df = future_df.merge(incoming_df, on='Date', how='left')
    future_df['APO'] = future_df['APO'].fillna(0)

    # 递推 container
    container_list = []
    container = 105  # 初始值

    for i, row in future_df.iterrows():
        sold = row['Total Cuft Prediction'] / 2350
        container = container - sold + row['APO']
        container_list.append(container)

    future_df['container'] = container_list

    # ± residual_std 置信区间
    container_std = residual_std / 2350
    future_df['lower_bound'] = future_df['container'] - z_score * container_std
    future_df['upper_bound'] = future_df['container'] + z_score * container_std

    # 保留两位小数
    future_df[['container', 'lower_bound', 'upper_bound']] = future_df[['container', 'lower_bound', 'upper_bound']].round(2)

    # 绘制图表
    plt.style.use('ggplot')
    plt.figure(figsize=(12, 6))
    plt.plot(future_df['Date'], future_df['container'], color='royalblue', linewidth=2, label='Predicted Container')
    plt.fill_between(future_df['Date'], future_df['lower_bound'], future_df['upper_bound'], color='skyblue', alpha=0.3, label='80% Confidence Interval')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%y-%m-%d'))
    plt.title(f'{days}-Day Forecast (with 80% Confidence Interval)', fontsize=16)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Container', fontsize=12)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()

    # 保存图表
    static_dir = os.path.join(base_dir, 'static')
    plt.savefig(os.path.join(static_dir, 'prediction.png'), dpi=150)
    plt.close()

    return future_df[['Date', 'container', 'lower_bound', 'upper_bound']]
