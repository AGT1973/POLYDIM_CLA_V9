# build_and_test_v914.py
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MINGW_BIN = r"E:\winlibs_gcc14_zip\mingw64\bin"
GPP = os.path.join(MINGW_BIN, "g++.exe")
RUSTC = r"C:\Users\eluithi\.cargo\bin\rustc.exe"
PYTHON = sys.executable

def build_cpp():
    print("=" * 70)
    print("[BUILD] Compiling C++ kernel v914...")
    src = os.path.join(BASE_DIR, "kernel_cpp_v914.cpp")
    dll = os.path.join(BASE_DIR, "polydim_cpp_v914.dll")
    cmd = [
        GPP, src, "-o", dll,
        "-shared", "-O3", "-std=c++20",
        "-fopenmp", "-mavx", "-msse4.2",
        "-Wl,--export-all-symbols"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0: raise RuntimeError(f"C++ build failed:\n{res.stderr}")
    print("  -> C++ DLL built successfully:", dll)

def build_rust():
    print("[BUILD] Compiling Rust kernel v914...")
    src = os.path.join(BASE_DIR, "kernel_rust_v914.rs")
    dll = os.path.join(BASE_DIR, "polydim_rust_v914.dll")
    cmd = [
        RUSTC, src, "-o", dll,
        "--crate-type", "cdylib",
        "-C", "opt-level=3",
        "-C", "panic=unwind"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0: raise RuntimeError(f"Rust build failed:\n{res.stderr}")
    print("  -> Rust DLL built successfully:", dll)

def run_tests():
    print("[TEST] Running V914 suite...")
    test_script = os.path.join(BASE_DIR, "auditoria_externa", "test_v914_comprehensive_suite.py")
    res = subprocess.run([PYTHON, test_script], capture_output=True, text=True, cwd=BASE_DIR)
    print(res.stdout)
    if res.returncode != 0: raise RuntimeError(f"Tests failed:\n{res.stderr}")

def run_fuzz():
    print("[FUZZ] Running V914 fuzz hounds...")
    fuzz_script = os.path.join(BASE_DIR, "auditoria_externa", "fuzz_v914_destructive_hounds.py")
    res = subprocess.run([PYTHON, fuzz_script], capture_output=True, text=True, cwd=BASE_DIR)
    print(res.stdout)
    if res.returncode != 0: raise RuntimeError(f"Fuzz failed:\n{res.stderr}")

if __name__ == "__main__":
    try:
        build_cpp()
        build_rust()
        run_tests()
        run_fuzz()
        print("V914 BUILT AND TESTED SUCCESSFULLY - EXIT CODE 0")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)
