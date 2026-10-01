# fuzz_v909_destructive_hounds.py
# Red Team Adversarial Fuzzing Hounds - POLYDIM v909
# Fixes BRECHA 12: deeper coverage (NaN/Inf/subnormal direct injection, double-close, concurrency)
# ============================================================================

import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v909_monolito import (
    PolydimEnginev909, require, PolydimErrorv909,
    PmtpSlabAllocatorWin, GenerationalBatchHNSW
)

def hound_1_fpu_extreme_magnitude_attack(engine: PolydimEnginev909):
    print("[SABUESO 1/4] Extreme FPU Magnitude Attack (NaN/Inf/subnormal/10^-300/10^300)...")

    # 1. Underflow scale array in RMS normalize
    mat_tiny = np.random.randn(10, 10) * 1e-300
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat_tiny)
    require(np.isfinite(rms), "RMS must be finite for tiny magnitudes")

    # 2. Huge residual that would overflow exp in V905
    l, g = engine.cpp_auon_brake(1e300, 1.0, 1.0)
    require(np.isfinite(l) and np.isfinite(g), "FPU overflow in huge residual")

    # 3. Large matrix values (|a| <= 350) that caused V905 RMS overflow
    mat_large = np.random.uniform(-350, 350, (10, 10))
    normed_big, rms_big = engine.cpp_auon_matrix_rms_normalize(mat_large)
    require(np.isfinite(rms_big), f"RMS must be finite for |a|<=350, got {rms_big}")
    require(np.all(np.isfinite(normed_big)), "Output must be finite for large input")

    # 4. NaN injection must be rejected by FFI
    err = PolydimErrorv909()
    loss_out = ctypes.c_double(0.0)
    grad_out = ctypes.c_double(0.0)
    res = engine.cpp.polydim_cpp_auon_log_cosh_brake_v909(
        float('nan'), 1.0, 1.0,
        ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err)
    )
    require(res != 0, "NaN input must be rejected by FFI")

    # 5. Inf injection must be rejected
    res2 = engine.cpp.polydim_cpp_auon_log_cosh_brake_v909(
        float('inf'), 1.0, 1.0,
        ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err)
    )
    require(res2 != 0, "Inf input must be rejected by FFI")

    # 6. Subnormal float (5e-324)
    l_sub, g_sub = engine.cpp_auon_brake(5e-324, 1.0, 1.0)
    require(np.isfinite(l_sub), "Subnormal residual must produce finite loss")

    print("  -> SABUESO 1 PASS: NaN/Inf/subnormal/extreme magnitude all handled.")

def hound_2_pmtp_boundary_and_lifecycle(engine: PolydimEnginev909):
    print("[SABUESO 2/4] PMTP SharedMemory Boundary & Lifecycle Attack...")

    # Overflow attempt
    pmtp = PmtpSlabAllocatorWin("Local\\Polydimv909FuzzSlab", 512)
    large_data = np.zeros(200, dtype=np.float64)  # 1600 bytes > 512
    try:
        pmtp.write_tensor(large_data)
        require(False, "PMTP should have raised error on overflow")
    except RuntimeError:
        pass
    pmtp.close()

    # Double-close must not crash
    try:
        pmtp.close()
    except Exception:
        pass  # Acceptable: may raise, but must not segfault

    # Zero-size slab
    try:
        pmtp0 = PmtpSlabAllocatorWin("Local\\Polydimv909ZeroSlab", 0)
        # On Windows, CreateFileMappingA with size=0 may fail
        pmtp0.close()
    except (RuntimeError, OSError):
        pass

    print("  -> SABUESO 2 PASS: PMTP boundary + double-close + zero-size handled.")

def hound_3_matrix_degeneracy_attack(engine: PolydimEnginev909):
    print("[SABUESO 3/4] Matrix & Graph Degeneracy Attack...")

    # Zero matrix rank for GF(2)
    mat_zero = np.zeros((10, 2), dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_zero)
    require(rank_gf2 == 0, "Zero matrix rank must be 0")

    # HNSW empty batch
    hnsw = GenerationalBatchHNSW(dim=4)
    try:
        hnsw.insert_batch(np.empty((0, 4)))
    except Exception:
        pass

    # HNSW single-element batch
    hnsw2 = GenerationalBatchHNSW(dim=4)
    hnsw2.insert_batch(np.array([[1.0, 0.0, 0.0, 0.0]]))
    require(hnsw2.version == 1, "Single-element HNSW version mismatch")

    # Nearly-degenerate Stiefel input (almost singular)
    q_degen = np.eye(8, 3) * 1e-15
    q_degen[0, 0] = 1.0
    y_degen = np.zeros_like(q_degen)
    g_degen = np.random.randn(8, 3) * 0.001
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorv909()
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v909(
        8, 3, 0.01,
        np.ascontiguousarray(q_degen, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        np.ascontiguousarray(g_degen, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y_degen.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(ortho_err), ctypes.byref(err)
    )
    # Should return error code -5 (not on Stiefel manifold)
    require(res != 0, f"Degenerate Stiefel input should fail, got res={res}")

    print("  -> SABUESO 3 PASS: Degeneracy handling confirmed.")

def hound_4_clifford_sign_adversarial(engine: PolydimEnginev909):
    """Attack the Clifford sign calculation with known-tricky cases."""
    from polydim_v909_monolito import SparseCliffordBladeIndexer

    print("[SABUESO 4/4] Clifford Sign Adversarial Attack...")

    # Case 1: e3 * e1 = -e13 (needs 1 transposition)
    a = SparseCliffordBladeIndexer(dim=32)
    b = SparseCliffordBladeIndexer(dim=32)
    a.set_blade(0b100, 1.0)  # e3
    b.set_blade(0b001, 1.0)  # e1
    p = a.geometric_product(b)
    require(0b101 in p.blades, "e3*e1 mask missing")
    require(abs(p.blades[0b101] - (-1.0)) < 1e-14, f"e3*e1 should be -e13, got {p.blades[0b101]}")

    # Case 2: e23 * e12 = e1*e3 with sign from transpositions
    # e2*e3 * e1*e2 = e2 e3 e1 e2
    # Move e1 left: e2 e1 e3 e2 (1 swap, sign=-1), e1 e2 e3 e2 (1 swap, sign=+1)
    # Contract e2*e2 = +1: e1 e3 = e13 with sign +1
    c = SparseCliffordBladeIndexer(dim=32)
    d = SparseCliffordBladeIndexer(dim=32)
    c.set_blade(0b110, 1.0)  # e23
    d.set_blade(0b011, 1.0)  # e12
    q = c.geometric_product(d)
    require(0b101 in q.blades, "e23*e12 mask missing")
    # Canonical: e2 e3 e1 e2. Count transpositions to sort [2,3,1,2]:
    # e3 must pass 0 of m1 above it, e1 must pass 1 of m1 above it (bit 1=e2), e2 contracts.
    # Using our algorithm: m1=0b110, m2=0b011
    # Process m2 bit 0 (e1): bits in m1=0b110 above bit 0 = bits 1,2 = 2 bits -> even -> no flip
    # Process m2 bit 1 (e2): bits in m1=0b110 above bit 1 = bit 2 = 1 bit -> odd -> flip
    # m1 had bit 1 set, so contraction: remove from m. m becomes 0b100
    # So sign flipped once -> sign = -1
    # prod_mask = 0b110 ^ 0b011 = 0b101 = e13
    # Result: -e13
    require(abs(q.blades[0b101] - (-1.0)) < 1e-14, f"e23*e12 = {q.blades[0b101]}, expected -1.0")

    # Case 3: e1^2 = 1 (Euclidean)
    e = SparseCliffordBladeIndexer(dim=32)
    f = SparseCliffordBladeIndexer(dim=32)
    e.set_blade(0b001, 1.0)  # e1
    f.set_blade(0b001, 1.0)  # e1
    r = e.geometric_product(f)
    # e1*e1 = +1, mask = 0b001^0b001 = 0, scalar
    require(0 in r.blades, "e1*e1 should produce scalar (mask 0)")
    require(abs(r.blades[0] - 1.0) < 1e-14, f"e1^2 should be +1, got {r.blades[0]}")

    print("  -> SABUESO 4 PASS: Clifford sign canonical correctness verified.")

def run_fuzzing_hounds():
    print("=" * 70)
    print("      POLYDIM v909 RED TEAM ADVERSARIAL FUZZING HOUNDS (4/4)")
    print("=" * 70)
    engine = PolydimEnginev909()
    hound_1_fpu_extreme_magnitude_attack(engine)
    hound_2_pmtp_boundary_and_lifecycle(engine)
    hound_3_matrix_degeneracy_attack(engine)
    hound_4_clifford_sign_adversarial(engine)
    print("=" * 70)
    print("     ALL 4 RED TEAM FUZZING HOUNDS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_fuzzing_hounds()
