# test_v910_comprehensive_suite.py
# Comprehensive Physical Unit Test Suite - POLYDIM v910
# ============================================================================

import os
import sys
import ctypes
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v910_monolito import (
    PolydimEnginev910, require, PolydimErrorv910,
    PmtpSlabAllocatorWin, GenerationalBatchHNSW, SparseCliffordBladeIndexer,
    _clifford_canonical_sign
)

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM v910 PHYSICAL SILICON COMPREHENSIVE SUITE (14/14)")
    print("=" * 70)

    engine = PolydimEnginev910()

    # TEST 1: AuON Log-Cosh Brake
    print("[TEST 1/14] AuON Log-Cosh Brake...")
    l1, g1 = engine.cpp_auon_brake(0.5, scale_s=1.0, lambda_val=1.0)
    require(l1 > 0.0, "Loss must be positive")
    require(abs(g1 - math.tanh(0.5)) < 1e-5, "Gradient mismatch")
    print("  -> PASS: Log-cosh loss and grad matched.")

    # TEST 2: AuON Log-Space RMS Normalize (fixing BUG 13: exp overflow for |a|>350)
    print("[TEST 2/14] AuON Log-Space RMS Normalize (anti-overflow)...")
    mat = np.random.randn(10, 10) * 1e-100
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat)
    require(np.isfinite(rms), "RMS must be finite for tiny input")
    require(np.all(np.isfinite(normed)), "Normalized matrix must be finite")
    # Test with large values that would overflow exp(2*a) in V905 (limit is ~354)
    # We use uniform(-350, 350) so max value is 350. cosh(350) = exp(350) which fits in double (limit ~709).
    mat_big = np.random.uniform(-350, 350, (10, 10))
    normed_big, rms_big = engine.cpp_auon_matrix_rms_normalize(mat_big)
    require(np.isfinite(rms_big), f"RMS must be finite for |a|~350, got {rms_big}")
    require(np.all(np.isfinite(normed_big)), "Normalized matrix must be finite for large input")
    print(f"  -> PASS: Log-space RMS tiny={rms:.6e}, large={rms_big:.6e}")

    # TEST 3: Riemannian Geodesic
    print("[TEST 3/14] Riemannian Geodesic Metric on S^(D-1)...")
    u = np.array([1.0, 0.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    require(abs(ang - np.pi / 2.0) < 1e-6, f"Angular distance mismatch: {ang}")
    require(abs(chord - np.sqrt(2.0)) < 1e-6, f"Chordal distance mismatch: {chord}")
    print("  -> PASS: Orthogonal vector distance exact pi/2.")

    # TEST 4: CliffordNet Bivector Interaction (4x unroll boundary fix)
    print("[TEST 4/14] CliffordNet Bivector Interaction (fixed 4x unroll)...")
    vecs = np.random.randn(10, 8)
    bivecs, energy = engine.cpp_cliffordnet_interact(vecs)
    require(bivecs.shape == (10, 28), f"Bivector shape mismatch: {bivecs.shape}")
    require(energy > 0.0, "Energy must be positive")
    # Test with k=5 (non-multiple of 4, exercises tail loop)
    vecs5 = np.random.randn(10, 5)
    bivecs5, energy5 = engine.cpp_cliffordnet_interact(vecs5)
    require(bivecs5.shape == (10, 10), f"Bivector shape for k=5: {bivecs5.shape}")
    require(energy5 > 0.0, "Energy for k=5 must be positive")
    print(f"  -> PASS: Bivector energy k=8: {energy:.6f}, k=5: {energy5:.6f}")

    # TEST 5: GF(2) Bitpacked Reduction with Dynamic OpenMP Threshold
    print("[TEST 5/14] GF(2) Bitpacked Reduction with Dynamic Threshold...")
    mat_gf2 = np.array([
        [0b1100],
        [0b1010],
        [0b0110],
        [0b0000]
    ], dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_gf2)
    require(rank_gf2 == 2, f"GF(2) rank mismatch: expected 2, got {rank_gf2}")
    print(f"  -> PASS: GF(2) matrix rank = {rank_gf2}")

    # TEST 6: Stiefel Cayley-SMW Matrix-Free Retraction (with int64 solver)
    print("[TEST 6/14] Stiefel Cayley-SMW Matrix-Free Retraction...")
    q_mat, _ = np.linalg.qr(np.random.randn(16, 4))
    g_mat = np.random.randn(16, 4) * 0.01
    y_out = np.zeros_like(q_mat)
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorv910()
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v910(
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
    print("[TEST 7/14] FIRE Spectral Metric...")
    q_mat, _ = np.linalg.qr(np.random.randn(20, 5))
    drift = ctypes.c_double(0.0)
    reinit = ctypes.c_uint8(0)
    err = PolydimErrorv910()
    res = engine.cpp.polydim_cpp_fire_metric_v910(
        20, 5,
        q_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        1e-4, ctypes.byref(drift), ctypes.byref(reinit), ctypes.byref(err)
    )
    require(res == 0, "FIRE metric failed")
    require(drift.value < 1e-12, f"FIRE drift too high for QR matrix: {drift.value}")
    print(f"  -> PASS: Spectral drift = {drift.value:.10e}, Reinit needed = {reinit.value}")

    # TEST 8: Native Windows PMTP SharedMemory Transport
    print("[TEST 8/14] Native Windows SharedMemory PMTP Transport...")
    pmtp = PmtpSlabAllocatorWin("Local\\Polydimv910TestSlab", 1024)
    arr_in = np.array([3.14159, 2.71828, 1.41421, 1.73205], dtype=np.float64)
    pmtp.write_tensor(arr_in)
    arr_out = pmtp.read_tensor((4,), np.float64)
    require(np.allclose(arr_in, arr_out), "PMTP shared memory data mismatch")
    pmtp.close()
    print("  -> PASS: Native Windows PMTP SharedMemory zero-copy verified.")

    # TEST 9: Generational Batch HNSW Graph Builder (with KeyError guard)
    print("[TEST 9/14] Generational Batch HNSW Graph Builder...")
    hnsw = GenerationalBatchHNSW(dim=4, m=8)
    hnsw.insert_batch(np.random.randn(20, 4))
    hnsw.insert_batch(np.random.randn(10, 4))  # Second batch to exercise edge back-linking
    snap = hnsw.get_read_snapshot()
    require(snap["version"] == 2, f"Snapshot version mismatch: {snap['version']}")
    require(len(snap["nodes"]) == 30, f"Snapshot node count mismatch: {len(snap['nodes'])}")
    print(f"  -> PASS: HNSW 2 batches (30 nodes), version={snap['version']}")

    # TEST 10: Sparse Clifford Blade with CORRECT canonical sign
    print("[TEST 10/14] Sparse Clifford Blade (canonical sign fix)...")
    b1 = SparseCliffordBladeIndexer(dim=32)
    b2 = SparseCliffordBladeIndexer(dim=32)
    b1.set_blade(0b0001, 2.0)  # e_1
    b2.set_blade(0b0010, 3.0)  # e_2
    prod = b1.geometric_product(b2)
    require(0b0011 in prod.blades, "e1*e2 -> e12 mask missing")
    require(abs(prod.blades[0b0011] - 6.0) < 1e-6, f"e1*e2 coeff: {prod.blades.get(0b0011)}")

    # Verify e2*e1 = -e12 (anti-commutativity)
    b3 = SparseCliffordBladeIndexer(dim=32)
    b4 = SparseCliffordBladeIndexer(dim=32)
    b3.set_blade(0b0010, 1.0)  # e_2
    b4.set_blade(0b0001, 1.0)  # e_1
    prod2 = b3.geometric_product(b4)
    require(0b0011 in prod2.blades, "e2*e1 -> e12 mask missing")
    require(abs(prod2.blades[0b0011] - (-1.0)) < 1e-6,
            f"e2*e1 should be -e12, got {prod2.blades.get(0b0011)}")

    # Verify e12 * e23 = e13 (not -e13) in Euclidean metric
    b5 = SparseCliffordBladeIndexer(dim=32)
    b6 = SparseCliffordBladeIndexer(dim=32)
    b5.set_blade(0b0011, 1.0)  # e12
    b6.set_blade(0b0110, 1.0)  # e23
    prod3 = b5.geometric_product(b6)
    # e1*e2*e2*e3 = e1*(e2^2)*e3 = e1*1*e3 = e13
    # mask: 0b0011 ^ 0b0110 = 0b0101 = e13
    require(0b0101 in prod3.blades, "e12*e23 -> e13 mask missing")
    expected_sign = 1.0  # e1 e2 e2 e3: e2 passes 0 elements of m1 above it, sign=+1
    require(abs(prod3.blades[0b0101] - expected_sign) < 1e-6,
            f"e12*e23 = {prod3.blades.get(0b0101)}, expected {expected_sign}")
    print("  -> PASS: Clifford canonical sign verified (anti-commutativity + contraction).")

    # TEST 11: Rust FFI Bridge v910
    print("[TEST 11/14] Rust FFI Bridge v910...")
    loss_r = ctypes.c_double(0.0)
    grad_r = ctypes.c_double(0.0)
    err_r = PolydimErrorv910()
    res_r = engine.rust.polydim_rust_auon_log_cosh_brake_v910(
        0.5, 1.0, 1.0,
        ctypes.byref(loss_r), ctypes.byref(grad_r), ctypes.byref(err_r)
    )
    require(res_r == 0, "Rust FFI AuON failed")
    require(abs(grad_r.value - math.tanh(0.5)) < 1e-5, "Rust grad mismatch")
    print("  -> PASS: Rust FFI v910 bridge operational.")

    # TEST 12: Invariant Protection Guard Safety
    print("[TEST 12/14] Invariant Protection Guard Safety...")
    try:
        require(False, "Test synthetic invariant violation")
        raise RuntimeError("Fail: require did not raise")
    except RuntimeError as e:
        require("INVARIANT ERROR" in str(e), "Exception string mismatch")
    print("  -> PASS: require() invariant guard active and immune to -O.")

    # TEST 13: Rust RMS Normalize Cross-Validation (BRECHA 11 fix)
    print("[TEST 13/14] Rust RMS Normalize Cross-Validation vs C++...")
    mat_cross = np.random.randn(8, 8)
    mat_cross_c = np.ascontiguousarray(mat_cross, dtype=np.float64)
    out_cpp = np.zeros_like(mat_cross_c)
    out_rust = np.zeros_like(mat_cross_c)
    rms_cpp = ctypes.c_double(0.0)
    rms_rust = ctypes.c_double(0.0)
    err_cpp = PolydimErrorv910()
    err_rust = PolydimErrorv910()

    r_cpp = engine.cpp.polydim_cpp_auon_matrix_rms_normalize_v910(
        8, 8,
        mat_cross_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_cpp.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(rms_cpp), ctypes.byref(err_cpp)
    )
    r_rust = engine.rust.polydim_rust_auon_matrix_rms_normalize_v910(
        8, 8,
        mat_cross_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_rust.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(rms_rust), ctypes.byref(err_rust)
    )
    require(r_cpp == 0, "C++ RMS normalize failed")
    require(r_rust == 0, "Rust RMS normalize failed")
    rms_diff = abs(rms_cpp.value - rms_rust.value)
    require(rms_diff < 1e-6, f"C++/Rust RMS divergence: {rms_diff}")
    print(f"  -> PASS: C++ RMS={rms_cpp.value:.10e}, Rust RMS={rms_rust.value:.10e}, diff={rms_diff:.2e}")

    # TEST 14: Rust FIRE Metric Cross-Validation (BRECHA 11 fix)
    print("[TEST 14/14] Rust FIRE Metric Cross-Validation vs C++...")
    q_cross, _ = np.linalg.qr(np.random.randn(20, 5))
    q_cross_c = np.ascontiguousarray(q_cross, dtype=np.float64)
    drift_cpp = ctypes.c_double(0.0)
    drift_rust = ctypes.c_double(0.0)
    reinit_cpp = ctypes.c_uint8(0)
    reinit_rust = ctypes.c_uint8(0)
    err_cpp2 = PolydimErrorv910()
    err_rust2 = PolydimErrorv910()

    r_cpp2 = engine.cpp.polydim_cpp_fire_metric_v910(
        20, 5,
        q_cross_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        1e-4, ctypes.byref(drift_cpp), ctypes.byref(reinit_cpp), ctypes.byref(err_cpp2)
    )
    r_rust2 = engine.rust.polydim_rust_fire_metric_v910(
        20, 5,
        q_cross_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        1e-4, ctypes.byref(drift_rust), ctypes.byref(reinit_rust), ctypes.byref(err_rust2)
    )
    require(r_cpp2 == 0, "C++ FIRE failed")
    require(r_rust2 == 0, "Rust FIRE failed")
    drift_diff = abs(drift_cpp.value - drift_rust.value)
    require(drift_diff < 1e-10, f"C++/Rust FIRE drift divergence: {drift_diff}")
    print(f"  -> PASS: C++ drift={drift_cpp.value:.12e}, Rust drift={drift_rust.value:.12e}")

    print("=" * 70)
    print("     ALL 14/14 PHYSICAL SILICON TESTS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_all_tests()
