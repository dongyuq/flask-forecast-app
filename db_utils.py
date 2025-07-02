import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

# 加载 .env 文件中的数据库配置（可选）
load_dotenv()

# 获取连接信息（从环境变量中读取，避免硬编码）
DB_CONFIG = {
    'host': 'nj.homelegance.com',
    'port': 5437,
    'user': 'njhmlg_bi',
    'password': 'NJ53cd**',
    'database': 'njhmlg_database'
}


def get_postgres_connection():
    """建立并返回一个 PostgreSQL 数据库连接。"""
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database']
    )


def query_to_dataframe(query: str, params=None) -> pd.DataFrame:
    """执行 SQL 查询并返回 Pandas DataFrame。"""
    conn = get_postgres_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()
    return df

