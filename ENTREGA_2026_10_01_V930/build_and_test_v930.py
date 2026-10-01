"""
BUILD AND TEST SCRIPT - POLYDIM SERIE 900 V930 (HITO DECENAL 20)
Compila kernel C++20 y kernel Rust, y ejecuta suite de tests y sabuesos adversariales.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
CPP_SRC = BASE_DIR / "kernel_cpp_v930.cpp"
CPP_DLL = BASE_DIR / "kernel_cpp_v930.dll"
RUST_SRC = BASE_DIR / "kernel_rust_v930.rs"
RUST_DLL = BASE_DIR / "kernel_rust_v930.dll"

GCC_PATH = Path(r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe")
RUSTC_PATH = Path(r"C:\Users\eluithi\.cargo\bin\rustc.exe")

def compile_cpp():
    print("=" * 70)
    print("1. COMPILANDO KERNEL C++20 V930 CON WINLIBS GCC 14 (CLASE 4 FLOOR)")
    print("=" * 70)
    if not GCC_PATH.exists():
        gcc = "g++"
    else:
        gcc = str(GCC_PATH)
    
    cmd = [
        gcc,
        "-O3",
        "-std=c++20",
        "-shared",
        "-fPIC",
        "-fopenmp",
        "-msse4.2",
        "-mavx",
        str(CPP_SRC),
        "-o",
        str(CPP_DLL)
    ]
    print(f"Comando: {' '.join(cmd)}")
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"❌ ERROR de compilacion C++ (Exit code {res.returncode}):")
        print(res.stderr)
        return False
    print(f"✅ Kernel C++20 compilado con éxito en {dt:.2f}s -> {CPP_DLL.name} ({CPP_DLL.stat().st_size} bytes)")
    return True

def compile_rust():
    print("\n" + "=" * 70)
    print("2. COMPILANDO KERNEL RUST V930 CON RUSTC (OPT-LEVEL=3)")
    print("=" * 70)
    if not RUSTC_PATH.exists():
        rustc = "rustc"
    else:
        rustc = str(RUSTC_PATH)
        
    cmd = [
        rustc,
        "--crate-type",
        "cdylib",
        "-C",
        "opt-level=3",
        "-C",
        "panic=unwind",
        str(RUST_SRC),
        "-o",
        str(RUST_DLL)
    ]
    print(f"Comando: {' '.join(cmd)}")
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"❌ ERROR de compilacion Rust (Exit code {res.returncode}):")
        print(res.stderr)
        return False
    print(f"✅ Kernel Rust compilado con éxito en {dt:.2f}s -> {RUST_DLL.name} ({RUST_DLL.stat().st_size} bytes)")
    return True

def run_tests():
    print("\n" + "=" * 70)
    print("3. EJECUTANDO SUITE COMPLETA DE TESTS V930 (20 TESTS)")
    print("=" * 70)
    test_script = BASE_DIR / "auditoria_externa" / "test_v930_comprehensive_suite.py"
    t0 = time.time()
    res = subprocess.run([sys.executable, str(test_script)], capture_output=False, timeout=60)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"\n❌ FALLA EN SUITE DE TESTS (Exit code {res.returncode})")
        return False
    print(f"\n✅ SUITE DE TESTS V930 APROBADA (Exit Code 0 en {dt:.2f}s)")
    return True

def run_fuzz():
    print("\n" + "=" * 70)
    print("4. EJECUTANDO SABUESOS ADVERSARIALES DESTRUCTIVOS V930 (4 HOUNDS)")
    print("=" * 70)
    fuzz_script = BASE_DIR / "auditoria_externa" / "fuzz_v930_destructive_hounds.py"
    t0 = time.time()
    res = subprocess.run([sys.executable, str(fuzz_script)], capture_output=False, timeout=60)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"\n❌ FALLA EN SABUESOS ADVERSARIALES (Exit code {res.returncode})")
        return False
    print(f"\n✅ SABUESOS ADVERSARIALES V930 SUPERADOS (Exit Code 0 en {dt:.2f}s)")
    return True

if __name__ == "__main__":
    t_start = time.time()
    ok_cpp = compile_cpp()
    ok_rust = compile_rust()
    
    if not (ok_cpp and ok_rust):
        print("\n❌ FALLO EN COMPILACION. ABORTANDO TESTS.")
        sys.exit(1)
        
    ok_test = run_tests()
    ok_fuzz = run_fuzz()
    
    t_total = time.time() - t_start
    print("\n" + "#" * 70)
    if ok_test and ok_fuzz:
        print(f"🎯 CERTIFICACION FISICA V930 EXITOSA (EXIT CODE 0) EN {t_total:.2f}s")
        print("#" * 70)
        sys.exit(0)
    else:
        print(f"❌ CERTIFICACION FISICA V930 FALLIDA EN {t_total:.2f}s")
        print("#" * 70)
        sys.exit(1)
