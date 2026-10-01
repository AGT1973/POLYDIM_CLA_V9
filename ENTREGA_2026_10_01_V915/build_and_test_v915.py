# ============================================================================
# POLYDIM BUILD & TEST RUNNER V915 (SILICON CERTIFICATION SCRIPT)
# ============================================================================

import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_DIR = os.path.join(BASE_DIR, "auditoria_externa")

GXX_PATH = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
RUSTC_PATH = r"C:\Users\eluithi\.cargo\bin\rustc.exe"


def run_cmd(cmd, cwd=BASE_DIR):
    print(f"[CMD] {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[STDERR]\n{res.stderr}")
        print(f"[STDOUT]\n{res.stdout}")
        sys.exit(res.returncode)
    print(f"[OK] Exit Code 0")
    return res.stdout


def main():
    print("============================================================================")
    print("POLYDIM V915: INICIANDO COMPILACIÓN Y CERTIFICACIÓN DE SILICIO")
    print("============================================================================")

    # 1. Compilar C++ DLL
    cpp_src = os.path.join(BASE_DIR, "kernel_cpp_v915.cpp")
    cpp_dll = os.path.join(BASE_DIR, "polydim_cpp_v915.dll")
    cpp_cmd = f'"{GXX_PATH}" -O3 -std=c++20 -fopenmp -mavx -msse4.2 -shared -o "{cpp_dll}" "{cpp_src}"'
    print("\n--- Compilando C++ Kernel V915 ---")
    run_cmd(cpp_cmd)

    # 2. Compilar Rust DLL
    rust_src = os.path.join(BASE_DIR, "kernel_rust_v915.rs")
    rust_dll = os.path.join(BASE_DIR, "polydim_rust_v915.dll")
    rust_cmd = f'"{RUSTC_PATH}" --crate-type cdylib -C opt-level=3 -o "{rust_dll}" "{rust_src}"'
    print("\n--- Compilando Rust Kernel V915 ---")
    run_cmd(rust_cmd)

    # 3. Ejecutar Suite de Tests Comprensiva (16 tests)
    print("\n--- Ejecutando Suite de Tests Comprensiva (16 Tests) ---")
    suite_script = os.path.join(AUDIT_DIR, "test_v915_comprehensive_suite.py")
    test_out = run_cmd(f'python "{suite_script}"', cwd=AUDIT_DIR)
    print(test_out)

    # 4. Ejecutar Sabuesos Destructivos Red Team (4 Hounds)
    print("\n--- Ejecutando Sabuesos Adversarios Red Team (4 Hounds) ---")
    fuzz_script = os.path.join(AUDIT_DIR, "fuzz_v915_destructive_hounds.py")
    fuzz_out = run_cmd(f'python "{fuzz_script}"', cwd=AUDIT_DIR)
    print(fuzz_out)

    print("============================================================================")
    print("POLYDIM V915: CERTIFICACIÓN FÍSICA EXITOSA (16/16 TESTS + 4/4 HOUNDS PASS)")
    print("============================================================================")


if __name__ == "__main__":
    main()
