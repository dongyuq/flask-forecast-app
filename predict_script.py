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

def get_recent_history_data(warehouse, days_back=90):
    from db_utils import query_to_dataframe
    from datetime import datetime, timedelta

    # 计算起止时间
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    sql = f"""
        WITH combined_data AS (
            SELECT
                location,
                model,
                manufacturer,
                invoice_date,
                price,
                cost,
                qty
            FROM bi.v_model_revenue_etail

            UNION ALL

            SELECT
                'NJHMLG' AS location,
                model,
                manufacturer,
                invoice_date,
                0 AS price,
                0 AS cost,
                qty
            FROM bi.v_rma_qty
            WHERE invoice_date IS NOT NULL
              AND LOWER(is_to_stock) = 'no'
        )

        SELECT
            c.invoice_date::date AS "Date",
            SUM(c.price) AS "Sales",
            SUM(c.cost) AS "Cost"
        FROM combined_data c
        WHERE c.invoice_date BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY c.invoice_date::date
        ORDER BY "Date"
    """

    df = query_to_dataframe(sql)
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def generate_predictions(future_df, warehouse, days=30, history_df=None):
    import pickle
    import os
    import numpy as np
    import pandas as pd

    base_dir = os.path.dirname(os.path.abspath(__file__))

    def load_model(metric):
        with open(os.path.join(base_dir, f'prophet_model_{metric}_{warehouse}.pkl'), 'rb') as f:
            return pickle.load(f)

    # ✅ 只加载 sales 模型
    model_sales = load_model('sales')

    start_date = future_df['Date'].min()
    future_dates = pd.date_range(start=start_date, periods=days, freq='D')
    future_df_prophet = pd.DataFrame({'ds': future_dates})

    forecast_sales = model_sales.predict(future_df_prophet)
    sales_preds = np.array(forecast_sales['yhat'])

    # ✨ 添加扰动（包含季节性 + 随机波动）
    if history_df is not None and not history_df.empty:
        np.random.seed(42)

        # 正弦周期波动（模拟周五高、周一低）
        seasonal_wave = 0.15 * np.sin(np.linspace(0, 3 * np.pi, len(sales_preds)))
        noise = np.random.normal(0, 0.25, size=len(sales_preds))  # 25% 波动
        sales_preds = sales_preds * (1 + noise + seasonal_wave)
        sales_preds = np.clip(sales_preds, a_min=0, a_max=sales_preds * 1.25)

        # 👇 平均 Cuft / Sales 比率（推 Cuft）
        cuft_sales_ratio_series = (history_df['Total Cuft'] / history_df['Sales']).replace([np.inf, -np.inf], np.nan).dropna()
        avg_cuft_per_dollar = cuft_sales_ratio_series.mean()
        cuft_preds = sales_preds * avg_cuft_per_dollar

        # 👇 平均 Cost / Sales 比率（推 Cost）
        cost_ratio_series = (history_df['Cost'] / history_df['Sales']).replace([np.inf, -np.inf], np.nan).dropna()
        avg_cost_ratio = cost_ratio_series.clip(upper=1).mean()
        cost_preds = sales_preds * avg_cost_ratio
    else:
        # Fallback
        cuft_preds = sales_preds * 0.072  # 假设每 $1 占 0.03 cuft
        cost_preds = sales_preds * 0.7

    return cuft_preds.tolist(), sales_preds.tolist(), cost_preds.tolist()



def calculate_monthly_summary(df, future_df):
    from datetime import datetime
    import pytz

    tz = pytz.timezone('America/Los_Angeles')
    today = pd.Timestamp.now(tz).normalize()  # 用洛杉矶时间的当天0点
    month_start = today.replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(0)

    # 🟩 实际值
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date']).dt.tz_localize(tz, ambiguous='NaT', nonexistent='NaT')
    real_df = df[(df['Invoice Date'] >= month_start) & (df['Invoice Date'] < today)]
    real_grouped = real_df.groupby('Invoice Date').agg({
        'Sales': 'sum',
        'Cost': 'sum',
        'Total Cuft': 'sum'
    }).reset_index()

    actual_sales = real_grouped['Sales'].sum()
    actual_cost = real_grouped['Cost'].sum()
    actual_cuft = real_grouped['Total Cuft'].sum()

    # 🟨 预测值（未来部分 + 今天）
    future_df['Date'] = pd.to_datetime(future_df['Date']).dt.tz_localize(tz)

    forecast_range = future_df[
        (future_df['Date'] >= today) & (future_df['Date'] <= month_end)
    ]

    today_row = forecast_range[forecast_range['Date'] == today]
    future_rows = forecast_range[forecast_range['Date'] > today]

    today_sales = today_row['Sales Prediction'].values[0] if not today_row.empty else 0
    today_cost = today_row['Cost Prediction'].values[0] if not today_row.empty else 0
    today_cuft = today_row['Total Cuft Prediction'].values[0] if not today_row.empty else 0

    forecast_sales = today_sales + future_rows['Sales Prediction'].sum()
    forecast_cost = today_cost + future_rows['Cost Prediction'].sum()
    forecast_cuft = today_cuft + future_rows['Total Cuft Prediction'].sum()

    monthly_sales = int(actual_sales + forecast_sales)
    monthly_cost = int(actual_cost + forecast_cost)
    monthly_cuft = int(actual_cuft + forecast_cuft)

    # ✅ 打印实际 & 预测值
    print(f"🔹 实际 Sales: ${actual_sales:,.0f} | Cost: ${actual_cost:,.0f} | Cuft: {actual_cuft:,.0f}")
    print(f"🔸 预测 Sales: ${forecast_sales:,.0f} | Cost: ${forecast_cost:,.0f} | Cuft: {forecast_cuft:,.0f}")
    print(f"✅ 本月总计 Sales: ${monthly_sales:,} | Cost: ${monthly_cost:,} | Cuft: {monthly_cuft:,}")

    # ✅ 检查 forecast 是否有重复日期
    if forecast_range['Date'].duplicated().any():
        print("⚠️ forecast_range 中存在重复日期！")
    else:
        print("✅ 预测日期没有重复。")

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

def generate_forecast_charts(future_df, static_dir, days, warehouse, force, history_df=None):
    import plotly.graph_objects as go
    import pandas as pd
    import os

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

    future_df[['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']] = future_df[
        ['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']].round(2)

    # ✅ Container 图保持不变
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
            xaxis_title='Date', yaxis_title='Container',
            template='plotly_white',
            legend=dict(orientation='h', yanchor='top', y=1, xanchor='left', x=0),
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

    # ✅ Sales / Cost 图：实线为历史，虚线为预测
    if force or not os.path.exists(sales_cost_chart_path):
        print(f"📈 生成 sales_cost_forecast_{days}_{warehouse}.html")
        fig2 = go.Figure()

        if history_df is not None:
            history_df = history_df.sort_values('Date')
            sales_actual = history_df[['Date', 'Sales']]
            sales_actual['Sales'] = sales_actual['Sales'].round(2)
            cost_actual = history_df[['Date', 'Cost']]
            cost_actual['Cost'] = cost_actual['Cost'].round(2)
        else:
            sales_actual = pd.DataFrame(columns=['Date', 'Sales'])
            cost_actual = pd.DataFrame(columns=['Date', 'Cost'])

        sales_pred = future_df[['Date', 'Sales Prediction']].rename(columns={'Sales Prediction': 'Sales'})
        sales_pred['Sales'] = sales_pred['Sales'].round(2)
        cost_pred = future_df[['Date', 'Cost Prediction']].rename(columns={'Cost Prediction': 'Cost'})
        cost_pred['Cost'] = cost_pred['Cost'].round(2)

        # 📊 实线部分
        fig2.add_trace(go.Scatter(
            x=sales_actual['Date'], y=sales_actual['Sales'], mode='lines',
            name='Actual Sales', line=dict(color='green'),
            hovertemplate='%{x}<br>%{y:.0f}<extra></extra>'
        ))
        fig2.add_trace(go.Scatter(
            x=cost_actual['Date'], y=cost_actual['Cost'], mode='lines',
            name='Actual Cost', line=dict(color='orange'),
            hovertemplate='%{x}<br>%{y:.0f}<extra></extra>'
        ))

        # 📈 虚线部分（预测）
        fig2.add_trace(go.Scatter(
            x=sales_pred['Date'], y=sales_pred['Sales'], mode='lines',
            name='Forecast Sales', line=dict(color='green', dash='dash'),
            hovertemplate='%{x}<br>%{y:.0f}<extra></extra>'
        ))
        fig2.add_trace(go.Scatter(
            x=cost_pred['Date'], y=cost_pred['Cost'], mode='lines',
            name='Forecast Cost', line=dict(color='orange', dash='dash'),
            hovertemplate='%{x}<br>%{y:.0f}<extra></extra>'
        ))

        fig2.update_layout(
            title={'text': f'{days}-Day Sales & Cost Forecast', 'x': 0.5, 'xanchor': 'center'},
            xaxis_title='Date', yaxis_title='Value',yaxis=dict(tickformat=',.0f'),
            template='plotly_white',
            legend=dict(orientation='h', yanchor='top', y=1, xanchor='left', x=0),
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
    container = get_current_container(warehouse)

    # 📥 加载 daily cuft 数据
    sql_cuft = load_sql('daily_cuft_sales_cost.sql', warehouse)
    df = query_to_dataframe(sql_cuft)
    df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])

    # 📥 加载 APO 数据
    sql_apo = load_sql('daily_apo.sql', warehouse)
    incoming_df = query_to_dataframe(sql_apo)
    incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])

    # 📊 聚合为 daily_df
    daily_df = df.groupby('Invoice Date').agg({
        'Total Cuft': 'sum', 'Sales': 'sum', 'Cost': 'sum'
    }).reset_index()
    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()

    # 📅 构造统一预测90天的时间区间，从今天开始
    now_ts = pd.Timestamp(datetime.now(ZoneInfo('America/Los_Angeles'))).tz_localize(None)
    forecast_start = now_ts.normalize()
    full_days = 90
    forecast_dates = pd.date_range(start=forecast_start, periods=full_days, freq='D')

    future_df_full = pd.DataFrame({'Date': forecast_dates})
    future_df_full['Date'] = future_df_full['Date'].dt.normalize()
    future_df_full['dayofweek'] = future_df_full['Date'].dt.dayofweek
    future_df_full['day'] = future_df_full['Date'].dt.day
    future_df_full['month'] = future_df_full['Date'].dt.month

    # ✅ 获取最近三个月历史数据
    cutoff_date = forecast_start - pd.Timedelta(days=80)
    history_df = daily_df[daily_df['Invoice Date'] >= cutoff_date].copy()
    history_df = history_df.rename(columns={'Invoice Date': 'Date'})[['Date', 'Sales', 'Cost']]
    history_df = history_df.merge(daily_df[['Invoice Date', 'Total Cuft']].rename(columns={'Invoice Date': 'Date'}), on='Date', how='left')

    # 🎌 节假日处理
    future_years = future_df_full['Date'].dt.year.unique()
    all_holidays = []
    for y in future_years:
        holidays = get_company_holidays(y)
        all_holidays.extend(pd.to_datetime(holidays))
    future_holidays = pd.to_datetime(all_holidays).normalize()
    future_df_full['is_holiday'] = future_df_full['Date'].isin(future_holidays).astype(int)

    # 🔮 使用 Prophet 模型预测全量 future_df_full
    cuft_preds, sales_preds, cost_preds = generate_predictions(
        future_df_full, warehouse, days=full_days, history_df=history_df
    )
    future_df_full['Total Cuft Prediction'] = cuft_preds
    # 设置周末（周六=5，周日=6）卖出为0
    future_df_full['Containers Forecast'] = future_df_full.apply(
        lambda row: 0 if row['dayofweek'] >= 5 else round(row['Total Cuft Prediction'] / 2350, 2),
        axis=1
    )

    future_df_full['Sales Prediction'] = sales_preds
    future_df_full['Cost Prediction'] = cost_preds


    # 📉 上下界估算
    residual_std = daily_df['Total Cuft'].std()
    z_score = 2.576
    future_df_full = adjust_for_holidays(future_df_full, residual_std)
    future_df_full['lower'] = future_df_full['Total Cuft Prediction'] - z_score * residual_std
    future_df_full['upper'] = future_df_full['Total Cuft Prediction'] + z_score * residual_std

    # 📦 容器库存模拟
    future_df_full = future_df_full.merge(incoming_df, on='Date', how='left').fillna({'APO': 0})
    container_list = []
    for _, row in future_df_full.iterrows():
        sold = row['Total Cuft Prediction'] / 2350
        apo = row['APO']
        is_weekend = row['dayofweek'] >= 5

        if is_weekend and sold == 0 and apo == 0:
            # container unchanged
            pass
        else:
            container = container - sold + apo

        container_list.append(container)

    future_df_full['container'] = container_list

    std_cont = residual_std / 2350
    future_df_full['lower_bound'] = future_df_full['container'] - z_score * std_cont
    future_df_full['upper_bound'] = future_df_full['container'] + z_score * std_cont

    # 📅 周末预测为 0
    future_df_full.loc[future_df_full['dayofweek'] >= 5, ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']] = 0

    future_df = future_df_full.iloc[:days].copy()

    # 📈 当前预测图表（含 total 行）
    static_dir = os.path.join(base_dir, 'static')
    future_df[['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']] = future_df[
        ['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']].round(2)
    force_generate = True if days in [30, 60, 90] else force

    # 📊 保存 30/60/90 图表（统一用 future_df_full）
    # 📈 当前预测图表（含 total 行）并返回
    forecast_with_total = generate_forecast_charts(
        future_df, static_dir, days, warehouse, force_generate, history_df=history_df
    )

    # 📊 保存 30/60/90 图表，每个都添加 total 行
    for d in [30, 60, 90]:
        sliced_df = future_df_full.iloc[:d].copy()
        sliced_df[['container', 'lower_bound', 'upper_bound',
                   'Total Cuft Prediction', 'Containers Forecast']] = sliced_df[
            ['container', 'lower_bound', 'upper_bound',
             'Total Cuft Prediction', 'Containers Forecast']].round(2)

        _ = generate_forecast_charts(
            sliced_df, static_dir, d, warehouse, force, history_df=history_df
        )

    # 📊 月度汇总（只影响右上角指标）
    monthly_summary = calculate_monthly_summary(df, future_df_full)

    return {
        'forecast_df': forecast_with_total,
        'monthly_summary': monthly_summary
    }



