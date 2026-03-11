import sqlite3
db = sqlite3.connect(r"D:\!DEV\04. Hydroset\5.홍수량산정\rainfall_db.sqlite")
c = db.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", c.fetchall())
# 각 테이블
for t in [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
    print(f"\n=== {t} ===")
    print(db.execute(f"SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0])
    print("Count:", db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
    cur = db.execute(f'SELECT * FROM "{t}" LIMIT 3')
    print([d[0] for d in cur.description])
    for row in cur: print(row)
db.close()