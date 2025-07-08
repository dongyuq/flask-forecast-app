import os

from train_scriptl import get_company_holidays
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

# def predict_inventory(days=30, force=False, warehouse='NJ'):
#     import os
#     import pandas as pd
#     import pickle
#     import plotly.graph_objs as go
#     from db_utils import query_to_dataframe
#     from gauge_plot import get_current_container
#     from train_scriptl import get_company_holidays
#
#     # 获取数据库中的实际库存 container 数量
#     container = get_current_container()
#
#     base_dir = os.path.dirname(os.path.abspath(__file__))
#     # 加载主数据（Total Cuft / Sales / Cost）
#     sql_cuft = load_sql('daily_cuft_sales_cost.sql', warehouse)
#     df = query_to_dataframe(sql_cuft)
#     df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
#
#     # 加载 APO 数据
#     sql_apo = load_sql('daily_apo.sql', warehouse)
#     incoming_df = query_to_dataframe(sql_apo)
#     incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])
#
#     df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
#
#     daily_df = df.groupby('Invoice Date').agg({
#         'Total Cuft': 'sum',
#         'Sales': 'sum',
#         'Cost': 'sum'
#     }).reset_index()
#
#     daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
#     daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
#     daily_df['day'] = daily_df['Invoice Date'].dt.day
#     daily_df['month'] = daily_df['Invoice Date'].dt.month
#     daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
#     daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
#     daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)
#
#     X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]
#     y_cuft = daily_df['Total Cuft']
#
#     # 加载模型
#     with open(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'), 'rb') as f:
#         rf_cuft = pickle.load(f)
#     with open(os.path.join(base_dir, f'rf_model_sales_{warehouse}.pkl'), 'rb') as f:
#         rf_sales = pickle.load(f)
#     with open(os.path.join(base_dir, f'rf_model_cost_{warehouse}.pkl'), 'rb') as f:
#         rf_cost = pickle.load(f)
#
#     y_pred = rf_cuft.predict(X)
#     residual_std = (y_cuft - y_pred).std()
#     z_score = 1.28
#
#     # 生成未来日期
#     forecast_dates = pd.date_range(start=pd.Timestamp.today().normalize(), periods=days, freq='D')
#     future_df = pd.DataFrame({'Date': forecast_dates})
#     future_df['Date'] = future_df['Date'].dt.normalize()  # ← 加这一行！！
#
#     future_df['dayofweek'] = future_df['Date'].dt.dayofweek
#     future_df['day'] = future_df['Date'].dt.day
#     future_df['month'] = future_df['Date'].dt.month
#
#     # # 加入未来日期 is_holiday 特征
#     future_years = future_df['Date'].dt.year.unique()
#
#     # 🔁 正确顺序 ✅：先定义再 normalize
#     future_holidays = []
#
#     for y in future_years:
#         future_holidays.extend(get_company_holidays(y))
#
#     # 转为 datetime 并 normalize，确保精确匹配
#     future_holidays = pd.to_datetime(future_holidays).normalize()
#
#     # 再做判断
#     future_df['is_holiday'] = future_df['Date'].isin(future_holidays).astype(int)
#
#     last_known = daily_df.iloc[-1][['lag1', 'lag2', 'lag7']].values.tolist()
#     cuft_preds, sales_preds, cost_preds = [], [], []
#
#     for i in range(len(future_df)):
#         if future_df.loc[i, 'dayofweek'] in [5,6]:
#             cuft_preds.append(0)
#             sales_preds.append(0)
#             cost_preds.append(0)
#             continue
#
#         if i == 0:
#             lag1, lag2, lag7 = last_known
#         else:
#             lag1 = cuft_preds[-1]
#             lag2 = lag1 if i == 1 else cuft_preds[-2]
#             lag7 = lag1 if i < 7 else cuft_preds[i - 7]
#
#         # 如果是周一且 lag7 为 0，尝试往历史的真实值中找周一
#         if future_df.loc[i, 'dayofweek'] == 0 and lag7 == 0:
#             prev_mondays = daily_df[daily_df['dayofweek'] == 0].sort_values(by='Invoice Date', ascending=False)
#             for _, row in prev_mondays.iterrows():
#                 val = row['Total Cuft']
#                 if val > 0:
#                     lag7 = val
#                     print(f"📌 替换周一 lag7: 使用历史周一 {row['Invoice Date']} 的值 {val}")
#                     break
#
#         features = pd.DataFrame([{
#             'dayofweek': future_df.loc[i, 'dayofweek'],
#             'day': future_df.loc[i, 'day'],
#             'month': future_df.loc[i, 'month'],
#             'lag1': lag1,
#             'lag2': lag2,
#             'lag7': lag7
#         }])
#
#         if future_df.loc[i, 'dayofweek'] == 0:
#             print(f"🔍 第 {i} 天（{future_df.loc[i, 'Date']}，周一）的预测输入：", features.to_dict('records')[0])
#
#         cuft_pred = rf_cuft.predict(features)[0]
#         sales_pred = rf_sales.predict(features)[0]
#         cost_pred = rf_cost.predict(features)[0]
#
#         cuft_preds.append(cuft_pred)
#         sales_preds.append(sales_pred)
#         cost_preds.append(cost_pred)
#
#     future_df['Total Cuft Prediction'] = cuft_preds
#     future_df['Containers Forecast'] = (future_df['Total Cuft Prediction'] / 2350).round(1)
#
#     future_df['Sales Prediction'] = sales_preds
#     future_df['Cost Prediction'] = cost_preds
#     future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
#     future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std
#
#     # 加入 APO 数据
#     incoming_df['Date'] = pd.to_datetime(incoming_df['Date'])
#     future_df = future_df.merge(incoming_df, on='Date', how='left')
#     future_df['APO'] = future_df['APO'].fillna(0)
#
#     container_list = []
#     for _, row in future_df.iterrows():
#         sold = row['Total Cuft Prediction'] / 2350
#         container = container - sold + row['APO']
#         container_list.append(container)
#     future_df['container'] = container_list
#
#     container_std = residual_std / 2350
#     future_df['lower_bound'] = future_df['container'] - z_score * container_std
#     future_df['upper_bound'] = future_df['container'] + z_score * container_std
#
#     future_df[['container', 'lower_bound', 'upper_bound']] = future_df[['container', 'lower_bound', 'upper_bound']].round(2)
#     future_df[['Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction']] = \
#         future_df[['Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction']].round(0).astype(int)
#     static_dir = os.path.join(base_dir, 'static')
#
#     # 👉 先处理所有预测列
#     for col in ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']:
#         # 将今天是假期的值，转移到下一天
#         future_df[col] = future_df[col] + future_df[col].shift(1).where(future_df['is_holiday'] == 1, 0)
#
#     # 👉 再将假期当天置 0
#     future_df.loc[future_df['is_holiday'] == 1, ['Total Cuft Prediction', 'Sales Prediction', 'Cost Prediction']] = 0
#
#     # 当前时间 & 月份范围
#     today = pd.Timestamp.today().normalize()
#     month_start = today.replace(day=1)
#     month_end = (month_start + pd.offsets.MonthEnd(0))  # 当前月最后一天
#
#     # 📌 Step 1: 真实数据部分（来自 df）
#     df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
#     real_df = df[(df['Invoice Date'] >= month_start) & (df['Invoice Date'] <= today)]
#     real_grouped = real_df.groupby('Invoice Date').agg({
#         'Sales': 'sum',
#         'Cost': 'sum',
#         'Total Cuft': 'sum'
#     }).reset_index()
#
#     # 📌 Step 2: 预测数据部分（来自 future_df）
#     future_part = future_df[(future_df['Date'] > today) & (future_df['Date'] <= month_end)]
#
#     # 📌 Step 3: 合并，考虑今天销售数据是否缺失
#     today = pd.Timestamp.today().normalize()
#     real_past = real_grouped[real_grouped['Invoice Date'] < today]
#
#     # ✅ 不再使用 real_today，始终使用预测值
#     future_today = future_df[future_df['Date'] == today]
#     today_sales = future_today['Sales Prediction'].values[0] if not future_today.empty else 0
#     today_cost = future_today['Cost Prediction'].values[0] if not future_today.empty else 0
#     today_cuft = future_today['Total Cuft Prediction'].values[0] if not future_today.empty else 0
#
#     monthly_sales = int(real_past['Sales'].sum() + today_sales + future_part['Sales Prediction'].sum())
#     monthly_cost = int(real_past['Cost'].sum() + today_cost + future_part['Cost Prediction'].sum())
#     monthly_cuft = int(real_past['Total Cuft'].sum() + today_cuft + future_part['Total Cuft Prediction'].sum())
#
#     # 图表文件按天数命名，避免重复生成
#     container_chart_path = os.path.join(static_dir, f'forecast/container_forecast_{days}_{warehouse}.html')
#     sales_cost_chart_path = os.path.join(static_dir, f'forecast/sales_cost_forecast_{days}_{warehouse}.html')
#
#     # 添加 Total 行到 forecast_df 的底部
#     total_row = {
#         'Date': 'Total',
#         'container': '',
#         'lower_bound': '',
#         'upper_bound': '',
#         'Sales Prediction': int(future_df['Sales Prediction'].sum()),
#         'Cost Prediction': int(future_df['Cost Prediction'].sum()),
#         'Total Cuft Prediction': int(future_df['Total Cuft Prediction'].sum()),
#         'Containers Forecast': round(future_df['Containers Forecast'].sum(), 1)  # ✅ 新增这行
#     }
#
#     forecast_with_total = pd.concat([future_df, pd.DataFrame([total_row])], ignore_index=True)
#
#     if force or not os.path.exists(container_chart_path):
#         print(f"📈 生成 container_forecast_{days}_NJ.html")
#         fig1 = go.Figure()
#         fig1.add_trace(go.Scatter(x=future_df['Date'], y=future_df['container'], mode='lines', name='Container', line=dict(color='royalblue')))
#         fig1.add_trace(go.Scatter(
#             x=pd.concat([future_df['Date'], future_df['Date'][::-1]]),
#             y=pd.concat([future_df['upper_bound'], future_df['lower_bound'][::-1]]),
#             fill='toself', fillcolor='rgba(135, 206, 250, 0.3)',
#             line=dict(color='rgba(255,255,255,0)'), hoverinfo="skip", showlegend=True, name='Forecast Range'
#         ))
#         fig1.update_layout(
#             title={'text': f'{days}-Day Container Forecast', 'x': 0.5, 'xanchor': 'center'},
#             xaxis_title='Date',
#             yaxis_title='Container',
#             template='plotly_white',
#             legend=dict(
#                 orientation='h',
#                 yanchor='top',
#                 y=1,
#                 xanchor='left',
#                 x=0
#             ),
#             margin=dict(l=20, r=20, t=30, b=20)
#         )
#
#         fig1.write_html(container_chart_path, config={
#         'modeBarButtonsToRemove': [
#             'zoom2d', 'pan2d', 'select2d', 'lasso2d',
#             'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
#             'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'
#         ],
#         'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'toImage'],
#         'displaylogo': False
#     })
#     else:
#         print(f"✅ 已存在 container_forecast_{days}_NJ.html")
#
#     if force or not os.path.exists(sales_cost_chart_path):
#         print(f"📈 生成 sales_cost_forecast_{days}_NJ.html")
#         fig2 = go.Figure()
#         fig2.add_trace(go.Scatter(x=future_df['Date'], y=future_df['Sales Prediction'], mode='lines', name='Sales', line=dict(color='green')))
#         fig2.add_trace(go.Scatter(x=future_df['Date'], y=future_df['Cost Prediction'], mode='lines', name='Cost', line=dict(color='orange')))
#         fig2.update_layout(
#             title={'text': f'{days}-Day Sales & Cost Forecast', 'x': 0.5, 'xanchor': 'center'},
#             xaxis_title='Date',
#             yaxis_title='Value',
#             template='plotly_white',
#             legend=dict(
#                 orientation='h',
#                 yanchor='top',
#                 y=1,
#                 xanchor='left',
#                 x=0
#             ),
#             margin=dict(l=20, r=20, t=30, b=20)
#         )
#
#         fig2.write_html(sales_cost_chart_path, config={
#         'modeBarButtonsToRemove': [
#             'zoom2d', 'pan2d', 'select2d', 'lasso2d',
#             'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
#             'toggleSpikelines', 'hoverClosestCartesian', 'hoverCompareCartesian'
#         ],
#         'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'toImage'],
#         'displaylogo': False
#     })
#     else:
#         print(f"✅ 已存在 sales_cost_forecast_{days}_{warehouse}.html")
#         print("✅ 文件路径：", base_dir)
#         print("✅ 模型文件路径：", os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'))
#         print("✅ 数据文件夹是否存在：", os.path.exists(base_dir))
#         print("✅ 模型是否存在：", os.path.exists(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl')))
#         print(f"✅ 预测结果 dataframe 行数：{len(df)}")
#
#         # 🧾 销售数据分析
#         df['Invoice Date'] = pd.to_datetime(df['Invoice Date'])
#         df['dayofweek'] = df['Invoice Date'].dt.dayofweek
#         print("📊 各星期平均销量（Total Cuft）:")
#         print(df.groupby('dayofweek')['Total Cuft'].mean())
#
#         # 🕵️ 最近几个周一的数据
#         print("📅 最近 5 个周一的数据：")
#         print(daily_df[daily_df['Invoice Date'].dt.weekday == 0].tail(5))
#
#         # 🧮 lags 值
#         print("📌 Last known values for lags:", last_known)
#
#         # 📆 节假日相关信息（确保在 future_df['is_holiday'] 赋值之后）
#         print("🟠 节假日 future_holidays 列表：", [d.strftime('%Y-%m-%d') for d in future_holidays])
#         print("🟢 future_df 中 is_holiday == 1 的日期：",
#               future_df[future_df['is_holiday'] == 1]['Date'].dt.strftime('%Y-%m-%d').tolist())
#
#         # 🔎 数据类型核查
#         print("📌 future_df['Date'] sample:", future_df['Date'].head())
#         print("📌 future_holidays sample:", future_holidays[:5])
#         print("📎 类型对比：", type(future_df['Date'].iloc[0]), type(future_holidays[0]))
#         print("📎 future_df['Date'] dtype:", future_df['Date'].dtype)
#         print("📎 future_holidays dtype:", pd.Series(future_holidays).dtype)
#
#         print("🧪 future_df 中的周一行（dayofweek == 0）:")
#         print(future_df[future_df['dayofweek'] == 0][['Date', 'dayofweek', 'is_holiday']])
#         print("📌 周一中 is_holiday == 1 的行：")
#         print(future_df[(future_df['dayofweek'] == 0) & (future_df['is_holiday'] == 1)])
#         print("📌 周一的预测前后值变化：")
#         print(future_df[['Date', 'dayofweek', 'is_holiday', 'Total Cuft Prediction']].head(10))
#
#         print(f"🔍 第 {i} 天（{future_df.loc[i, 'Date']}）的预测输入：", features.to_dict('records')[0])
#         print(f"🎯 模型输出：{cuft_pred}")
#
#     return {
#     'forecast_df': forecast_with_total[
#         ['Date', 'container', 'lower_bound', 'upper_bound', 'Sales Prediction', 'Cost Prediction', 'Total Cuft Prediction', 'Containers Forecast']
#     ],
#         'monthly_summary': {
#             'sales': monthly_sales,
#             'cost': monthly_cost,
#             'cuft': monthly_cuft
#         }
#     }

def generate_predictions(future_df, daily_df, rf_cuft, rf_sales, rf_cost, last_known):
    """
    根据未来日期、历史数据和训练模型，生成未来 cuft/sales/cost 的预测。
    """
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

        # 如果是周一且 lag7 为 0，尝试往历史的真实值中找周一
        if future_df.loc[i, 'dayofweek'] == 0 and lag7 == 0:
            prev_mondays = daily_df[daily_df['dayofweek'] == 0].sort_values(by='Invoice Date', ascending=False)
            for _, row in prev_mondays.iterrows():
                val = row['Total Cuft']
                if val > 0:
                    lag7 = val
                    print(f"📌 替换周一 lag7: 使用历史周一 {row['Invoice Date']} 的值 {val}")
                    break

        features = pd.DataFrame([{
            'dayofweek': future_df.loc[i, 'dayofweek'],
            'day': future_df.loc[i, 'day'],
            'month': future_df.loc[i, 'month'],
            'lag1': lag1,
            'lag2': lag2,
            'lag7': lag7
        }])

        if future_df.loc[i, 'dayofweek'] == 0:
            print(f"🔍 第 {i} 天（{future_df.loc[i, 'Date']}，周一）的预测输入：", features.to_dict('records')[0])

        cuft_pred = rf_cuft.predict(features)[0]
        sales_pred = rf_sales.predict(features)[0]
        cost_pred = rf_cost.predict(features)[0]

        cuft_preds.append(cuft_pred)
        sales_preds.append(sales_pred)
        cost_preds.append(cost_pred)

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
    import pickle
    from db_utils import query_to_dataframe
    from gauge_plot import get_current_container
    from train_scriptl import get_company_holidays

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

    daily_df = daily_df.set_index('Invoice Date').asfreq('D').fillna(0).reset_index()
    daily_df['dayofweek'] = daily_df['Invoice Date'].dt.dayofweek
    daily_df['day'] = daily_df['Invoice Date'].dt.day
    daily_df['month'] = daily_df['Invoice Date'].dt.month
    daily_df['lag1'] = daily_df['Total Cuft'].shift(1).fillna(0)
    daily_df['lag2'] = daily_df['Total Cuft'].shift(2).fillna(0)
    daily_df['lag7'] = daily_df['Total Cuft'].shift(7).fillna(0)

    X = daily_df[['dayofweek', 'day', 'month', 'lag1', 'lag2', 'lag7']]
    y_cuft = daily_df['Total Cuft']

    rf_cuft = pickle.load(open(os.path.join(base_dir, f'rf_model_cuft_{warehouse}.pkl'), 'rb'))
    rf_sales = pickle.load(open(os.path.join(base_dir, f'rf_model_sales_{warehouse}.pkl'), 'rb'))
    rf_cost = pickle.load(open(os.path.join(base_dir, f'rf_model_cost_{warehouse}.pkl'), 'rb'))

    residual_std = (y_cuft - rf_cuft.predict(X)).std()
    z_score = 1.28

    forecast_dates = pd.date_range(start=pd.Timestamp.today().normalize(), periods=days, freq='D')
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

    last_known = daily_df.iloc[-1][['lag1', 'lag2', 'lag7']].values.tolist()
    cuft_preds, sales_preds, cost_preds = generate_predictions(future_df, daily_df, rf_cuft, rf_sales, rf_cost, last_known)

    future_df['Total Cuft Prediction'] = cuft_preds
    future_df['Containers Forecast'] = (future_df['Total Cuft Prediction'] / 2350).round(2)
    future_df['Sales Prediction'] = sales_preds
    future_df['Cost Prediction'] = cost_preds

    future_df = adjust_for_holidays(future_df, residual_std)

    future_df['lower'] = future_df['Total Cuft Prediction'] - z_score * residual_std
    future_df['upper'] = future_df['Total Cuft Prediction'] + z_score * residual_std

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

    static_dir = os.path.join(base_dir, 'static')
    # 保留 future_df 中用于作图的字段两位小数
    future_df[['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']] = future_df[
        ['container', 'lower_bound', 'upper_bound', 'Total Cuft Prediction', 'Containers Forecast']].round(2)
    forecast_with_total = generate_forecast_charts(future_df, static_dir, days, warehouse, force)

    monthly_summary = calculate_monthly_summary(df, future_df)

    return {
        'forecast_df': forecast_with_total,
        'monthly_summary': monthly_summary
    }