from db_utils import query_to_dataframe  # 顶部导入
def load_sql(file_name, warehouse='NJ'):
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wh = warehouse.lower()
    file_core = file_name.lower().replace('.sql', '')
    full_path = os.path.join(base_dir, 'sql', f"{file_core}_{wh}.sql")
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


def predict_inventory(days=30, force=False, warehouse='NJ'):
    import os
    import pandas as pd
    import pickle
    import plotly.graph_objs as go
    from db_utils import query_to_dataframe
    from gauge_plot import get_current_container

    # 获取数据库中的实际库存 container 数量
    container = get_current_container()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 加载主数据（Total Cuft / Sales / Cost）
    sql_cuft = load_sql('daily_cuft_sales_cost.sql', warehouse)
    df = query_to_dataframe(sql_cuft)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

    # 加载 APO 数据
    sql_apo = load_sql('daily_apo.sql', warehouse)
    incoming_df = query_to_dataframe(sql_apo)
    incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])

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

    # 加载模型
    with open(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'), 'rb') as f:
        rf_cuft = pickle.load(f)
    with open(os.path.join(base_dir, f'rf_model_sales_{warehouse}.pkl'), 'rb') as f:
        rf_sales = pickle.load(f)
    with open(os.path.join(base_dir, f'rf_model_cost_{warehouse}.pkl'), 'rb') as f:
        rf_cost = pickle.load(f)

    y_pred = rf_cuft.predict(X)
    residual_std = (y_cuft - y_pred).std()
    z_score = 1.28

    # 生成未来日期
    forecast_dates = pd.date_range(start=pd.Timestamp.today().normalize(), periods=days, freq='D')
    future_df = pd.DataFrame({'Date': forecast_dates})
    future_df['dayofweek'] = future_df['Date'].dt.dayofweek
    future_df['day'] = future_df['Date'].dt.day
    future_df['month'] = future_df['Date'].dt.month

    last_known = daily_df.iloc[-1][['lag1', 'lag2', 'lag7']].values.tolist()
    cuft_preds, sales_preds, cost_preds = [], [], []

    for i in range(len(future_df)):
        if future_df.loc[i, 'dayofweek'] in [5, 6]:
            cuft_preds.append(0)
            sales_preds.append(0)
            cost_preds.append(0)
            continue

        if i == 0:
            lag1, lag2, lag7 = last_known
        else:
            lag1 = cuft_preds[-1]
            lag2 = lag1 if i == 1 else cuft_preds[-2]
            lag7 = lag1 if i < 7 else cuft_preds[i - 7]

        features = pd.DataFrame([{
            'dayofweek': future_df.loc[i, 'dayofweek'],
            'day': future_df.loc[i, 'day'],
            'month': future_df.loc[i, 'month'],
            'lag1': lag1,
            'lag2': lag2,
            'lag7': lag7
        }])

        cuft_pred = rf_cuft.predict(features)[0]
        sales_pred = rf_sales.predict(features)[0]
        cost_pred = rf_cost.predict(features)[0]

        cuft_preds.append(cuft_pred)
        sales_preds.append(sales_pred)
        cost_preds.append(cost_pred)

    future_df['Total Cuft Prediction'] = cuft_preds
    future_df['Sales Prediction'] = sales_preds
    future_df['Cost Prediction'] = cost_preds
    future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
    future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std

    # 加入 APO 数据
    incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])
    future_df = future_df.merge(incoming_df, on='Date', how='left')
    future_df['APO'] = future_df['APO'].fillna(0)

    container_list = []
    for _, row in future_df.iterrows():
        sold = row['Total Cuft Prediction'] / 2350
        container = container - sold + row['APO']
        container_list.append(container)
    future_df['container'] = container_list

    container_std = residual_std / 2350
    future_df['lower_bound'] = future_df['container'] - z_score * container_std
    future_df['upper_bound'] = future_df['container'] + z_score * container_std

    future_df[['container', 'lower_bound', 'upper_bound']] = future_df[['container', 'lower_bound', 'upper_bound']].round(2)
    future_df[['Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction']] = \
        future_df[['Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction']].round(0).astype(int)
    static_dir = os.path.join(base_dir, 'static')

    # 当前时间 & 月份范围
    today = pd.Timestamp.today().normalize()
    month_start = today.replace(day=1)
    month_end = (month_start + pd.offsets.MonthEnd(0))  # 当前月最后一天

    # 📌 Step 1: 真实数据部分（来自 df）
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    real_df = df[(df['Invoice Date'] >= month_start) & (df['Invoice Date'] <= today)]
    real_grouped = real_df.groupby('Invoice Date').agg({
        'Sales': 'sum',
        'Cost': 'sum',
        'Total Cuft': 'sum'
    }).reset_index()

    # 📌 Step 2: 预测数据部分（来自 future_df）
    future_part = future_df[(future_df['Date'] > today) & (future_df['Date'] <= month_end)]

    # 📌 Step 3: 合并
    monthly_sales = int(real_grouped['Sales'].sum() + future_part['Sales Prediction'].sum())
    monthly_cost = int(real_grouped['Cost'].sum() + future_part['Cost Prediction'].sum())
    monthly_cuft = int(real_grouped['Total Cuft'].sum() + future_part['Total Cuft Prediction'].sum())

    # 图表文件按天数命名，避免重复生成
    container_chart_path = os.path.join(static_dir, f'forecast/container_forecast_{days}_{warehouse}.html')
    sales_cost_chart_path = os.path.join(static_dir, f'forecast/sales_cost_forecast_{days}_{warehouse}.html')

    # 添加 Total 行到 forecast_df 的底部
    total_row = {
        'Date': 'Total',
        'container': '',
        'lower_bound': '',
        'upper_bound': '',
        'Sales Prediction': int(future_df['Sales Prediction'].sum()),
        'Cost Prediction': int(future_df['Cost Prediction'].sum()),
        'Total Cuft Prediction': int(future_df['Total Cuft Prediction'].sum())
    }
    forecast_with_total = pd.concat([future_df, pd.DataFrame([total_row])], ignore_index=True)

    if force or not os.path.exists(container_chart_path):
        print(f"📈 生成 container_forecast_{days}_NJ.html")
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=future_df['Date'], y=future_df['container'], mode='lines', name='Container', line=dict(color='royalblue')))
        fig1.add_trace(go.Scatter(
            x=pd.concat([future_df['Date'], future_df['Date'][::-1]]),
            y=pd.concat([future_df['upper_bound'], future_df['lower_bound'][::-1]]),
            fill='toself', fillcolor='rgba(135, 206, 250, 0.3)',
            line=dict(color='rgba(255,255,255,0)'), hoverinfo="skip", showlegend=True, name='Forecast Range'
        ))
        fig1.update_layout(
            title={'text': f'{days}-Day Container Forecast', 'x': 0.5, 'xanchor': 'center'},
            xaxis_title='Date',
            yaxis_title='Container',
            template='plotly_white',
            legend=dict(
                orientation='h',
                yanchor='top',
                y=1,
                xanchor='left',
                x=0
            ),
            margin=dict(l=20, r=20, t=30, b=20)
        )

        fig1.write_html(container_chart_path, config={
        'modeBarButtonsToRemove': [
            'zoom2d', 'pan2d', 'select2d', 'lasso2d',
            'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
            'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'
        ],
        'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'toImage'],
        'displaylogo': False
    })
    else:
        print(f"✅ 已存在 container_forecast_{days}_NJ.html")

    if force or not os.path.exists(sales_cost_chart_path):
        print(f"📈 生成 sales_cost_forecast_{days}_NJ.html")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=future_df['Date'], y=future_df['Sales Prediction'], mode='lines', name='Sales', line=dict(color='green')))
        fig2.add_trace(go.Scatter(x=future_df['Date'], y=future_df['Cost Prediction'], mode='lines', name='Cost', line=dict(color='orange')))
        fig2.update_layout(
            title={'text': f'{days}-Day Sales & Cost Forecast', 'x': 0.5, 'xanchor': 'center'},
            xaxis_title='Date',
            yaxis_title='Value',
            template='plotly_white',
            legend=dict(
                orientation='h',
                yanchor='top',
                y=1,
                xanchor='left',
                x=0
            ),
            margin=dict(l=20, r=20, t=30, b=20)
        )

        fig2.write_html(sales_cost_chart_path, config={
        'modeBarButtonsToRemove': [
            'zoom2d', 'pan2d', 'select2d', 'lasso2d',
            'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
            'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'
        ],
        'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'toImage'],
        'displaylogo': False
    })
    else:
        print(f"✅ 已存在 sales_cost_forecast_{days}.html")
        print("✅ 文件路径：", base_dir)
        print("✅ 模型文件路径：", os.path.join(base_dir, 'rf_model_cuft.pkl'))
        print("✅ 数据文件是否存在：", os.path.exists(base_dir))
        print("✅ 模型是否存在：", os.path.exists(os.path.join(base_dir, 'rf_model_cuft.pkl')))
        print(f"预测结果 dataframe 行数：{len(df)}")
    return {
        'forecast_df': forecast_with_total[
                ['Date', 'container', 'lower_bound', 'upper_bound', 'Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction']
            ],
        'monthly_summary': {
            'sales': monthly_sales,
            'cost': monthly_cost,
            'cuft': monthly_cuft
        }
    }

