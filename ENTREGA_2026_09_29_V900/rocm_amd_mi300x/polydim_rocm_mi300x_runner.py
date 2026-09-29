#!/usr/bin/env python3
# ==============================================================================
# POLYDIM V900 — AMD INSTINCT MI300X / MI325X AUTOMATED BENCHMARK RUNNER
# Autonómicamente detecta entorno AMD ROCm (hipcc) o fallback local (g++)
# Ejecuta validaciones asintóticas D = [10^4, 10^5, 10^6, 10^7]
# ==============================================================================

import os
import sys
import subprocess
import time
import json
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_SRC = os.path.join(BASE_DIR, "polydim_rocm_mi300x_benchmark.cpp")
OUTPUT_BIN = os.path.join(BASE_DIR, "polydim_rocm_bench.exe" if sys.platform == "win32" else "polydim_rocm_bench")
LOG_FILE = os.path.join(BASE_DIR, "amd_mi300x_benchmark_raw_log.txt")

def detect_compiler():
    # 1. Check for hipcc (ROCm Linux)
    hipcc_path = shutil.which("hipcc")
    if hipcc_path:
        return "hipcc", [hipcc_path, "-O3", "--offload-arch=gfx940,gfx942", CPP_SRC, "-o", OUTPUT_BIN]
    
    # 2. Check for local WinLibs GCC
    winlibs_gcc = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
    if os.path.exists(winlibs_gcc):
        return "g++_winlibs", [winlibs_gcc, "-O3", "-std=c++20", "-fopenmp", CPP_SRC, "-o", OUTPUT_BIN]
    
    # 3. System g++
    gpp_path = shutil.which("g++")
    if gpp_path:
        return "g++_system", [gpp_path, "-O3", "-std=c++20", "-fopenmp", CPP_SRC, "-o", OUTPUT_BIN]
    
    return None, []

def main():
    print("=" * 70)
    print("🚀 POLYDIM V900 — AMD INSTINCT MI300X/MI325X BENCHMARK RUNNER")
    print("=" * 70)
    
    compiler_type, build_cmd = detect_compiler()
    if not compiler_type:
        print("[ERROR] No se encontró ningún compilador (hipcc / g++) disponible.")
        sys.exit(1)
        
    print(f"[COMPILER] Tipo detectado: {compiler_type}")
    print(f"[BUILD COMMAND] {' '.join(build_cmd)}")
    
    build_res = subprocess.run(build_cmd, capture_output=True, text=True)
    if build_res.returncode != 0:
        print(f"[ERROR DE COMPILACIÓN]\n{build_res.stderr}")
        sys.exit(build_res.returncode)
        
    print("✅ Compilación exitosa (Exit Code 0).")
    print(f"[EXECUTING] {OUTPUT_BIN}")
    
    # Run test sweeps
    test_dims = [10000, 100000, 1000000, 10000000]
    all_logs = []
    
    for d in test_dims:
        print(f"\n>>> Ejecutando benchmark para D = {d:,}...")
        cmd = [OUTPUT_BIN, str(d), "16"]
        start_t = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        end_t = time.perf_counter()
        
        output_txt = proc.stdout
        print(output_txt.strip())
        all_logs.append({
            "dimension": d,
            "rank_k": 16,
            "exit_code": proc.returncode,
            "wall_time_s": end_t - start_t,
            "raw_output": output_txt
        })
        
        if proc.returncode != 0:
            print(f"[FAIL] Falló ejecución para D={d}. Stderr: {proc.stderr}")
            sys.exit(proc.returncode)
            
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=================================================================\n")
        f.write("POLYDIM V900 — AMD INSTINCT MI300X/MI325X EMPIRICAL BENCHMARK LOG\n")
        f.write(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Compilador: {compiler_type}\n")
        f.write("=================================================================\n\n")
        for entry in all_logs:
            f.write(f"--- D={entry['dimension']} (Exit Code {entry['exit_code']}) ---\n")
            f.write(entry['raw_output'] + "\n\n")
            
    print(f"\n✅ Todos los benchmarks completados con éxito (Exit Code 0).")
    print(f"📄 Log empírico guardado en: {LOG_FILE}")

if __name__ == "__main__":
    main()
