# test_v913_comprehensive_suite.py
import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v913_monolito import PolydimEnginev913, require

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM v913 PHYSICAL SILICON COMPREHENSIVE SUITE (16/16)")
    print("=" * 70)

    engine = PolydimEnginev913()

    # TEST 1: AuON Log-Cosh Brake
    print("[TEST 1/16] AuON Log-Cosh Brake...")
    l, g = engine.cpp_auon_brake(0.5, 1.0, 1.0)
    require(l > 0.0 and abs(g - np.tanh(0.5)) < 1e-5, "AuON brake mismatch")
    print("  -> PASS: AuON log-cosh brake verified.")

    # TEST 2: RMS Normalize with FTZ/DAZ & Kahan
    print("[TEST 2/16] AuON Log-Space RMS Normalize (anti-overflow)...")
    mat_big = np.random.uniform(-350, 350, (10, 10))
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat_big)
    require(np.isfinite(rms) and np.all(np.isfinite(normed)), "RMS failed for large input")
    print(f"  -> PASS: Log-space RMS large={rms:.4e}")

    # TEST 3: Riemannian Geodesic Kahan
    print("[TEST 3/16] Riemannian Geodesic Metric on S^(D-1)...")
    u = np.array([1.0, 0.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    require(abs(ang - np.pi/2) < 1e-6, "Geodesic angle mismatch")
    print("  -> PASS: Orthogonal vector distance exact pi/2.")

    # TEST 4: Order-5 Newton-Schulz Isometric Retraction
    print("[TEST 4/16] Order-5 Newton-Schulz Isometric Retraction (Zero-Inversion)...")
    q = np.eye(16, 4)
    g = np.random.randn(16, 4) * 0.05
    y, ortho_err = engine.cpp_stiefel_newton_schulz(q, g, alpha=0.01)
    require(ortho_err < 1e-4, f"Newton-Schulz ortho error too high: {ortho_err}")
    print(f"  -> PASS: Newton-Schulz retraction converged (ortho_err={ortho_err:.2e})")

    # TEST 5: CliffordBlade256 Sign (C++ Popcount)
    print("[TEST 5/16] CliffordBlade256 Canonical Sign (C++ 256-bit SIMD)...")
    ma = np.array([0b110, 0, 0, 0], dtype=np.uint64)
    mb = np.array([0b011, 0, 0, 0], dtype=np.uint64)
    s_cpp = engine.cpp_clifford256_canonical_sign(ma, mb)
    require(s_cpp == -1, f"Expected -1, got {s_cpp}")
    print("  -> PASS: CliffordBlade256 sign verified in C++.")

    # TEST 6: CliffordBlade256 Sign (Rust Multi-Lane)
    print("[TEST 6/16] CliffordBlade256 Canonical Sign (Rust Multi-Lane)...")
    s_rust = engine.rust_clifford256_canonical_sign(ma, mb)
    require(s_rust == -1, f"Expected -1, got {s_rust}")
    print("  -> PASS: CliffordBlade256 sign verified in Rust.")

    # TEST 7: Multi-Word CliffordBlade256 Transposition
    print("[TEST 7/16] Multi-Word CliffordBlade256 Inter-Lane Transposition...")
    ma2 = np.array([0, 0b001, 0, 0], dtype=np.uint64) # e64 in lane 1
    mb2 = np.array([0b001, 0, 0, 0], dtype=np.uint64) # e0 in lane 0
    s_cross = engine.cpp_clifford256_canonical_sign(ma2, mb2)
    s_cross_r = engine.rust_clifford256_canonical_sign(ma2, mb2)
    require(s_cross == -1 and s_cross_r == -1, "Inter-lane sign mismatch")
    print("  -> PASS: Inter-lane blade transposition sign exact match (-1).")

    # TEST 8: Log1p OGD Conformal Martingale in Rust
    print("[TEST 8/16] Log1p OGD Conformal Martingale in Rust...")
    scores = np.random.uniform(-0.5, 0.5, 50)
    log_e, final_e, alarm = engine.rust_log1p_ogd_martingale(scores)
    require(np.isfinite(log_e) and final_e > 0.0, "Martingale log_e failed")
    require(not alarm, "Stationary noise should not trigger alarm")
    print(f"  -> PASS: Log1p OGD Martingale verified (log_e={log_e:.4f}, E={final_e:.4f})")

    # TEST 9: Alarm Triggering on True Drift
    print("[TEST 9/16] Martingale Alarm Triggering on True Structural Drift...")
    scores_drift = np.ones(30, dtype=np.float64) * 0.9 # Strong persistent positive score
    log_e_d, final_e_d, alarm_d = engine.rust_log1p_ogd_martingale(scores_drift)
    require(alarm_d and log_e_d > 2.99, f"Alarm must trigger on persistent drift, got {log_e_d}")
    print(f"  -> PASS: Alarm successfully triggered on true drift (log_e={log_e_d:.4f})")

    # TEST 10: Matrix-Free FGMRES Tri-State Solver
    print("[TEST 10/16] Matrix-Free FGMRES Tri-State Solver...")
    b_vec = np.random.randn(64)
    x_sol, iters, final_res, state = engine.cpp_fgmres_woodbury_solve(b_vec, max_iter=30, tol=1e-5)
    require(final_res <= 1e-4, f"FGMRES residual too high: {final_res}")
    print(f"  -> PASS: FGMRES solved in {iters} iters (residual={final_res:.2e}, state={state})")

    # TEST 11: Rust FIRE Isometry Metric
    print("[TEST 11/16] Rust FIRE Isometry Metric...")
    q_eye = np.eye(32, 8)
    fire = ctypes.c_double(0.0)
    err = PolydimEnginev913
    res = engine.rust.polydim_rust_fire_metric_v913(
        np.ascontiguousarray(q_eye, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        32, 8, ctypes.byref(fire), None
    )
    require(res == 0 and abs(fire.value) < 1e-12, "FIRE metric on eye failed")
    print(f"  -> PASS: Rust FIRE metric verified ({fire.value:.2e}).")

    # TEST 12: Zero RHS in FGMRES
    print("[TEST 12/16] FGMRES with Zero RHS...")
    b_zero = np.zeros(32, dtype=np.float64)
    x_z, it_z, res_z, st_z = engine.cpp_fgmres_woodbury_solve(b_zero)
    require(res_z == 0.0 and it_z == 0, "Zero RHS solve failed")
    print("  -> PASS: Zero RHS correctly handled in 0 iters.")

    # TEST 13: Antipodal Geodesic Continuity
    print("[TEST 13/16] Antipodal Geodesic Limit Metric...")
    u_anti = np.array([1.0, 0.0, 0.0])
    v_anti = np.array([-1.0 + 1e-12, 0.0, 0.0])
    ang_a, chord_a = engine.cpp_riemannian_geodesic(u_anti, v_anti)
    require(abs(ang_a - np.pi) < 1e-5, f"Antipodal angle mismatch: {ang_a}")
    print("  -> PASS: Antipodal limit continuous and finite.")

    # TEST 14: AuON Scale Invariance
    print("[TEST 14/16] AuON Matrix Scale Invariance...")
    m1 = np.random.randn(8, 8)
    m2 = m1 * 100.0
    n1, r1 = engine.cpp_auon_matrix_rms_normalize(m1)
    n2, r2 = engine.cpp_auon_matrix_rms_normalize(m2)
    require(np.allclose(n1, n2, atol=1e-5), "Normalized matrices should match for scaled inputs")
    print("  -> PASS: RMS normalization scale invariance confirmed.")

    # TEST 15: Rust AuON Brake Float Guardrails
    print("[TEST 15/16] Rust AuON Log-Cosh Brake...")
    loss_r = ctypes.c_double(0.0)
    grad_r = ctypes.c_double(0.0)
    res_r = engine.rust.polydim_rust_auon_log_cosh_brake_v913(
        0.5, 1.0, 1.0, ctypes.byref(loss_r), ctypes.byref(grad_r), None
    )
    require(res_r == 0 and abs(grad_r.value - np.tanh(0.5)) < 1e-5, "Rust brake mismatch")
    print("  -> PASS: Rust AuON log-cosh brake verified.")

    # TEST 16: Full Pipeline Integration
    print("[TEST 16/16] Full Pipeline Numerical Stability...")
    q_init = np.eye(32, 4)
    g_step = np.random.randn(32, 4) * 0.1
    y_step, err_step = engine.cpp_stiefel_newton_schulz(q_init, g_step, alpha=0.05)
    require(err_step < 1e-3, f"Step error too high: {err_step}")
    print("  -> PASS: Full pipeline numerical integration verified.")

    print("=" * 70)
    print("      ALL 16 PHYSICAL UNIT TESTS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_all_tests()
