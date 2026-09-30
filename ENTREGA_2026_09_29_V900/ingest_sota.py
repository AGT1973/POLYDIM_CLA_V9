import sqlite3
import json
from datetime import datetime

db_path = r"E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

timestamp = datetime.utcnow().isoformat()

# Insert SOTA Findings into novelties
novelties = [
    (
        "SABUESO_1_HPC",
        "benchmark",
        "OpenURMA / sparrow-ipc / HBM3",
        "Implementar alineación SIMD estricta de 64-bytes en C++/Rust (align(64)) para tensores PMTP y SeqLocks. Evitar 'line straddling' para no saturar memoria DDR3/HBM3. Zero-Copy consolidado sin serializadores pesados.",
        json.dumps(["PMTP", "HPC", "SIMD", "Zero-Copy"])
    ),
    (
        "SABUESO_2_MATH",
        "teoria",
        "Stiefel-AdamW / arXiv Math",
        "Reemplazo de inversión matricial O(D^3) por fórmula Sherman-Morrison-Woodbury (SMW) O(DK^2) para Retracción Cayley en St(D,K). Uso mandatorio de función Log-Cosh como freno espectral asintótico para estabilizar gradientes en D>10^6.",
        json.dumps(["Stiefel", "SMW", "Geometría Diferencial", "Freno Espectral"])
    ),
    (
        "SABUESO_3_DL",
        "teoria",
        "ICLR 2026 / cs.LG",
        "Tokenización impone Cuello de Botella de Información (IB) estricto (pérdida DPI). Riesgo de singularidad en estimador Two-NN (curvatura plana ilusoria) violando cota Baraniuk-Wakin. Requerido watchdog en runtime para abortar (Exit Code 1) si k viola la cota.",
        json.dumps(["Information Bottleneck", "Two-NN", "Baraniuk-Wakin", "Topología"])
    ),
    (
        "SABUESO_4_CODE",
        "code_change",
        "Triton / vLLM / CUDA",
        "Eliminar `std::shared_ptr` en PMTP. Implementar barreras QSBR explícitas en FFI C++ para lifecycle de tensores S^{D-1}. Implementar kernels fusionados tipo Triton para Productos Geométricos Cl(D) Bivectoriales nativos en Rust/C++.",
        json.dumps(["QSBR", "FFI", "Clifford Algebra", "Kernel Fusion"])
    ),
    (
        "SABUESO_5_OPENREVIEW",
        "optimizacion",
        "NeurIPS 2026 / OpenReview",
        "Reemplazar Newton-Schulz O(N^2) puro por Hybrid-AuON (escalado hiperbólico RMS) en S^{D-1}. Acoplar métricas FIRE (Frobenius-Isometry Reinitialization) en daemons multihop. Usar Homología Persistente (Betti-1) como métrica determinista contra el Gusano 1D.",
        json.dumps(["AuON Híbrido", "FIRE", "Homología Persistente", "Gusano 1D"])
    )
]

cursor.executemany('''
    INSERT INTO novelties (agent_id, ntype, path, summary, topics, absorbed, inserted_at)
    VALUES (?, ?, ?, ?, ?, 0, ?)
''', [(n[0], n[1], n[2], n[3], n[4], timestamp) for n in novelties])

conn.commit()
print(f"Insertadas {len(novelties)} novedades SOTA en la Base de Datos Vectorial.")
conn.close()
