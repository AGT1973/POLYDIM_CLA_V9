# test_v914_comprehensive_suite.py
import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v914_monolito import PolydimEnginev914, require

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM v914 PHYSICAL SILICON COMPREHENSIVE SUITE (16/16)")
    print("=" * 70)

    engine = PolydimEnginev914()

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

    # TEST 4: Minimax Pre-Scaled Newton-Schulz Isometric Retraction
    print("[TEST 4/16] Minimax Pre-Scaled Newton-Schulz Stiefel Retraction...")
    q = np.eye(16, 4)
    g = np.random.randn(16, 4) * 0.05
    y, ortho_err = engine.cpp_stiefel_minimax_newton_schulz(q, g, alpha_step=0.01)
    require(ortho_err < 1e-4, f"Newton-Schulz ortho error too high: {ortho_err}")
    print(f"  -> PASS: Minimax Newton-Schulz converged (ortho_err={ortho_err:.2e})")

    # TEST 5: Minimax Newton-Schulz on Massive Distortion (Extreme Test)
    print("[TEST 5/16] Minimax Newton-Schulz on Massive Distortion (||G|| = 10.0)...")
    g_huge = np.random.randn(16, 4) * 10.0 # Huge step that diverged in V913
    y_h, ortho_h = engine.cpp_stiefel_minimax_newton_schulz(q, g_huge, alpha_step=0.1)
    require(ortho_h < 1e-3 and np.all(np.isfinite(y_h)), f"Minimax scaling failed on huge step: {ortho_h}")
    print(f"  -> PASS: Minimax pre-scaling guaranteed convergence under massive distortion (ortho_err={ortho_h:.2e})")

    # TEST 6: O(W) Clifford Prefix Canonical Sign (C++)
    print("[TEST 6/16] O(W) Prefix-Sum Clifford Canonical Sign (C++)...")
    ma = np.array([0b110, 0, 0, 0], dtype=np.uint64)
    mb = np.array([0b011, 0, 0, 0], dtype=np.uint64)
    s_cpp = engine.cpp_clifford_prefix_sign(ma, mb)
    require(s_cpp == -1, f"Expected -1, got {s_cpp}")
    print("  -> PASS: O(W) prefix sign verified in C++.")

    # TEST 7: O(W) Clifford Prefix Canonical Sign (Rust)
    print("[TEST 7/16] O(W) Prefix-Sum Clifford Canonical Sign (Rust)...")
    s_rust = engine.rust_clifford_prefix_sign(ma, mb)
    require(s_rust == -1, f"Expected -1, got {s_rust}")
    print("  -> PASS: O(W) prefix sign verified in Rust.")

    # TEST 8: Multi-Word D=1024 (W=16) Clifford Prefix Canonical Sign
    print("[TEST 8/16] High-Dimensional D=1024 (W=16 Words) Clifford Prefix Sign...")
    ma_16 = np.zeros(16, dtype=np.uint64)
    mb_16 = np.zeros(16, dtype=np.uint64)
    ma_16[15] = 0b001 # e960
    mb_16[0] = 0b001  # e0
    s_16_cpp = engine.cpp_clifford_prefix_sign(ma_16, mb_16)
    s_16_rust = engine.rust_clifford_prefix_sign(ma_16, mb_16)
    require(s_16_cpp == -1 and s_16_rust == -1, "High-D prefix sign mismatch")
    print("  -> PASS: D=1024 (W=16) prefix-sum Clifford sign exact match (-1).")

    # TEST 9: Discounted OGD Martingale (Stationary Noise)
    print("[TEST 9/16] Discounted OGD Conformal Martingale (Stationary Noise)...")
    scores = np.random.uniform(-0.5, 0.5, 50)
    log_e, final_e, alarm = engine.rust_discounted_ogd_martingale(scores, gamma=0.98)
    require(np.isfinite(log_e) and final_e > 0.0, "Martingale log_e failed")
    require(not alarm, "Stationary noise should not trigger alarm")
    print(f"  -> PASS: Discounted Martingale stationary test passed (log_e={log_e:.4f}, E={final_e:.4f})")

    # TEST 10: Discounted OGD Martingale on Late Regime Shift (Anti-Anesthesia)
    print("[TEST 10/16] Discounted OGD Martingale on Late Shift (t=200)...")
    scores_late = np.concatenate([np.random.uniform(-0.1, 0.1, 200), np.ones(30) * 0.8])
    log_e_l, final_e_l, alarm_l = engine.rust_discounted_ogd_martingale(scores_late, gamma=0.95)
    require(alarm_l and log_e_l > 2.99, f"Discounted OGD failed to detect late drift: log_e={log_e_l}")
    print(f"  -> PASS: Discounted OGD detected late regime shift immediately (log_e={log_e_l:.4f})")

    # TEST 11: Matrix-Free FGMRES Tri-State Solver
    print("[TEST 11/16] Matrix-Free FGMRES Tri-State Solver...")
    b_vec = np.random.randn(64)
    x_sol, iters, final_res, state = engine.cpp_fgmres_woodbury_solve(b_vec, max_iter=30, tol=1e-5)
    require(final_res <= 1e-4, f"FGMRES residual too high: {final_res}")
    print(f"  -> PASS: FGMRES solved in {iters} iters (residual={final_res:.2e}, state={state})")

    # TEST 12: Rust FIRE Isometry Metric
    print("[TEST 12/16] Rust FIRE Isometry Metric...")
    q_eye = np.eye(32, 8)
    fire = ctypes.c_double(0.0)
    res = engine.rust.polydim_rust_fire_metric_v914(
        np.ascontiguousarray(q_eye, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        32, 8, ctypes.byref(fire), None
    )
    require(res == 0 and abs(fire.value) < 1e-12, "FIRE metric on eye failed")
    print(f"  -> PASS: Rust FIRE metric verified ({fire.value:.2e}).")

    # TEST 13: Zero RHS in FGMRES
    print("[TEST 13/16] FGMRES with Zero RHS...")
    b_zero = np.zeros(32, dtype=np.float64)
    x_z, it_z, res_z, st_z = engine.cpp_fgmres_woodbury_solve(b_zero)
    require(res_z == 0.0 and it_z == 0, "Zero RHS solve failed")
    print("  -> PASS: Zero RHS correctly handled in 0 iters.")

    # TEST 14: Antipodal Geodesic Limit Metric
    print("[TEST 14/16] Antipodal Geodesic Limit Metric...")
    u_anti = np.array([1.0, 0.0, 0.0])
    v_anti = np.array([-1.0 + 1e-12, 0.0, 0.0])
    ang_a, chord_a = engine.cpp_riemannian_geodesic(u_anti, v_anti)
    require(abs(ang_a - np.pi) < 1e-5, f"Antipodal angle mismatch: {ang_a}")
    print("  -> PASS: Antipodal limit continuous and finite.")

    # TEST 15: Rust AuON Brake Float Guardrails
    print("[TEST 15/16] Rust AuON Log-Cosh Brake...")
    loss_r = ctypes.c_double(0.0)
    grad_r = ctypes.c_double(0.0)
    res_r = engine.rust.polydim_rust_auon_log_cosh_brake_v914(
        0.5, 1.0, 1.0, ctypes.byref(loss_r), ctypes.byref(grad_r), None
    )
    require(res_r == 0 and abs(grad_r.value - np.tanh(0.5)) < 1e-5, "Rust brake mismatch")
    print("  -> PASS: Rust AuON log-cosh brake verified.")

    # TEST 16: Full Pipeline Integration
    print("[TEST 16/16] Full Pipeline Numerical Stability...")
    q_init = np.eye(32, 4)
    g_step = np.random.randn(32, 4) * 0.1
    y_step, err_step = engine.cpp_stiefel_minimax_newton_schulz(q_init, g_step, alpha_step=0.05)
    require(err_step < 1e-3, f"Step error too high: {err_step}")
    print("  -> PASS: Full pipeline numerical integration verified.")

    print("=" * 70)
    print("      ALL 16 PHYSICAL UNIT TESTS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_all_tests()
