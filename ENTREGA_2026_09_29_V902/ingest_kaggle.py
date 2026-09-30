import sqlite3
from datetime import datetime

db_path = r"E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

timestamp = datetime.utcnow().isoformat()

cursor.execute('''
    INSERT INTO facts (fact_type, source_file, version, topic, metric_key, metric_val, metric_unit, detail, certified, inserted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', ("cert", "kaggle_export/results.json", "V902", "kaggle_t4_gpu", "bandwidth_fp64_max", 70.52, "GB/s", "Rodrigues Geodesic en S^(D-1) (D=10,000,000) en GPU NVIDIA Tesla T4 FP64", 1, timestamp))

cursor.execute('''
    INSERT INTO facts (fact_type, source_file, version, topic, metric_key, metric_val, metric_unit, detail, certified, inserted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', ("cert", "kaggle_export/results.json", "V902", "cholqr2_ortho_error", 4.44e-16, "drift", "Error de Isometría CholQR2 K=32 FP64 en GPU", 1, timestamp))

conn.commit()
conn.close()
