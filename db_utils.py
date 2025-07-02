import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# 数据库连接信息
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

# 创建 Engine
engine: Engine = create_engine(DATABASE_URL, echo=False)


def query_to_dataframe(query: str, params=None) -> pd.DataFrame:
    """
    安全执行 SQL 查询，兼容本地和 Render 上可能传入的 immutabledict 类型参数
    """
    from sqlalchemy.util._collections import immutabledict

    with engine.connect() as connection:
        # 👇 强制将 immutabledict 转为普通 dict
        if isinstance(params, immutabledict):
            params = dict(params)
        elif not isinstance(params, (dict, type(None))):
            params = None

        df = pd.read_sql_query(sql=text(query), con=connection, params=params)
    return df
