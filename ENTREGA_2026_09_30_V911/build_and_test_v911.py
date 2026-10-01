# build_and_test_v911.py
# Master Build & Certification Runner - POLYDIM v911
# ============================================================================
import os
import sys
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MINGW_BIN = r"E:\winlibs_gcc14_zip\mingw64\bin"
GPP = os.path.join(MINGW_BIN, "g++.exe")
RUSTC = r"C:\Users\eluithi\.cargo\bin\rustc.exe"
PYTHON = sys.executable

def build_cpp():
    print("=" * 70)
    print("[BUILD] Compiling C++ kernel v911...")
    src = os.path.join(BASE_DIR, "kernel_cpp_v911.cpp")
    dll = os.path.join(BASE_DIR, "polydim_cpp_v911.dll")
    cmd = [
        GPP, src, "-o", dll,
        "-shared", "-O3", "-std=c++20",
        "-fopenmp", "-mavx", "-msse4.2",
        "-Wl,--export-all-symbols"
    ]
    print(f"  CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"C++ compilation failed with exit code {result.returncode}")
    print(f"  -> C++ DLL built: {dll}")

def build_rust():
    print("[BUILD] Compiling Rust kernel v911...")
    src = os.path.join(BASE_DIR, "kernel_rust_v911.rs")
    dll = os.path.join(BASE_DIR, "polydim_rust_v911.dll")
    cmd = [
        RUSTC, src, "-o", dll,
        "--crate-type", "cdylib",
        "-C", "opt-level=3",
        "-C", "panic=unwind"
    ]
    print(f"  CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"Rust compilation failed with exit code {result.returncode}")
    print(f"  -> Rust DLL built: {dll}")

def run_tests():
    print("=" * 70)
    print("[TEST] Running comprehensive suite (14/14)...")
    test_script = os.path.join(BASE_DIR, "auditoria_externa", "test_v911_comprehensive_suite.py")
    result = subprocess.run([PYTHON, test_script], capture_output=True, text=True, cwd=BASE_DIR)
    print(result.stdout)
    if result.stderr:
        print(f"  STDERR: {result.stderr}")
    if result.returncode != 0:
        raise RuntimeError(f"Test suite failed with exit code {result.returncode}")

def run_fuzz():
    print("[FUZZ] Running Red Team adversarial hounds (4/4)...")
    fuzz_script = os.path.join(BASE_DIR, "auditoria_externa", "fuzz_v911_destructive_hounds.py")
    result = subprocess.run([PYTHON, fuzz_script], capture_output=True, text=True, cwd=BASE_DIR)
    print(result.stdout)
    if result.stderr:
        print(f"  STDERR: {result.stderr}")
    if result.returncode != 0:
        raise RuntimeError(f"Fuzz hounds failed with exit code {result.returncode}")

if __name__ == "__main__":
    t0 = time.time()
    try:
        build_cpp()
        build_rust()
        run_tests()
        run_fuzz()
        elapsed = time.time() - t0
        print("=" * 70)
        print(f"  POLYDIM v911 FULLY CERTIFIED — EXIT CODE 0 — {elapsed:.2f}s")
        print("=" * 70)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n  CERTIFICATION FAILED: {e} ({elapsed:.2f}s)")
        sys.exit(1)
