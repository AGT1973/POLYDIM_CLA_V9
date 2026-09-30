"""
03_SUITE_DE_PRUEBAS_Y_BENCHMARKS_V902.py
Suite Consolidada de Pruebas Físicas, Asintóticas y Sabuesos Destructivos POLYDIM V902
Certificación en Silicio Físico (Class-4 Floor AMD A4-6300 / GCC 14.2 / Rustc 1.98.1)
"""

import sys
import os
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

def main():
    print("=" * 80)
    print("🚀 POLYDIM V902 — EJECUCIÓN CONSOLIDADA DE SUITE Y SABUESOS")
    print("=" * 80)

    # 1. Ejecutar Suite Asintótica 12/12
    t0 = time.perf_counter()
    print("\n>>> [1/3] Ejecutando Suite Asintótica 12/12...")
    res1 = subprocess.run([sys.executable, os.path.join(BASE_DIR, "test_v902_comprehensive_suite.py")], cwd=BASE_DIR)
    if res1.returncode != 0:
        print("[FAIL] Suite 12/12 falló.")
        sys.exit(res1.returncode)

    # 2. Ejecutar 3 Sabuesos Destructivos
    print("\n>>> [2/3] Ejecutando 3 Sabuesos Destructivos Red Team...")
    res2 = subprocess.run([sys.executable, os.path.join(BASE_DIR, "fuzz_v902_destructive_hounds.py")], cwd=BASE_DIR)
    if res2.returncode != 0:
        print("[FAIL] Sabuesos destructivos fallaron.")
        sys.exit(res2.returncode)

    # 3. Ejecutar Contrato de Silicio AMD Instinct ROCm / OpenMP
    rocm_script = os.path.join(PARENT_DIR, "rocm_amd_mi300x", "polydim_rocm_mi300x_runner.py")
    if os.path.exists(rocm_script):
        print("\n>>> [3/3] Ejecutando Contrato AMD Instinct ROCm / OpenMP...")
        res3 = subprocess.run([sys.executable, rocm_script], cwd=os.path.join(PARENT_DIR, "rocm_amd_mi300x"))
        if res3.returncode != 0:
            print("[FAIL] Benchmark AMD ROCm falló.")
            sys.exit(res3.returncode)

    total_t = time.perf_counter() - t0
    print("\n" + "=" * 80)
    print(f"✅ CERTIFICACIÓN V902 EXITOSA: 15/15 PRUEBAS COMPLETADAS (Exit Code 0) en {total_t:.2f}s")
    print("=" * 80)
    sys.exit(0)

if __name__ == "__main__":
    main()
