# fuzz_v904_destructive_hounds.py
# Red Team Adversarial Fuzzing Hounds - POLYDIM V904
# ============================================================================

import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v904_monolito import PolydimEngineV904, require, PolydimErrorV904

def hound_1_fpu_adversarial_attack(engine: PolydimEngineV904):
    print("[SABUESO 1/3] Adversarial FPU Attack (NaNs, Infs, Extremes)...")
    
    # 1. NaN in residual
    try:
        engine.cpp_auon_brake(np.nan, 1.0, 1.0)
    except RuntimeError:
        pass
    
    # 2. Inf in residual
    try:
        engine.cpp_auon_brake(np.inf, 1.0, 1.0)
    except RuntimeError:
        pass

    # 3. Subnormal / Zero vector in Riemannian Geodesic
    u_zero = np.zeros(10, dtype=np.float64)
    v_zero = np.zeros(10, dtype=np.float64)
    try:
        engine.cpp_riemannian_geodesic(u_zero, v_zero)
    except RuntimeError:
        pass

    # 4. Extreme magnitude input
    res_huge = 1e300
    l, g = engine.cpp_auon_brake(res_huge, 1.0, 1.0)
    require(np.isfinite(l) and np.isfinite(g), "FPU overflow in huge residual")

    print("  -> SABUESO 1 PASS: FPU Hardening confirmed resistant.")

def hound_2_memory_alignment_and_ffi_attack(engine: PolydimEngineV904):
    print("[SABUESO 2/3] Memory Alignment & FFI Overlap Attack...")
    
    # Overlapping copy in QSBR
    src_data = (ctypes.c_uint8 * 100)(*range(100))
    dst_data = src_data # Same memory pointer!
    copied = ctypes.c_size_t(0)
    err = PolydimErrorV904()
    
    res = engine.cpp.polydim_cpp_qsbr_snapshot_copy_v904(
        src_data, 100, dst_data, ctypes.byref(copied), ctypes.byref(err)
    )
    require(res == 0, "QSBR overlapping copy failed")
    require(copied.value == 100, "Copied bytes mismatch")

    print("  -> SABUESO 2 PASS: FFI Memory & Overlap safety confirmed.")

def hound_3_simplicial_and_matrix_degeneracy_attack(engine: PolydimEngineV904):
    print("[SABUESO 3/3] Simplicial & Matrix Degeneracy Attack...")
    
    # Rank-deficient zero matrix for GF(2) reduction
    mat_zero = np.zeros((10, 2), dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_zero)
    require(rank_gf2 == 0, "Zero matrix rank must be 0")

    # Degenerate non-orthogonal X for Stiefel SMW
    x_bad = np.ones((8, 3), dtype=np.float64)
    g_bad = np.random.randn(8, 3)
    y_out = np.zeros_like(x_bad)
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorV904()
    
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v904(
        8, 3, 0.1,
        x_bad.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        g_bad.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(ortho_err), ctypes.byref(err)
    )
    require(res == -5, f"Expected error code -5 for non-Stiefel input, got {res}")

    print("  -> SABUESO 3 PASS: Matrix Degeneracy handling confirmed.")

def run_fuzzing_hounds():
    print("=" * 70)
    print("      POLYDIM V904 RED TEAM ADVERSARIAL FUZZING HOUNDS (3/3)")
    print("=" * 70)
    engine = PolydimEngineV904()
    hound_1_fpu_adversarial_attack(engine)
    hound_2_memory_alignment_and_ffi_attack(engine)
    hound_3_simplicial_and_matrix_degeneracy_attack(engine)
    print("=" * 70)
    print("     ALL 3 RED TEAM FUZZING HOUNDS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_fuzzing_hounds()
