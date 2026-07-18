import sqlite3
conn = sqlite3.connect(r'C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\data\quote.db')
cur = conn.cursor()

print('=== quotes 表结构 ===')
for row in cur.execute('PRAGMA table_info(quotes)'):
    print(' ', row[1], row[2])

print()
print('=== 报价记录数 ===')
cur.execute('SELECT COUNT(*), source FROM quotes GROUP BY source')
for r in cur.fetchall():
    print(' ', r)

print()
print('=== 最新 1 条 ml_features + total ===')
cur.execute('SELECT ml_features_json, total_amount, source FROM quotes ORDER BY id DESC LIMIT 1')
r = cur.fetchone()
if r:
    print(' source:', r[2])
    print(' total_amount:', r[1])
    print(' ml_features:', r[0][:300] if r[0] else '(空)')
else:
    print(' (无记录!)')
conn.close()
