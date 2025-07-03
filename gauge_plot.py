import matplotlib
matplotlib.use('Agg')  # ✅ 使用非交互式后端，适合服务器/脚本

import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
import numpy as np
import os
from db_utils import query_to_dataframe

def get_current_container(warehouse: str = 'NJ'):
    if warehouse == 'NJ':
        sql = """
        SELECT total / 2350 AS container FROM bi.v_inventory_total;
        """
    elif warehouse == 'HMLG':
        # 未来支持 HMLG 时，替换为正确的 SQL 或视图
        sql = """
        SELECT total / 2350 AS container FROM bi.v_inventory_total;
        """
    else:
        raise ValueError(f"Unsupported warehouse: {warehouse}")

    df = query_to_dataframe(sql)
    if df.empty:
        return 0
    return round(df.iloc[0]['container'], 2)


def plot_half_gauge(value, min_val, max_val, title, save_path):
    fig, ax = plt.subplots(figsize=(4, 2.2))  # 🔧 适配你网页的比例
    ax.axis('equal')

    ax.set_facecolor('#f8f9fa')  # 🔧 和页面一致的灰白底色

    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.2, 1.2)

    ax.axis('off')

    low_end = 180 - (159 - min_val) / (max_val - min_val) * 180
    med_end = 180 - (190 - min_val) / (max_val - min_val) * 180

    sectors = [
        (180, low_end, '#fdd835'),
        (low_end, med_end, '#43a047'),
        (med_end, 0, '#e53935')
    ]

    inner_radius = 0.6
    outer_radius = 1.0

    for start, end, color in sectors:
        wedge = Wedge(center=(0,0), r=outer_radius, theta1=end, theta2=start,
                       width=outer_radius-inner_radius, facecolor=color,
                       edgecolor='white', lw=2)
        ax.add_patch(wedge)

    ax.text(1.1, 0.15, 'High\n191 - 220', ha='center', va='center', fontsize=9, fontweight='bold', color='#555555')
    ax.text(0.95, 0.6, 'Medium\n160 - 190', ha='center', va='center', fontsize=9, fontweight='bold', color='#555555')
    ax.text(-0.3, 0.6, 'Low\n<160', ha='center', va='center', fontsize=9, fontweight='bold', color='#555555')

    angle_deg = 180 - (value - min_val) / (max_val - min_val) * 180
    angle_rad = np.radians(angle_deg)

    x_end = outer_radius * np.cos(angle_rad)
    y_end = outer_radius * np.sin(angle_rad)

    ax.annotate('', xy=(x_end, y_end), xytext=(0, 0),
                 arrowprops=dict(facecolor='#1e88e5', edgecolor='#1e88e5', arrowstyle='-|>', lw=2))

    ax.text(0, -0.05, f'{value}', ha='center', va='center', fontsize=12, fontweight='bold', color='#333333')

    ax.set_title(title, fontsize=12, fontweight='bold', color='#333333', pad=2)

    fig.patch.set_facecolor('#eef2f7')
    ax.set_facecolor('#eef2f7')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight', transparent=False)
    plt.close()

# 直接保存图像文件
if __name__ == '__main__':
    container = get_current_container()
    min_val = 0
    max_val = 220
    title = 'Inventory Level (Containers)'
    output_path = os.path.join('static', 'gauge.png')  # 🔧 你网页里引用的路径
    plot_half_gauge(container, min_val, max_val, title, output_path)
