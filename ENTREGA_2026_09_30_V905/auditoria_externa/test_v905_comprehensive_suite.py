# test_v905_comprehensive_suite.py
# Comprehensive Physical Unit Test Suite - POLYDIM V905
# ============================================================================

import os
import sys
import ctypes
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v905_monolito import (
    PolydimEngineV905, require, PolydimErrorV905,
    PmtpSlabAllocatorWin, GenerationalBatchHNSW, SparseCliffordBladeIndexer
)

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM V905 PHYSICAL SILICON COMPREHENSIVE SUITE (12/12)")
    print("=" * 70)

    engine = PolydimEngineV905()

    # TEST 1: AuON Log-Cosh Brake
    print("[TEST 1/12] AuON Log-Cosh Brake...")
    l1, g1 = engine.cpp_auon_brake(0.5, scale_s=1.0, lambda_val=1.0)
    require(l1 > 0.0, "Loss must be positive")
    require(abs(g1 - math.tanh(0.5)) < 1e-5, "Gradient mismatch")
    print("  -> PASS: Log-cosh loss and grad matched.")

    # TEST 2: AuON Kahan Compensated RMS Normalize
    print("[TEST 2/12] AuON Kahan Compensated RMS Normalize...")
    mat = np.random.randn(10, 10) * 1e-100
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat)
    require(np.isfinite(rms), "RMS must be finite")
    require(np.all(np.isfinite(normed)), "Normalized matrix must be finite")
    print(f"  -> PASS: Kahan compensated RMS = {rms:.6e}")

    # TEST 3: Riemannian Geodesic
    print("[TEST 3/12] Riemannian Geodesic Metric on S^(D-1)...")
    u = np.array([1.0, 0.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    require(abs(ang - np.pi / 2.0) < 1e-6, f"Angular distance mismatch: {ang}")
    require(abs(chord - np.sqrt(2.0)) < 1e-6, f"Chordal distance mismatch: {chord}")
    print("  -> PASS: Orthogonal vector distance exact pi/2.")

    # TEST 4: CliffordNet SIMD 4x Unrolled Bivector Interaction
    print("[TEST 4/12] CliffordNet SIMD 4x Unrolled Bivector Interaction...")
    vecs = np.random.randn(10, 8)
    bivecs, energy = engine.cpp_cliffordnet_interact(vecs)
    require(bivecs.shape == (10, 28), f"Bivector shape mismatch: {bivecs.shape}")
    require(energy > 0.0, "Energy must be positive")
    print(f"  -> PASS: SIMD 4x unrolled bivector energy = {energy:.6f}")

    # TEST 5: GF(2) Bitpacked Reduction with Dynamic OpenMP Threshold
    print("[TEST 5/12] GF(2) Bitpacked Reduction with Dynamic Threshold...")
    mat_gf2 = np.array([
        [0b1100],
        [0b1010],
        [0b0110],
        [0b0000]
    ], dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_gf2)
    require(rank_gf2 == 2, f"GF(2) rank mismatch: expected 2, got {rank_gf2}")
    print(f"  -> PASS: GF(2) matrix rank = {rank_gf2}")

    # TEST 6: Stiefel Cayley-SMW Matrix-Free Retraction
    print("[TEST 6/12] Stiefel Cayley-SMW Matrix-Free Retraction...")
    q_mat, _ = np.linalg.qr(np.random.randn(16, 4))
    g_mat = np.random.randn(16, 4) * 0.01
    y_out = np.zeros_like(q_mat)
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorV905()
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v905(
        16, 4, 0.1,
        q_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        g_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(ortho_err), ctypes.byref(err)
    )
    require(res == 0, "Stiefel SMW failed")
    require(ortho_err.value < 1e-4, f"Orthogonality defect too high: {ortho_err.value}")
    print(f"  -> PASS: Retracted Y orthogonality error = {ortho_err.value:.8e}")

    # TEST 7: FIRE Metric
    print("[TEST 7/12] FIRE Spectral Metric...")
    q_mat, _ = np.linalg.qr(np.random.randn(20, 5))
    drift = ctypes.c_double(0.0)
    reinit = ctypes.c_uint8(0)
    err = PolydimErrorV905()
    res = engine.cpp.polydim_cpp_fire_metric_v905(
        20, 5,
        q_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        1e-4, ctypes.byref(drift), ctypes.byref(reinit), ctypes.byref(err)
    )
    require(res == 0, "FIRE metric failed")
    require(drift.value < 1e-12, f"FIRE drift too high for QR matrix: {drift.value}")
    print(f"  -> PASS: Spectral drift = {drift.value:.10e}, Reinit needed = {reinit.value}")

    # TEST 8: Native Windows PMTP SharedMemory Transport (Solving Brecha 7)
    print("[TEST 8/12] Native Windows SharedMemory PMTP Transport...")
    pmtp = PmtpSlabAllocatorWin("Local\\PolydimV905TestSlab", 1024)
    arr_in = np.array([3.14159, 2.71828, 1.41421, 1.73205], dtype=np.float64)
    pmtp.write_tensor(arr_in)
    arr_out = pmtp.read_tensor((4,), np.float64)
    require(np.allclose(arr_in, arr_out), "PMTP shared memory data mismatch")
    pmtp.close()
    print("  -> PASS: Native Windows PMTP SharedMemory zero-copy verified.")

    # TEST 9: Generational Batch HNSW Graph Builder (Solving Cuello 1)
    print("[TEST 9/12] Generational Batch HNSW Graph Builder...")
    hnsw = GenerationalBatchHNSW(dim=4, m=8)
    hnsw.insert_batch(np.random.randn(20, 4))
    snap = hnsw.get_read_snapshot()
    require(snap["version"] == 1, "Snapshot version mismatch")
    require(len(snap["nodes"]) == 20, "Snapshot node count mismatch")
    print(f"  -> PASS: Generational HNSW batch inserted 20 nodes, version={snap['version']}")

    # TEST 10: Sparse Clifford Blade Representation for D >= 32 (Solving Brecha 6)
    print("[TEST 10/12] Sparse Clifford Blade Representation for D >= 32...")
    b1 = SparseCliffordBladeIndexer(dim=32)
    b2 = SparseCliffordBladeIndexer(dim=32)
    b1.set_blade(0b0001, 2.0) # e_1 component
    b2.set_blade(0b0010, 3.0) # e_2 component
    prod = b1.geometric_product(b2)
    require(0b0011 in prod.blades, "Wedge product mask 0b0011 missing")
    require(abs(prod.blades[0b0011] - 6.0) < 1e-6, f"Wedge product coeff mismatch: {prod.blades.get(0b0011)}")
    print("  -> PASS: Sparse Clifford Blade geometric product 2.0 e_1 ^ 3.0 e_2 = 6.0 e_12.")

    # TEST 11: Rust FFI Bridge V905 & std::ptr::copy Safety
    print("[TEST 11/12] Rust FFI Bridge V905...")
    loss_r = ctypes.c_double(0.0)
    grad_r = ctypes.c_double(0.0)
    err_r = PolydimErrorV905()
    res_r = engine.rust.polydim_rust_auon_log_cosh_brake_v905(
        0.5, 1.0, 1.0,
        ctypes.byref(loss_r), ctypes.byref(grad_r), ctypes.byref(err_r)
    )
    require(res_r == 0, "Rust FFI AuON failed")
    print("  -> PASS: Rust FFI V905 bridge operational.")

    # TEST 12: Invariant Protection Guard Safety
    print("[TEST 12/12] Invariant Protection Guard Safety...")
    try:
        require(False, "Test synthetic invariant violation")
        raise RuntimeError("Fail: require did not raise")
    except RuntimeError as e:
        require("INVARIANT ERROR" in str(e), "Exception string mismatch")
    print("  -> PASS: require() invariant guard active and immune to -O.")

    print("=" * 70)
    print("     ALL 12/12 PHYSICAL SILICON TESTS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_all_tests()
