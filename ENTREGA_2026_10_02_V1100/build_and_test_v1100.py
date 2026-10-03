# ============================================================================
# POLYDIM BUILD & TEST RUNNER V1100 (LOW IMPACT SILICON CERTIFICATION)
# Platform: AMD A4-6300 APU (DDR3 Dual-Channel, ~2.7 GB/s)
# ============================================================================

import os
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
gcc_path = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
rustc_path = r"C:\Users\eluithi\.cargo\bin\rustc.exe"

cpp_src = os.path.join(_DIR, "kernel_cpp_v1100.cpp")
cpp_dll = os.path.join(_DIR, "kernel_cpp_v1100.dll")

rust_src = os.path.join(_DIR, "kernel_rust_v1100.rs")
rust_dll = os.path.join(_DIR, "kernel_rust_v1100.dll")

print("--- 1. COMPILACIÓN C++20 (GCC 14 - MODO BAJO IMPACTO) ---")
cpp_cmd = [
    gcc_path, "-O2", "-std=c++20", "-fopenmp", "-msse4.2", "-mavx",
    "-shared", "-fPIC", "-o", cpp_dll, cpp_src
]
print("Ejecutando:", " ".join(cpp_cmd))
try:
    res_cpp = subprocess.run(cpp_cmd, capture_output=True, text=True, timeout=60)
    print("C++ Exit Code:", res_cpp.returncode)
    if res_cpp.returncode != 0:
        print("C++ Error Output:\n", res_cpp.stderr)
        sys.exit(1)
    print("C++ DLL compilada exitosamente.")
except Exception as e:
    print(f"Error compilando C++: {e}")
    sys.exit(1)

print("\n--- 2. COMPILACIÓN RUST (RUSTC - MODO BAJO IMPACTO) ---")
rust_cmd = [
    rustc_path, "--crate-type", "cdylib", "-C", "opt-level=2",
    "-C", "codegen-units=1", "-C", "panic=unwind",
    "-o", rust_dll, rust_src
]
print("Ejecutando:", " ".join(rust_cmd))
try:
    res_rust = subprocess.run(rust_cmd, capture_output=True, text=True, timeout=60)
    print("Rust Exit Code:", res_rust.returncode)
    if res_rust.returncode != 0:
        print("Rust Error Output:\n", res_rust.stderr)
        sys.exit(1)
    print("Rust DLL compilada exitosamente.")
except Exception as e:
    print(f"Error compilando Rust: {e}")
    sys.exit(1)

print("\n--- 3. EJECUTANDO AUTO-TEST MONOLITO ---")
test_cmd = [sys.executable, os.path.join(_DIR, "polydim_v1100_monolito.py")]
res_test = subprocess.run(test_cmd, capture_output=True, text=True)
print(res_test.stdout)
if res_test.returncode != 0:
    print("Error en monolito:", res_test.stderr)
    sys.exit(1)

print("\n=== CERTIFICACIÓN EN SILICIO V1100 EXIT CODE 0 ===")
