from db_utils import query_to_dataframe

print("✅ 正在测试数据库连接...\n")

# 🔍 显示当前数据库名和默认 schema
try:
    db_info = query_to_dataframe("SELECT current_database() AS db, current_schema() AS schema;")
    print("📌 当前连接信息：")
    print(db_info)
except Exception as e:
    print("❌ 数据库连接失败（current_database 查询出错）：", e)

# 🔍 显示可用的表和 schema
try:
    tables_df = query_to_dataframe("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name;
    """)
    print("\n📋 可访问的 schema 和表：")
    print(tables_df)
except Exception as e:
    print("❌ 无法列出表结构：", e)
