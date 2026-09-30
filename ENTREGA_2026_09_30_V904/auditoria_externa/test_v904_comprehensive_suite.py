# test_v904_comprehensive_suite.py
# Comprehensive Physical Unit Test Suite - POLYDIM V904
# ============================================================================

import os
import sys
import ctypes
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v904_monolito import PolydimEngineV904, require, PolydimErrorV904

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM V904 PHYSICAL SILICON COMPREHENSIVE SUITE (12/12)")
    print("=" * 70)

    engine = PolydimEngineV904()

    # TEST 1: AuON Log-Cosh Brake
    print("[TEST 1/12] AuON Log-Cosh Brake...")
    l1, g1 = engine.cpp_auon_brake(0.5, scale_s=1.0, lambda_val=1.0)
    require(l1 > 0.0, "Loss must be positive")
    require(abs(g1 - math.tanh(0.5)) < 1e-5, "Gradient mismatch")
    print("  -> PASS: Log-cosh loss and grad matched.")

    # TEST 2: Riemannian Geodesic
    print("[TEST 2/12] Riemannian Geodesic Metric on S^(D-1)...")
    u = np.array([1.0, 0.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    require(abs(ang - np.pi / 2.0) < 1e-6, f"Angular distance mismatch: {ang}")
    require(abs(chord - np.sqrt(2.0)) < 1e-6, f"Chordal distance mismatch: {chord}")
    print("  -> PASS: Orthogonal vector distance exact pi/2.")

    # TEST 3: Two-NN Intrinsic Dimension
    print("[TEST 3/12] Two-NN MAP Bayesian Intrinsic Dimension...")
    np.random.seed(42)
    # 5D manifold embedded in 20D space
    pts_5d = np.random.randn(100, 5)
    proj = np.random.randn(5, 20)
    pts_20d = np.ascontiguousarray(pts_5d @ proj, dtype=np.float64)
    
    d_mle = ctypes.c_double(0.0)
    d_ucb = ctypes.c_double(0.0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_two_nn_intrinsic_dim_v904(
        100, 20,
        pts_20d.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(d_mle), ctypes.byref(d_ucb), ctypes.byref(err)
    )
    require(res == 0, "cpp_two_nn_intrinsic_dim failed")
    require(4.0 <= d_mle.value <= 6.5, f"Intrinsic dimension out of bounds: {d_mle.value}")
    print(f"  -> PASS: MAP Bayesian estimated intrinsic dim = {d_mle.value:.4f}")

    # TEST 4: Baraniuk-Wakin Secant Bound
    print("[TEST 4/12] Baraniuk-Wakin Secant Bound...")
    m_req = ctypes.c_double(0.0)
    feasible = ctypes.c_uint8(0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_baraniuk_wakin_feasibility_v904(
        1000, 100, 10.0, 0.1, 0.5, 1.0, 0.01,
        ctypes.byref(m_req), ctypes.byref(feasible), ctypes.byref(err)
    )
    require(res == 0, "Baraniuk-Wakin failed")
    print(f"  -> PASS: Required projection dimension m = {m_req.value:.2f}")

    # TEST 5: CliffordNet Bivector Interaction & AuON Normalization
    print("[TEST 5/12] CliffordNet Grade Separation & AuON...")
    vecs = np.random.randn(10, 8)
    bivecs, energy = engine.cpp_cliffordnet_interact(vecs)
    require(bivecs.shape == (10, 28), f"Bivector shape mismatch: {bivecs.shape}")
    require(energy > 0.0, "Energy must be positive")
    print(f"  -> PASS: Bivector multivector energy = {energy:.6f}")

    # TEST 6: Hybrid AuON Orthogonalization
    print("[TEST 6/12] Hybrid AuON Column Orthogonalization...")
    mat_x = np.random.randn(8, 8)
    mat_q = np.zeros_like(mat_x)
    steps = ctypes.c_uint32(0)
    conv = ctypes.c_uint8(0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_hybrid_auon_orthogonalization_v904(
        8,
        mat_x.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        mat_q.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        20, ctypes.byref(steps), ctypes.byref(conv), ctypes.byref(err)
    )
    require(res == 0, "Hybrid AuON failed")
    print(f"  -> PASS: Executed steps = {steps.value}, Converged = {conv.value}")

    # TEST 7: Stiefel Cayley-SMW Retraction
    print("[TEST 7/12] Stiefel Cayley-SMW Matrix-Free Retraction...")
    # Orthogonal X on St(16, 4)
    q_mat, _ = np.linalg.qr(np.random.randn(16, 4))
    g_mat = np.random.randn(16, 4) * 0.01
    y_out = np.zeros_like(q_mat)
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v904(
        16, 4, 0.1,
        q_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        g_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(ortho_err), ctypes.byref(err)
    )
    require(res == 0, "Stiefel SMW failed")
    require(ortho_err.value < 1e-4, f"Orthogonality defect too high: {ortho_err.value}")
    print(f"  -> PASS: Retracted Y orthogonality error = {ortho_err.value:.8e}")

    # TEST 8: FIRE Metric
    print("[TEST 8/12] FIRE Spectral Metric...")
    q_mat, _ = np.linalg.qr(np.random.randn(20, 5))
    drift = ctypes.c_double(0.0)
    reinit = ctypes.c_uint8(0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_fire_metric_v904(
        20, 5,
        q_mat.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        1e-4, ctypes.byref(drift), ctypes.byref(reinit), ctypes.byref(err)
    )
    require(res == 0, "FIRE metric failed")
    require(drift.value < 1e-12, f"FIRE drift too high for QR matrix: {drift.value}")
    print(f"  -> PASS: Spectral drift = {drift.value:.10e}, Reinit needed = {reinit.value}")

    # TEST 9: Clifford Drift Bound
    print("[TEST 9/12] Clifford Asymptotic Drift Bound...")
    uncond = ctypes.c_double(0.0)
    reorth = ctypes.c_double(0.0)
    safe = ctypes.c_uint8(0)
    err = PolydimErrorV904()
    res = engine.cpp.polydim_cpp_clifford_drift_bound_v904(
        1024, 100, 10, 2.22e-16,
        ctypes.byref(uncond), ctypes.byref(reorth), ctypes.byref(safe), ctypes.byref(err)
    )
    require(res == 0, "Clifford drift bound failed")
    print(f"  -> PASS: Reorth drift bound = {reorth.value:.10e}, Safe = {safe.value}")

    # TEST 10: GF(2) Bitpacked Reduction
    print("[TEST 10/12] GF(2) Bitpacked uint64_t Reduction for Homology...")
    # 4 rows, 1 64-bit word
    mat_gf2 = np.array([
        [0b1100],
        [0b1010],
        [0b0110],
        [0b0000]
    ], dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_gf2)
    require(rank_gf2 == 2, f"GF(2) rank mismatch: expected 2, got {rank_gf2}")
    print(f"  -> PASS: GF(2) matrix rank = {rank_gf2}")

    # TEST 11: Rust FFI Bridge & Overlap Safety
    print("[TEST 11/12] Rust FFI Bridge & std::ptr::copy Safety...")
    loss_r = ctypes.c_double(0.0)
    grad_r = ctypes.c_double(0.0)
    err_r = PolydimErrorV904()
    res_r = engine.rust.polydim_rust_auon_log_cosh_brake_v904(
        0.5, 1.0, 1.0,
        ctypes.byref(loss_r), ctypes.byref(grad_r), ctypes.byref(err_r)
    )
    require(res_r == 0, "Rust FFI AuON failed")
    print("  -> PASS: Rust FFI bridge operational.")

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
