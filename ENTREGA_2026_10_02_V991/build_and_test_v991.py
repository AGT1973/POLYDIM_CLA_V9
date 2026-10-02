# ============================================================================
# POLYDIM V991 SILICON COMPILATION & CERTIFICATION SUITE (LOW-IMPACT APU MODE)
# Optimizado para AMD A4-6300 (1 Hilo de Compilación para no congelar Antigravity/OS)
# ============================================================================

import os
import subprocess
import sys
import time

# Forzar 1 solo hilo en OpenMP y compiladores para preservar el sistema
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["RAYON_NUM_THREADS"] = "1"

_DIR = os.path.dirname(os.path.abspath(__file__))

GCC_PATH = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
RUSTC_PATH = r"C:\Users\eluithi\.cargo\bin\rustc.exe"

CPP_SRC = os.path.join(_DIR, "kernel_cpp_v991.cpp")
CPP_DLL = os.path.join(_DIR, "kernel_cpp_v991.dll")

RUST_SRC = os.path.join(_DIR, "kernel_rust_v991.rs")
RUST_DLL = os.path.join(_DIR, "kernel_rust_v991.dll")

UNIT_TESTS = os.path.join(_DIR, "auditoria_externa", "test_v991_comprehensive_suite.py")
FUZZ_TESTS = os.path.join(_DIR, "auditoria_externa", "fuzz_v991_destructive_hounds.py")

def run_step(name, cmd_args):
    print(f"\n[BUILD-LOW-IMPACT] {name}...")
    t0 = time.time()
    # Timeout estricto de 60s para prevenir deadlocks o cuelgues
    res = subprocess.run(cmd_args, capture_output=True, text=True, timeout=60)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"[FAIL] {name} failed with exit code {res.returncode}:", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        print(res.stdout)
        sys.exit(res.returncode)
    print(f"[OK] {name} passed in {dt:.2f}s")
    if res.stdout.strip():
        print(res.stdout)

def main():
    print("=" * 76)
    print("POLYDIM V991 COMPILATION (LOW-IMPACT MODE - CPU PRESERVED)")
    print("=" * 76)

    # 1. Compile C++ Kernel V991 (1 codegen unit, bajo consumo)
    cpp_cmd = [
        GCC_PATH, "-O2", "-std=c++20", "-shared", "-fopenmp",
        "-mavx", "-msse4.2",
        "-o", CPP_DLL,
        CPP_SRC
    ]
    run_step("Compiling C++20 Kernel V991 (GCC 14 -O2 Low-Load)", cpp_cmd)

    # 2. Compile Rust Kernel V991 (1 codegen unit)
    rust_cmd = [
        RUSTC_PATH, "--crate-type", "cdylib", "-C", "opt-level=2", "-C", "codegen-units=1", "-C", "panic=unwind",
        "-o", RUST_DLL,
        RUST_SRC
    ]
    run_step("Compiling Rust Kernel V991 (rustc 1 codegen-unit)", rust_cmd)

    # 3. Run Unit Tests V991
    run_step("Running V991 Unit Tests", [sys.executable, UNIT_TESTS])

    # 4. Run Fuzz Hounds V991
    run_step("Running V991 Fuzz Hounds", [sys.executable, FUZZ_TESTS])

    print("\n" + "=" * 76)
    print("[SUCCESS] V991 CERTIFIED IN LOW-IMPACT MODE WITHOUT SYSTEM FREEZES")
    print("=" * 76)

if __name__ == "__main__":
    main()
