import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    password="tiger",
    host="localhost",
    port=5432
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_database WHERE datname='surveyai'")
exists = cur.fetchone()
if not exists:
    cur.execute("CREATE DATABASE surveyai")
    print("Database 'surveyai' created successfully!")
else:
    print("Database 'surveyai' already exists.")

cur.close()
conn.close()
