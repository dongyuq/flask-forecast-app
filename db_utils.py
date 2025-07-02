import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# 直接写数据库连接信息
DB_CONFIG = {
    'host': 'nj.homelegance.com',
    'port': 5437,
    'user': 'njhmlg_bi',
    'password': 'NJ53cd**',
    'database': 'njhmlg_database'
}

# 构造 SQLAlchemy 数据库 URL
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# 创建 SQLAlchemy engine
engine: Engine = create_engine(DATABASE_URL, echo=False)


def query_to_dataframe(query: str, params=None) -> pd.DataFrame:
    from collections.abc import Mapping, Sequence
    with engine.connect() as connection:
        if not (params is None or isinstance(params, (Mapping, Sequence))):
            params = None  # 安全回退
        df = pd.read_sql_query(query, con=connection, params=params)
    return df

