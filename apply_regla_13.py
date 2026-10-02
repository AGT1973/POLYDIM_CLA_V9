import sqlite3
import datetime
import os

db_path = r'E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite'
timestamp = datetime.datetime.now().isoformat()

summary_v900 = """[REGLA 13 STATE SNAPSHOT - 2026-10-01 SERIE 900 V990]
- Repositorio Oficial Git: https://github.com/AGT1973/POLYDIM_CLA_V9.git (origin -> V9)
- Directorio de Entrega Activo: E:\\POLYDIM_EINSOF\\ENTREGA_2026_10_01_V990\\
- Archivos Base V990 Generados:
  * kernel_cpp_v990.cpp (+ .cpp.txt, .dll)
  * kernel_rust_v990.rs (+ .rs.txt, .dll)
  * polydim_v990_monolito.py
  * polydim_triton_kernel_v990.py
  * readme_first.md
  * build_and_test_v990.py
  * auditoria_externa\\test_v990_comprehensive_suite.py
  * auditoria_externa\\fuzz_v990_destructive_hounds.py
- Remotes configurados en E:\\POLYDIM_EINSOF:
  * origin -> https://github.com/AGT1973/POLYDIM_CLA_V9.git
  * origin_v9 -> https://github.com/AGT1973/POLYDIM_CLA_V9.git
  * origin_v8 -> https://github.com/AGT1973/POLYDIM_CLA_V8.git
  * origin_v7 -> https://github.com/AGT1973/POLYDIM_CLA_V7.git
- Estado: Listo para compilacion de certificacion V990 en silicio AMD A4 y ejecucion de tests."""

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO facts (fact_type, topic, detail, certified, inserted_at) VALUES (?, ?, ?, ?, ?)",
                ("REGLA_13_V990", "SERIE_900_V990_STATE", summary_v900, 1, timestamp))
    conn.commit()
    conn.close()
    print("Snapshot V990 guardado en SQLite con exito.")
else:
    print("DB no encontrada.")
