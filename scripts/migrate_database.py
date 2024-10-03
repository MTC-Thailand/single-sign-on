import pymysql
from sqlalchemy import create_engine
from pandas import read_sql_query

# src_db = create_engine('postgresql+psycopg2:///mtc_sso')
# dst_db = create_engine('mysql+pymysql://likit@127.0.0.1/testacc2_dbtable?charset=utf8')

dst_db = pymysql.connect(host='127.0.0.1', user='root', database='testacc2_dbtable', password='Intrinity0')

query = 'SELECT * FROM member'
df = read_sql_query(query, con=dst_db)

print(df)

