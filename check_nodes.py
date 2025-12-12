import sqlite3
conn = sqlite3.connect('gateway_meta.db')
cur = conn.cursor()
cur.execute('SELECT * FROM nodes')
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
