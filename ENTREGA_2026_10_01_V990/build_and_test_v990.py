# ============================================================================
# POLYDIM BUILD & TEST RUNNER V990 (HITO 80 QUINCUAGESIMAL)
# ============================================================================

import subprocess
import sys
import os
import time

DIR = os.path.dirname(os.path.abspath(__file__))

def run_cmd(cmd, desc):
    print(f"\n[BUILD] {desc}...")
    print(f"Command: {cmd}")
    t0 = time.time()
    res = subprocess.run(cmd, shell=True, cwd=DIR, capture_output=True, text=True)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"[FAIL] {desc} (Exit code {res.returncode}) in {dt:.2f}s")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
        return False
    print(f"[OK] {desc} passed in {dt:.2f}s")
    return True

def main():
    print("============================================================================")
    print("POLYDIM V990 SILICON COMPILATION & CERTIFICATION SUITE")
    print("============================================================================")

    # 1. Compile C++ Kernel
    gpp = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
    cpp_src = os.path.join(DIR, "kernel_cpp_v990.cpp")
    cpp_dll = os.path.join(DIR, "kernel_cpp_v990.dll")
    cpp_cmd = f'"{gpp}" -O3 -std=c++20 -shared -fopenmp -mavx -msse4.2 -o "{cpp_dll}" "{cpp_src}"'
    if not run_cmd(cpp_cmd, "Compiling C++20 Kernel V990 with GCC 14"):
        sys.exit(1)

    # 2. Compile Rust Kernel
    rustc = r"C:\Users\eluithi\.cargo\bin\rustc.exe"
    rust_src = os.path.join(DIR, "kernel_rust_v990.rs")
    rust_dll = os.path.join(DIR, "kernel_rust_v990.dll")
    rust_cmd = f'"{rustc}" --crate-type cdylib -C opt-level=3 -C panic=unwind -o "{rust_dll}" "{rust_src}"'
    if not run_cmd(rust_cmd, "Compiling Rust Kernel V990 with rustc"):
        sys.exit(1)

    # 3. Run Unit Tests Suite
    test_suite = os.path.join(DIR, "auditoria_externa", "test_v990_comprehensive_suite.py")
    test_cmd = f'python "{test_suite}"'
    if not run_cmd(test_cmd, "Running V990 Comprehensive Unit Tests"):
        sys.exit(1)

    # 4. Run Destructive Fuzz Hounds
    hound_suite = os.path.join(DIR, "auditoria_externa", "fuzz_v990_destructive_hounds.py")
    hound_cmd = f'python "{hound_suite}"'
    if not run_cmd(hound_cmd, "Running V990 Destructive Fuzz Hounds"):
        sys.exit(1)

    print("\n============================================================================")
    print("[SUCCESS] ALL V990 KERNELS & TESTS CERTIFIED WITH EXIT CODE 0")
    print("============================================================================")

if __name__ == "__main__":
    main()
