import os
import shutil
import subprocess
import sys

base_dir = r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V903"
os.chdir(base_dir)

print(f"=== Compiling POLYDIM V903 Native Kernels in {base_dir} ===")

# 1. Sync double semantic extension .txt
cpp_txt = os.path.join(base_dir, "kernel_cpp_v903.cpp.txt")
cpp_src = os.path.join(base_dir, "kernel_cpp_v903.cpp")
shutil.copy(cpp_src, cpp_txt)

rust_txt = os.path.join(base_dir, "kernel_rust_v903.rs.txt")
rust_src = os.path.join(base_dir, "kernel_rust_v903.rs")
shutil.copy(rust_src, rust_txt)

# 2. Compile C++ DLL with WinLibs GCC 14
gpp_exe = r"E:\winlibs_gcc14_zip\mingw64\bin\g++.exe"
cpp_dll = os.path.join(base_dir, "polydim_cpp_v903.dll")
cmd_cpp = [gpp_exe, "-shared", "-O3", "-std=c++20", "-fopenmp", "-mavx", "-msse4.2", "-o", cpp_dll, cpp_src]
print("Running C++ compilation:", " ".join(cmd_cpp))
res_cpp = subprocess.run(cmd_cpp, capture_output=True, text=True)
if res_cpp.returncode != 0:
    print("C++ Compilation Error:", res_cpp.stderr)
    os._exit(1)
print(f"Compiled C++ DLL: {cpp_dll} ({os.path.getsize(cpp_dll)} bytes)")

# 3. Compile Rust DLL with Rustc
rustc_exe = r"C:\Users\eluithi\.cargo\bin\rustc.exe"
rust_dll = os.path.join(base_dir, "polydim_rust_v903.dll")
cmd_rust = [rustc_exe, "--crate-type", "cdylib", "-C", "opt-level=3", "-C", "panic=unwind", "-o", rust_dll, rust_src]
print("Running Rust compilation:", " ".join(cmd_rust))
res_rust = subprocess.run(cmd_rust, capture_output=True, text=True)
if res_rust.returncode != 0:
    print("Rust Compilation Error:", res_rust.stderr)
    os._exit(1)
print(f"Compiled Rust DLL: {rust_dll} ({os.path.getsize(rust_dll)} bytes)")

# Copy DLLs to auditoria_externa
audit_dir = os.path.join(base_dir, "auditoria_externa")
os.makedirs(audit_dir, exist_ok=True)
shutil.copy(cpp_dll, os.path.join(audit_dir, "polydim_cpp_v903.dll"))
shutil.copy(rust_dll, os.path.join(audit_dir, "polydim_rust_v903.dll"))

# 4. Run test suite
test_script = os.path.join(audit_dir, "test_v903_comprehensive_suite.py")
log_file = os.path.join(base_dir, "raw_silicon_test_log_v903.txt")

env = os.environ.copy()
env["PYTHONPATH"] = base_dir + os.pathsep + audit_dir + os.pathsep + env.get("PYTHONPATH", "")

print("Running test suite...")
with open(log_file, "w", encoding="utf-8") as lf:
    res_test = subprocess.run([sys.executable, test_script], cwd=audit_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lf.write(res_test.stdout)
    print(res_test.stdout)

print(f"Test Exit Code: {res_test.returncode}")
print(f"Saved Raw Log to: {log_file}")

# 5. Run Destructive Hounds
hounds_script = os.path.join(audit_dir, "fuzz_v903_destructive_hounds.py")
print("Running 3 Destructive Hounds...")
res_hounds = subprocess.run([sys.executable, hounds_script], cwd=audit_dir, env=env, text=True)
print(f"Hounds Exit Code: {res_hounds.returncode}")

if res_test.returncode == 0 and res_hounds.returncode == 0:
    print("\n=== POLYDIM V903 SILICON CERTIFICATION COMPLETE: 100% PASS ===")
else:
    print("\n=== POLYDIM V903 SILICON CERTIFICATION FAILED ===")
    os._exit(1)
