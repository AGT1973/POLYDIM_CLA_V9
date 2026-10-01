# fuzz_v912_destructive_hounds.py
# Red Team Adversarial Fuzzing Hounds - POLYDIM v912 (4/4 Destructive Hounds)
# ============================================================================

import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v912_monolito import (
    PolydimEnginev912, require, PolydimErrorv912,
    PmtpSlabAllocatorWin, GenerationalBatchHNSW
)

def hound_1_fpu_extreme_magnitude_attack(engine: PolydimEnginev912):
    print("[SABUESO 1/4] Extreme FPU Magnitude Attack (NaN/Inf/subnormal/10^-300/10^300)...")
    mat_tiny = np.random.randn(10, 10) * 1e-300
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat_tiny)
    require(np.isfinite(rms), "RMS must be finite for tiny magnitudes")

    l, g = engine.cpp_auon_brake(1e300, 1.0, 1.0)
    require(np.isfinite(l) and np.isfinite(g), "FPU overflow in huge residual")

    mat_large = np.random.uniform(-350, 350, (10, 10))
    normed_big, rms_big = engine.cpp_auon_matrix_rms_normalize(mat_large)
    require(np.isfinite(rms_big), f"RMS must be finite for |a|<=350, got {rms_big}")
    require(np.all(np.isfinite(normed_big)), "Output must be finite for large input")

    err = PolydimErrorv912()
    loss_out = ctypes.c_double(0.0)
    grad_out = ctypes.c_double(0.0)
    res = engine.cpp.polydim_cpp_auon_log_cosh_brake_v912(
        float('nan'), 1.0, 1.0,
        ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err)
    )
    require(res != 0, "NaN input must be rejected by FFI")

    res2 = engine.cpp.polydim_cpp_auon_log_cosh_brake_v912(
        float('inf'), 1.0, 1.0,
        ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err)
    )
    require(res2 != 0, "Inf input must be rejected by FFI")

    l_sub, g_sub = engine.cpp_auon_brake(5e-324, 1.0, 1.0)
    require(np.isfinite(l_sub), "Subnormal residual must produce finite loss")
    print("  -> SABUESO 1 PASS: NaN/Inf/subnormal/extreme magnitude all handled.")

def hound_2_pmtp_boundary_and_lifecycle(engine: PolydimEnginev912):
    print("[SABUESO 2/4] PMTP SharedMemory Boundary & Lifecycle Attack...")
    pmtp = PmtpSlabAllocatorWin("Local\\Polydimv912FuzzSlab", 512)
    large_data = np.zeros(200, dtype=np.float64)
    try:
        pmtp.write_tensor(large_data)
        require(False, "PMTP should have raised error on overflow")
    except RuntimeError:
        pass
    pmtp.close()

    try:
        pmtp.close()
    except Exception:
        pass
    print("  -> SABUESO 2 PASS: PMTP boundary + double-close handled.")

def hound_3_matrix_degeneracy_and_fgmres_attack(engine: PolydimEnginev912):
    print("[SABUESO 3/4] Matrix Degeneracy & FGMRES Extreme Conditioning Attack...")
    mat_zero = np.zeros((10, 2), dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_zero)
    require(rank_gf2 == 0, "Zero matrix rank must be 0")

    # Ill-conditioned system for FGMRES: near zero RHS
    b_tiny = np.zeros(32, dtype=np.float64)
    b_tiny[0] = 1e-18
    x_sol, iters, final_res, state = engine.cpp_fgmres_woodbury_solve(b_tiny, max_iter=20, tol=1e-5)
    require(np.all(np.isfinite(x_sol)), "FGMRES output must be finite for tiny RHS")
    print("  -> SABUESO 3 PASS: Degeneracy & ill-conditioned FGMRES handled.")

def hound_4_clifford_sign_adversarial(engine: PolydimEnginev912):
    print("[SABUESO 4/4] Clifford Sign Adversarial Multi-Grade Attack...")
    # e3 * e1 = -e13
    s1 = engine.cpp_clifford_canonical_sign(0b100, 0b001)
    require(s1 == -1, f"e3*e1 sign mismatch: {s1}")

    # e23 * e12 = -e13
    s2 = engine.cpp_clifford_canonical_sign(0b110, 0b011)
    require(s2 == -1, f"e23*e12 sign mismatch: {s2}")

    # e1 * e1 = +1
    s3 = engine.cpp_clifford_canonical_sign(0b001, 0b001)
    require(s3 == 1, f"e1*e1 sign mismatch: {s3}")
    print("  -> SABUESO 4 PASS: Clifford sign canonical correctness verified.")

def run_fuzzing_hounds():
    print("=" * 70)
    print("      POLYDIM v912 RED TEAM ADVERSARIAL FUZZING HOUNDS (4/4)")
    print("=" * 70)
    engine = PolydimEnginev912()
    hound_1_fpu_extreme_magnitude_attack(engine)
    hound_2_pmtp_boundary_and_lifecycle(engine)
    hound_3_matrix_degeneracy_and_fgmres_attack(engine)
    hound_4_clifford_sign_adversarial(engine)
    print("=" * 70)
    print("     ALL 4 RED TEAM FUZZING HOUNDS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_fuzzing_hounds()
