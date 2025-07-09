import os

import pandas as pd
import plotly.graph_objs as go

def load_sql(file_name, warehouse='NJ'):
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wh = warehouse.lower()
    file_core = file_name.lower().replace('.sql', '')
    full_path = os.path.join(base_dir, 'sql', f"{file_core}_{wh}.sql")
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_predictions(future_df, warehouse, days=30):
    """
    使用 Prophet 模型预测未来 days 天的 Cuft, Sales, Cost。
    - 自动读取已保存模型
    - 返回三类预测值列表
    """
    import pickle
    import os

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 加载模型
    def load_model(metric):
        with open(os.path.join(base_dir, f'prophet_model_{metric}_{warehouse}.pkl'), 'rb') as f:
            return pickle.load(f)

    model_cuft = load_model('cuft')
    model_sales = load_model('sales')
    model_cost = load_model('cost')

    # 生成未来日期
    start_date = future_df['Date'].min()
    future_dates = pd.date_range(start=start_date, periods=days, freq='D')
    future_df_prophet = pd.DataFrame({'ds': future_dates})

    # 预测
    forecast_cuft = model_cuft.predict(future_df_prophet)
    forecast_sales = model_sales.predict(future_df_prophet)
    forecast_cost = model_cost.predict(future_df_prophet)

    # 提取 yhat（预测中值）
    cuft_preds = forecast_cuft['yhat'].clip(lower=0).tolist()
    sales_preds = forecast_sales['yhat'].clip(lower=0).tolist()
    cost_preds = forecast_cost['yhat'].clip(lower=0).tolist()

    return cuft_preds, sales_preds, cost_preds

def calculate_monthly_summary(df, future_df):
    today = pd.Timestamp.today().normalize()
    month_start = today.replace(day=1)
    month_end = (month_start + pd.offsets.MonthEnd(0))

    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
    real_df = df[(df['Invoice Date'] >= month_start) & (df['Invoice Date'] <= today)]
    real_grouped = real_df.groupby('Invoice Date').agg({
        'Sales': 'sum',
        'Cost': 'sum',
        'Total Cuft': 'sum'
    }).reset_index()

    future_part = future_df[(future_df['Date'] > today) & (future_df['Date'] <= month_end)]
    real_past = real_grouped[real_grouped['Invoice Date'] < today]

    future_today = future_df[future_df['Date'] == today]
    today_sales = future_today['Sales Prediction'].values[0] if not future_today.empty else 0
    today_cost = future_today['Cost Prediction'].values[0] if not future_today.empty else 0
    today_cuft = future_today['Total Cuft Prediction'].values[0] if not future_today.empty else 0

    monthly_sales = int(real_past['Sales'].sum() + today_sales + future_part['Sales Prediction'].sum())
    monthly_cost = int(real_past['Cost'].sum() + today_cost + future_part['Cost Prediction'].sum())
    monthly_cuft = int(real_past['Total Cuft'].sum() + today_cuft + future_part['Total Cuft Prediction'].sum())

    return {
        'sales': monthly_sales,
        'cost': monthly_cost,
        'cuft': monthly_cuft
    }

def adjust_for_holidays(future_df, residual_std, z_score=1.28):
    for col in ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']:
        future_df[col] = future_df[col] + future_df[col].shift(1).where(future_df['is_holiday'] == 1, 0)

    future_df.loc[future_df['is_holiday'] == 1, ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']] = 0

    future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
    future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std
    return future_df

def generate_forecast_charts(future_df, static_dir, days, warehouse, force):
    total_row = {
        'Date': 'Total',
        'container': '',
        'lower_bound': '',
        'upper_bound': '',
        'Sales Prediction': int(future_df['Sales Prediction'].sum()),
        'Cost Prediction': int(future_df['Cost Prediction'].sum()),
        'Total Cuft Prediction': int(future_df['Total Cuft Prediction'].sum()),
        'Containers Forecast': round(future_df['Containers Forecast'].sum(), 1)
    }
    forecast_with_total = pd.concat([future_df, pd.DataFrame([total_row])], ignore_index=True)

    container_chart_path = os.path.join(static_dir, f'forecast/container_forecast_{days}_{warehouse}.html')
    sales_cost_chart_path = os.path.join(static_dir, f'forecast/sales_cost_forecast_{days}_{warehouse}.html')

    # 保留 future_df 中用于作图的字段两位小数
    future_df[['container', 'lower_bound', 'upper_bound','Total Cuft Prediction','Containers Forecast']] = future_df[
        ['container', 'lower_bound', 'upper_bound','Total Cuft Prediction','Containers Forecast']].round(2)

    if force or not os.path.exists(container_chart_path):
        print(f"📈 生成 container_forecast_{days}_{warehouse}.html")
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
        print(f"✅ 已存在 container_forecast_{days}_{warehouse}.html")

    if force or not os.path.exists(sales_cost_chart_path):
        print(f"📈 生成 sales_cost_forecast_{days}_{warehouse}.html")
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
        print(f"✅ 已存在 sales_cost_forecast_{days}_{warehouse}.html")

    return forecast_with_total

def predict_inventory(days=30, force=False, warehouse='NJ'):
    import os
    import pandas as pd
    from db_utils import query_to_dataframe
    from gauge_plot import get_current_container
    from train_scriptl import get_company_holidays
    from datetime import datetime
    from zoneinfo import ZoneInfo

    base_dir = os.path.dirname(os.path.abspath(__file__))
    container = get_current_container()

    sql_cuft = load_sql('daily_cuft_sales_cost.sql', warehouse)
    df = query_to_dataframe(sql_cuft)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

    sql_apo = load_sql('daily_apo.sql', warehouse)
    incoming_df = query_to_dataframe(sql_apo)
    incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])

    daily_df = df.groupby('Invoice Date').agg({
        'Total Cuft': 'sum', 'Sales': 'sum', 'Cost': 'sum'
    }).reset_index()

    # Prophet 不需要这些 lag 特征，但我们保留 daily_df 供 residual_std 使用
    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()

    # 加载 Prophet 模型预测（替换 RandomForest）
    pst_now = datetime.now(ZoneInfo('America/Los_Angeles')).date()
    forecast_dates = pd.date_range(start=pst_now, periods=days, freq='D')
    print("🌞 当前 PST 日期为：", pst_now)

    future_df = pd.DataFrame({'Date': forecast_dates})
    future_df['Date'] = future_df['Date'].dt.normalize()
    future_df['dayofweek'] = future_df['Date'].dt.dayofweek
    future_df['day'] = future_df['Date'].dt.day
    future_df['month'] = future_df['Date'].dt.month

    future_years = future_df['Date'].dt.year.unique()
    all_holidays = []
    for y in future_years:
        holidays = get_company_holidays(y)
        all_holidays.extend(pd.to_datetime(holidays))

    future_holidays = pd.to_datetime(all_holidays).normalize()
    future_df['is_holiday'] = future_df['Date'].isin(future_holidays).astype(int)

    # ✅ 使用 Prophet 进行预测
    cuft_preds, sales_preds, cost_preds = generate_predictions(future_df, warehouse, days)

    future_df['Total Cuft Prediction'] = cuft_preds
    future_df['Containers Forecast'] = (future_df['Total Cuft Prediction'] / 2350).round(2)
    future_df['Sales Prediction'] = sales_preds
    future_df['Cost Prediction'] = cost_preds


    # ⚠️ 使用 Prophet 时无法直接获取 residual_std，这里用历史 cuft 标准差作为估计
    residual_std = daily_df['Total Cuft'].std()
    z_score = 1.28

    future_df = adjust_for_holidays(future_df, residual_std)

    future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
    future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std

    # 加入 APO 逻辑和 container 滚动计算
    future_df = future_df.merge(incoming_df, on='Date', how='left').fillna({'APO': 0})
    container_list = []
    for _, row in future_df.iterrows():
        sold = row['Total Cuft Prediction'] / 2350
        container = container - sold + row['APO']
        container_list.append(container)
    future_df['container'] = container_list

    std_cont = residual_std / 2350
    future_df['lower_bound'] = future_df['container'] - z_score * std_cont
    future_df['upper_bound'] = future_df['container'] + z_score * std_cont

    future_df.loc[future_df['dayofweek'] >= 5, ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']] = 0

    # 生成图表
    static_dir = os.path.join(base_dir, 'static')
    future_df[['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']] = future_df[
        ['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']].round(2)

    forecast_with_total = generate_forecast_charts(future_df, static_dir, days, warehouse, force)

    monthly_summary = calculate_monthly_summary(df, future_df)

    return {
        'forecast_df': forecast_with_total,
        'monthly_summary': monthly_summary
    }
