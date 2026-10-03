"""
vectorizar_bruto_tribunal.py
Vectorizador Tensorial Denso en S^(D-1) (D=3072) para Auditorias del Tribunal Multi-IA V1000
Base de Datos: E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite
Modelo de Embedding: Google gemini-embedding-001 (D=3072)
Invariante: Norma unitaria ||v||_2 = 1.000000 en la hiperesfera S^(D-1)
"""

import sqlite3
import urllib.request
import json
import time
import math
import os
import numpy as np

DB_PATH = r"E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite"

def _load_gemini_key():
    """Carga la API key de Gemini desde env var o archivo .env_paid_keys (Regla 14 Anti-Leak)."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    env_file = os.path.join(os.path.expanduser("~"), ".gemini", "config", ".env_paid_keys")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY no encontrada en env ni en .env_paid_keys")

API_KEY = _load_gemini_key()
MODEL_NAME = "models/gemini-embedding-001"
BATCH_URL = f"https://generativelanguage.googleapis.com/v1beta/{MODEL_NAME}:batchEmbedContents?key={API_KEY}"

def init_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vault_id INTEGER,
        auditor TEXT,
        source_file TEXT,
        chunk_idx INTEGER,
        chunk_text TEXT,
        vector_blob BLOB,
        dim INTEGER,
        norm REAL,
        model_name TEXT,
        created_at REAL,
        FOREIGN KEY(vault_id) REFERENCES audit_ingestion_vault(id)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_embeddings_auditor ON audit_embeddings(auditor);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_embeddings_vault ON audit_embeddings(vault_id);")
    conn.commit()

def chunk_text(text, max_chunk_len=1200, overlap=100):
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        p_str = p.strip()
        if not p_str:
            continue
        p_len = len(p_str)
        if current_len + p_len > max_chunk_len and current_chunk:
            combined = "\n\n".join(current_chunk)
            chunks.append(combined)
            # overlap
            current_chunk = [current_chunk[-1], p_str] if len(current_chunk) > 1 else [p_str]
            current_len = sum(len(x) for x in current_chunk)
        else:
            current_chunk.append(p_str)
            current_len += p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks

def get_embeddings_batch(chunks_batch):
    req_body = {
        "requests": [
            {
                "model": MODEL_NAME,
                "content": {"parts": [{"text": c}]}
            }
            for c in chunks_batch
        ]
    }
    data = json.dumps(req_body).encode("utf-8")
    req = urllib.request.Request(BATCH_URL, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                embeddings = res.get("embeddings", [])
                return [np.array(e["values"], dtype=np.float32) for e in embeddings]
        except Exception as e:
            print(f"  [RETRY {attempt+1}/5] Error in batch embedding: {e}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("Failed to fetch embeddings after 5 attempts.")

def main():
    print("=" * 80)
    print("🚀 INICIANDO VECTORIZACIÓN TENSORIAL DENSA EN S^(D-1) (D=3072)")
    print("   Destino: E:\\POLYDIM-THEORICAL\\POLYDIM_VECDB.sqlite -> audit_embeddings")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    init_table(conn)
    cur = conn.cursor()

    # Obtener los 6 registros del tribunal (ID 24 a 29)
    cur.execute("SELECT id, auditor, source, raw_content FROM audit_ingestion_vault WHERE id >= 24")
    rows = cur.fetchall()

    total_chunks_processed = 0
    start_time = time.perf_counter()

    for vault_id, auditor, source, raw_content in rows:
        print(f"\n▶ Procesando Vault ID {vault_id}: {auditor} ({len(raw_content):,} chars)")
        chunks = chunk_text(raw_content, max_chunk_len=1400, overlap=150)
        print(f"  Total Chunks generados: {len(chunks)}")

        batch_size = 20
        num_batches = (len(chunks) + batch_size - 1) // batch_size

        for b_idx in range(num_batches):
            b_chunks = chunks[b_idx * batch_size : (b_idx + 1) * batch_size]
            vectors = get_embeddings_batch(b_chunks)

            for i, vec in enumerate(vectors):
                chunk_global_idx = b_idx * batch_size + i
                c_text = b_chunks[i]

                # Proyección / normalización estricta a S^(D-1)
                norm_orig = float(np.linalg.norm(vec))
                if norm_orig > 1e-12:
                    vec_normalized = vec / norm_orig
                else:
                    vec_normalized = vec
                norm_final = float(np.linalg.norm(vec_normalized))

                blob = vec_normalized.tobytes()
                dim = len(vec_normalized)

                cur.execute("""
                INSERT INTO audit_embeddings 
                (vault_id, auditor, source_file, chunk_idx, chunk_text, vector_blob, dim, norm, model_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    vault_id, auditor, source, chunk_global_idx, c_text,
                    blob, dim, norm_final, MODEL_NAME, time.time()
                ))

            conn.commit()
            total_chunks_processed += len(b_chunks)
            print(f"  [Batch {b_idx+1}/{num_batches}] Guardados {len(b_chunks)} tensores S^(3071) normalizados.")

    total_t = time.perf_counter() - start_time
    cur.execute("SELECT COUNT(*), AVG(norm), AVG(dim) FROM audit_embeddings")
    count, avg_norm, avg_dim = cur.fetchone()

    print("\n" + "=" * 80)
    print("✅ VECTORIZACIÓN TENSORIAL EN SILICIO COMPLETADA")
    print(f"   Tensores guardados:   {count:,}")
    print(f"   Dimensión latente D:  {int(avg_dim)}")
    print(f"   Norma media en S^D-1: {avg_norm:.6f}")
    print(f"   Tiempo transcurrido:  {total_t:.2f} s")
    print("=" * 80)
    conn.close()

if __name__ == "__main__":
    main()
