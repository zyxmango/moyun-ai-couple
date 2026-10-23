import sqlite3

conn = sqlite3.connect(r"d:\couple-app-ai\backend\data\couple_app.db")
cur = conn.cursor()

cols = [r[1] for r in cur.execute("PRAGMA table_info(couples)").fetchall()]
print("现有列:", cols)

if "chat_bg" not in cols:
    cur.execute('ALTER TABLE couples ADD COLUMN chat_bg VARCHAR(500) DEFAULT ""')
    conn.commit()
    print("已添加 chat_bg 列")
else:
    print("chat_bg 列已存在")

conn.close()
