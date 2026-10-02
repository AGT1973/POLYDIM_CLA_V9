# ============================================================================
# 03. SUITE DE PRUEBAS Y BENCHMARKS — POLYDIM V1000 (HITO 100)
# ============================================================================

import sys
import os
import time
import subprocess

_DIR = os.path.dirname(os.path.abspath(__file__))
UNIT_TESTS = os.path.join(_DIR, "test_v1000_comprehensive_suite.py")
FUZZ_TESTS = os.path.join(_DIR, "fuzz_v1000_destructive_hounds.py")

def main():
    print("=" * 80)
    print("🏛️  POLYDIM V1000 — SUITE DE PRUEBAS Y BENCHMARKS EN SILICIO LOCAL")
    print("=" * 80)

    # 1. Unit tests
    print("\n>>> Ejecutando Suite de Pruebas Unitarias e Invariantes...")
    t0 = time.perf_counter()
    r1 = subprocess.run([sys.executable, UNIT_TESTS], capture_output=True, text=True)
    dt1 = time.perf_counter() - t0
    if r1.returncode != 0:
        print(f"[FAIL] Unit tests failed:\n{r1.stderr}")
        sys.exit(r1.returncode)
    print(f"✅ PASS: 10/10 Tests aprobados en {dt1:.3f}s\n{r1.stdout.strip() or r1.stderr.strip()}")

    # 2. Fuzz hounds
    print("\n>>> Ejecutando Batería de 4 Sabuesos Destructivos Red Team...")
    t0 = time.perf_counter()
    r2 = subprocess.run([sys.executable, FUZZ_TESTS], capture_output=True, text=True)
    dt2 = time.perf_counter() - t0
    if r2.returncode != 0:
        print(f"[FAIL] Fuzz hounds failed:\n{r2.stderr}")
        sys.exit(r2.returncode)
    print(f"✅ PASS: 4/4 Sabuesos aprobados en {dt2:.3f}s\n{r2.stdout.strip() or r2.stderr.strip()}")

    print("\n" + "=" * 80)
    print(f"🏆 CERTIFICACIÓN FÍSICA EXITOSA — EXIT CODE 0 (Tiempo Total: {dt1+dt2:.3f}s)")
    print("=" * 80)

if __name__ == "__main__":
    main()
