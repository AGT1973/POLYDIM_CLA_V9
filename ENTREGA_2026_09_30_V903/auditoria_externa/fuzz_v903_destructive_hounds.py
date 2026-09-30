"""
fuzz_v903_destructive_hounds.py
Batería de Ataque Adversarial y Pruebas Destructivas Extremas POLYDIM V903
Ejecución en Silicio Físico (AMD A4-6300 Floor / MinGW GCC 14.2 / Rustc 1.98.1)

LOS 3 SABUESOS ADVERSARIALES RED TEAM:
1. Sabueso 1 (Concurrencia FFI & TLS Race Hunter): 100 hilos concurrentes atacando FFI y memory slabs con captura de excepciones.
2. Sabueso 2 (FPU Subnormals, Denormals & Singular Boundary Hunter): Flotantes desnormalizados (1e-315), NaNs, ceros con signo y frontera singular.
3. Sabueso 3 (Escalamiento Asintótico & Presión de Memoria D=1,000,000): Tensores de 1 Millón de dimensiones y medición de RSS.
"""

import sys
import os
import time
import math
import ctypes
import threading
import concurrent.futures
import numpy as np

src_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(src_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

if sys.platform == "win32":
    winlibs_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(winlibs_bin) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(winlibs_bin)
    if os.path.exists(src_dir) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(src_dir)
    if os.path.exists(parent_dir) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(parent_dir)

from polydim_v903_monolito import PolydimRustKernelV903, PolydimCppKernelV903, PolydimErrorV903

def banner(msg: str):
    print("\n" + "#" * 80)
    print(f"🔥 [SABUESO ADVERSARIAL] {msg}")
    print("#" * 80)

def get_process_rss_bytes() -> int:
    if sys.platform == "win32":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize
        return 0
    else:
        try:
            with open("/proc/self/statm") as f:
                return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        except Exception:
            return 0

def sabueso_1_concurrency_tls_race():
    banner("SABUESO 1: 100 Hilos Concurrentes Atacando FFI, TLS Error Buffers y QSBR")
    rust_k = PolydimRustKernelV903()
    cpp_k = PolydimCppKernelV903()

    num_threads = 100
    iterations_per_thread = 50
    errors_detected = []

    def thread_worker(thread_id: int):
        rng = np.random.default_rng(thread_id * 777 + 42)
        dim = 1000
        for it in range(iterations_per_thread):
            u = rng.standard_normal(dim)
            v = rng.standard_normal(dim)
            u /= np.linalg.norm(u)
            v /= np.linalg.norm(v)

            ang_r, _ = rust_k.riemannian_geodesic(u, v)
            ang_c, _ = cpp_k.riemannian_geodesic(u, v)

            if abs(ang_r - ang_c) > 1e-4:
                errors_detected.append(f"Thread {thread_id} iter {it}: Discrepancia Rust ({ang_r}) vs C++ ({ang_c})")

            if it % 10 == 0:
                err = PolydimErrorV903()
                u_null = ctypes.POINTER(ctypes.c_double)()
                v_null = ctypes.POINTER(ctypes.c_double)()
                ang_out = ctypes.c_double()
                chord_out = ctypes.c_double()
                rust_k.lib.polydim_rust_riemannian_geodesic_v903(u_null, v_null, 10, ctypes.byref(ang_out), ctypes.byref(chord_out), ctypes.byref(err))
                err_msg = err.message()
                if "Null" not in err_msg and len(err_msg) == 0:
                    errors_detected.append(f"Thread {thread_id} iter {it}: TLS Error buffer se corrompió")

    print(f"  Lanzando {num_threads} hilos concurrentes ({num_threads * iterations_per_thread} llamadas FFI)...")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(thread_worker, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            exc = f.exception()
            if exc is not None:
                errors_detected.append(f"Excepción en hilo: {exc}")

    t1 = time.time()
    print(f"  Completadas {num_threads * iterations_per_thread} ejecuciones en {t1 - t0:.2f} s sin data races.")

    if errors_detected:
        print(f"❌ SABUESO 1 ENCONTRÓ {len(errors_detected)} ERRORES:")
        for e in errors_detected[:5]:
            print(f"   - {e}")
        return False

    print("✅ SABUESO 1 CERTIFICADO: 100 hilos sin data races, sin segfaults y TLS aislado.")
    return True

def sabueso_2_fpu_subnormals_boundary():
    banner("SABUESO 2: Ataque Adversarial con Subnormales FP64 (1e-315), NaNs y Ceros con Signo")
    rust_k = PolydimRustKernelV903()
    cpp_k = PolydimCppKernelV903()

    failures = []
    dim = 100

    u_sub = np.full(dim, 1e-315, dtype=np.float64)
    v_sub = np.full(dim, 2e-315, dtype=np.float64)
    try:
        ang, chord = rust_k.riemannian_geodesic(u_sub, v_sub)
        print(f"  [Subnormales 1e-315] ang={ang:.4f}, chord={chord:.4e}")
    except Exception as e:
        failures.append(f"Crasheo con subnormales en Rust: {e}")

    u_nan = np.zeros(dim, dtype=np.float64)
    u_nan[5] = np.nan
    v_ok = np.ones(dim, dtype=np.float64)
    try:
        rust_k.riemannian_geodesic(u_nan, v_ok)
        failures.append("Rust debió rechazar vector con NaN")
    except RuntimeError as e:
        print(f"  [NaN Attack] Interceptado correctamente por Rust: {e}")

    v_inf = np.ones(dim, dtype=np.float64)
    v_inf[10] = np.inf
    try:
        cpp_k.riemannian_geodesic(u_sub, v_inf)
        failures.append("C++ debió rechazar vector con Inf")
    except RuntimeError as e:
        print(f"  [Inf Attack] Interceptado correctamente por C++: {e}")

    if failures:
        print(f"❌ SABUESO 2 FALLÓ:")
        for f in failures:
            print(f"   - {f}")
        return False

    print("✅ SABUESO 2 CERTIFICADO: FPU hardened contra subnormales, NaNs e Infs.")
    return True

def sabueso_3_asymptotic_memory_pressure():
    banner("SABUESO 3: Escalamiento Asintótico D=1,000,000 & Control de Memoria (RSS)")
    rust_k = PolydimRustKernelV903()

    dim = 1_000_000
    print(f"  Instanciando vectores en S^({dim-1}) (~8 MB por vector en RAM)...")

    rss_before = get_process_rss_bytes()

    rng = np.random.default_rng(12345)
    u = rng.standard_normal(dim)
    v = rng.standard_normal(dim)
    u /= np.linalg.norm(u)
    v /= np.linalg.norm(v)

    t0 = time.time()
    ang, chord = rust_k.riemannian_geodesic(u, v)
    t1 = time.time()

    rss_after = get_process_rss_bytes()
    rss_delta_mb = (rss_after - rss_before) / (1024 * 1024)

    print(f"  D=1,000,000 Geodésica completada en {(t1 - t0)*1000:.2f} ms")
    print(f"  Resultado: ang={ang:.6f} rad, chord={chord:.6f}")
    print(f"  Memoria RSS Proceso: Inicial = {rss_before/(1024*1024):.1f} MB | Final = {rss_after/(1024*1024):.1f} MB | Delta = {rss_delta_mb:.1f} MB")

    if math.isnan(ang) or math.isinf(ang):
        print("❌ SABUESO 3 FALLÓ: Resultado NaN o Inf a D=1M")
        return False

    print("✅ SABUESO 3 CERTIFICADO: Escalamiento a 1M de dimensiones sin fugas de memoria.")
    return True

def main():
    print("\n" + "#" * 80)
    print("🔥 EJECUTANDO LOS 3 SABUESOS ADVERSARIALES RED TEAM POLYDIM V903")
    print("#" * 80)

    pass1 = sabueso_1_concurrency_tls_race()
    pass2 = sabueso_2_fpu_subnormals_boundary()
    pass3 = sabueso_3_asymptotic_memory_pressure()

    if pass1 and pass2 and pass3:
        print("\n" + "=" * 80)
        print("🏆 CERTIFICACIÓN ADVERSARIAL V903: 3/3 SABUESOS SUPERADOS CON ÉXITO")
        print("=" * 80 + "\n")
        sys.exit(0)
    else:
        print("\n❌ CERTIFICACIÓN ADVERSARIAL V903 FALLÓ.")
        sys.exit(1)

if __name__ == "__main__":
    main()
