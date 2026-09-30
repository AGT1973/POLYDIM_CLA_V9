# build_and_test_v905.py
# Master Build & Silicon Certification Runner for POLYDIM V905
# ============================================================================

import os
import sys
import subprocess
import shutil
import time

def build_and_test():
    v905_dir = os.path.dirname(os.path.abspath(__file__))
    aud_dir = os.path.join(v905_dir, "auditoria_externa")
    log_path = os.path.join(v905_dir, "raw_silicon_test_log_v905.txt")

    print(f"=== POLYDIM V905 BUILD AND PHYSICAL SILICON CERTIFICATION ===")
    print(f"Directory: {v905_dir}")

    gcc_path = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
    rustc_path = r"C:\Users\eluithi\.cargo\bin\rustc.exe"

    if not os.path.exists(gcc_path):
        gcc_path = "g++"
    if not os.path.exists(rustc_path):
        rustc_path = "rustc"

    cpp_src = os.path.join(v905_dir, "kernel_cpp_v905.cpp")
    cpp_dll = os.path.join(v905_dir, "polydim_cpp_v905.dll")

    rust_src = os.path.join(v905_dir, "kernel_rust_v905.rs")
    rust_dll = os.path.join(v905_dir, "polydim_rust_v905.dll")

    start_time = time.time()
    log_file = open(log_path, "w", encoding="utf-8")

    def log(msg):
        print(msg)
        log_file.write(msg + "\n")
        log_file.flush()

    log(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"OS: {sys.platform}")
    log(f"Python: {sys.version}")

    # 1. Compile C++ Kernel
    log("\n--- STEP 1: Compiling C++20 Kernel V905 (MinGW GCC 14) ---")
    cmd_cpp = [
        gcc_path, "-O3", "-std=c++20", "-fopenmp", "-mavx", "-msse4.2",
        "-shared", cpp_src, "-o", cpp_dll
    ]
    log(f"Command: {' '.join(cmd_cpp)}")
    res_cpp = subprocess.run(cmd_cpp, capture_output=True, text=True)
    if res_cpp.returncode != 0:
        log(f"C++ Compilation FAILED with exit code {res_cpp.returncode}")
        log(f"STDERR:\n{res_cpp.stderr}")
        sys.exit(1)
    log(f"C++ DLL compiled successfully: {os.path.getsize(cpp_dll)} bytes.")
    shutil.copyfile(cpp_dll, os.path.join(aud_dir, "polydim_cpp_v905.dll"))

    # 2. Compile Rust Kernel
    log("\n--- STEP 2: Compiling Rust Kernel V905 (Rustc 1.98.1) ---")
    cmd_rust = [
        rustc_path, "--crate-type", "cdylib", "-C", "opt-level=3",
        "-C", "panic=unwind", rust_src, "-o", rust_dll
    ]
    log(f"Command: {' '.join(cmd_rust)}")
    res_rust = subprocess.run(cmd_rust, capture_output=True, text=True)
    if res_rust.returncode != 0:
        log(f"Rust Compilation FAILED with exit code {res_rust.returncode}")
        log(f"STDERR:\n{res_rust.stderr}")
        sys.exit(1)
    log(f"Rust DLL compiled successfully: {os.path.getsize(rust_dll)} bytes.")
    shutil.copyfile(rust_dll, os.path.join(aud_dir, "polydim_rust_v905.dll"))

    # 3. Run Physical Test Suite
    log("\n--- STEP 3: Running Physical Silicon Unit Test Suite (12/12) ---")
    cmd_test = [sys.executable, os.path.join(aud_dir, "test_v905_comprehensive_suite.py")]
    res_test = subprocess.run(cmd_test, capture_output=True, text=True)
    log(res_test.stdout)
    if res_test.returncode != 0:
        log(f"Test Suite FAILED with exit code {res_test.returncode}")
        log(f"STDERR:\n{res_test.stderr}")
        sys.exit(1)

    # 4. Run Fuzzing Hounds
    log("\n--- STEP 4: Running Red Team Fuzzing Hounds (3/3) ---")
    cmd_fuzz = [sys.executable, os.path.join(aud_dir, "fuzz_v905_destructive_hounds.py")]
    res_fuzz = subprocess.run(cmd_fuzz, capture_output=True, text=True)
    log(res_fuzz.stdout)
    if res_fuzz.returncode != 0:
        log(f"Fuzzing Hounds FAILED with exit code {res_fuzz.returncode}")
        log(f"STDERR:\n{res_fuzz.stderr}")
        sys.exit(1)

    elapsed = time.time() - start_time
    log("\n" + "=" * 70)
    log(f"     FULL V905 SILICON CERTIFICATION PASSED 100% IN {elapsed:.2f}s")
    log(f"     EXIT CODE 0 CERTIFIED ON AMD A4-6300 SILICON FLOOR")
    log("=" * 70)
    log_file.close()

if __name__ == "__main__":
    build_and_test()
