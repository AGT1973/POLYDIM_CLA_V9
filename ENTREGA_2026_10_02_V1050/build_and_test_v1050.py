# ============================================================================
# POLYDIM V1050 SILICON COMPILATION & CERTIFICATION SUITE (HITO DECENAL 110)
# Plataforma: AMD A4-6300 APU | GCC 14.2.0 MinGW64 | Rustc 1.80+
# ============================================================================

import os
import subprocess
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))

GCC_PATH = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
RUSTC_PATH = r"C:\Users\eluithi\.cargo\bin\rustc.exe"

CPP_SRC = os.path.join(_DIR, "kernel_cpp_v1050.cpp")
CPP_DLL = os.path.join(_DIR, "kernel_cpp_v1050.dll")

RUST_SRC = os.path.join(_DIR, "kernel_rust_v1050.rs")
RUST_DLL = os.path.join(_DIR, "kernel_rust_v1050.rs.dll")

UNIT_TESTS = os.path.join(_DIR, "auditoria_externa", "test_v1050_comprehensive_suite.py")
FUZZ_TESTS = os.path.join(_DIR, "auditoria_externa", "fuzz_v1050_destructive_hounds.py")

def run_step(name, cmd_args):
    print(f"\n[BUILD] {name}...")
    print(f"Command: {' '.join(cmd_args)}")
    t0 = time.time()
    res = subprocess.run(cmd_args, capture_output=True, text=True)
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
    print("POLYDIM V1050 SILICON COMPILATION & CERTIFICATION SUITE (HITO DECENAL 110)")
    print("=" * 76)

    # 1. Compile C++ Kernel V1050
    cpp_cmd = [
        GCC_PATH, "-O3", "-std=c++20", "-shared", "-fopenmp",
        "-mavx", "-msse4.2",
        "-o", CPP_DLL,
        CPP_SRC
    ]
    run_step("Compiling C++20 Kernel V1050 with GCC 14", cpp_cmd)

    # 2. Compile Rust Kernel V1050
    rust_dll_target = os.path.join(_DIR, "kernel_rust_v1050.dll")
    rust_cmd = [
        RUSTC_PATH, "--crate-type", "cdylib", "-C", "opt-level=3", "-C", "panic=unwind",
        "-o", rust_dll_target,
        RUST_SRC
    ]
    run_step("Compiling Rust Kernel V1050 with rustc", rust_cmd)

    # 3. Run Unit Tests V1050
    run_step("Running V1050 Comprehensive Unit Tests", [sys.executable, UNIT_TESTS])

    # 4. Run Fuzz Hounds V1050
    run_step("Running V1050 Destructive Fuzz Hounds", [sys.executable, FUZZ_TESTS])

    print("\n" + "=" * 76)
    print("[SUCCESS] ALL V1050 KERNELS & TESTS CERTIFIED WITH EXIT CODE 0")
    print("=" * 76)

if __name__ == "__main__":
    main()
