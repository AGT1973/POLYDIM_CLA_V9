import sqlite3
import json
from datetime import datetime

db_path = r'E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite'
conn = sqlite3.connect(db_path)
c = conn.cursor()

ts = datetime.utcnow().isoformat()

c.execute('''
    INSERT INTO novelties (agent_id, ntype, path, summary, topics, absorbed, inserted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
''', ('ANTIGRAVITY_NODE', 'log', 'E:\\POLYDIM_EINSOF\\ENTREGA_2026_09_29_V902\\V902_Context_Checkpoint.md', 'Regla 13: Colapso de contexto. QSBR y Hybrid-AuON (50/50 exitosas) implementados. Pendiente: alignas(64), Watchdog BW, FIRE y Clifford.', json.dumps(["checkpoint", "v902", "regla13"]), 0, ts))

c.execute('''
    INSERT INTO collapse_log (docx_path, chapters_n, facts_n, novelties_n, collapsed_at)
    VALUES (?, ?, ?, ?, ?)
''', ('V902_Context_Checkpoint.md', 0, 0, 1, ts))

conn.commit()
conn.close()
