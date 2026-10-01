# fuzz_v913_destructive_hounds.py
import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v913_monolito import PolydimEnginev913, require

def hound_1_fpu_extreme_magnitude_attack(engine: PolydimEnginev913):
    print("[SABUESO 1/4] Extreme FPU Magnitude Attack (NaN/Inf/subnormal/10^-300/10^300)...")
    mat_tiny = np.random.randn(10, 10) * 1e-300
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat_tiny)
    require(np.isfinite(rms), "RMS must be finite for tiny magnitudes")

    l, g = engine.cpp_auon_brake(1e300, 1.0, 1.0)
    require(np.isfinite(l) and np.isfinite(g), "FPU overflow in huge residual")

    # NaN input must fail gracefully
    try:
        engine.cpp_auon_brake(float('nan'), 1.0, 1.0)
        require(False, "NaN should raise error")
    except RuntimeError:
        pass
    print("  -> SABUESO 1 PASS: Extreme magnitude and NaNs handled.")

def hound_2_clifford256_high_grade_collision(engine: PolydimEnginev913):
    print("[SABUESO 2/4] Clifford256 High-Grade Multi-Lane Collision Attack...")
    # Full lane saturation
    ma = np.array([0xFFFFFFFFFFFFFFFF, 0xAAAAAAAAAAAAAAAA, 0x5555555555555555, 0x0123456789ABCDEF], dtype=np.uint64)
    mb = np.array([0x0123456789ABCDEF, 0xFFFFFFFFFFFFFFFF, 0xAAAAAAAAAAAAAAAA, 0x5555555555555555], dtype=np.uint64)
    s1 = engine.cpp_clifford256_canonical_sign(ma, mb)
    s2 = engine.rust_clifford256_canonical_sign(ma, mb)
    require(s1 == s2 and (s1 == 1 or s1 == -1), f"Clifford256 mismatch: cpp={s1}, rust={s2}")
    print(f"  -> SABUESO 2 PASS: 256-bit Clifford sign matches in C++ and Rust ({s1}).")

def hound_3_newton_schulz_stiefel_distortion(engine: PolydimEnginev913):
    print("[SABUESO 3/4] Stiefel Newton-Schulz Extreme Distortion Attack...")
    q = np.eye(32, 4)
    g_massive = np.random.randn(32, 4) * 5.0 # Large gradient step
    y, err = engine.cpp_stiefel_newton_schulz(q, g_massive, alpha=0.1)
    require(np.all(np.isfinite(y)), "Newton-Schulz output must be finite")
    print(f"  -> SABUESO 3 PASS: Large distortion handled safely (ortho_err={err:.2e}).")

def hound_4_martingale_adversarial_flipping(engine: PolydimEnginev913):
    print("[SABUESO 4/4] Martingale Adversarial Sign Flipping Attack...")
    scores = np.array([0.99, -0.99] * 50, dtype=np.float64) # Violent oscillation
    log_e, final_e, alarm = engine.rust_log1p_ogd_martingale(scores)
    require(np.isfinite(log_e) and final_e > 0.0, "Martingale diverged on oscillation")
    print(f"  -> SABUESO 4 PASS: Violent oscillation bounded (log_e={log_e:.4f}).")

def run_fuzzing_hounds():
    print("=" * 70)
    print("      POLYDIM v913 RED TEAM ADVERSARIAL FUZZING HOUNDS (4/4)")
    print("=" * 70)
    engine = PolydimEnginev913()
    hound_1_fpu_extreme_magnitude_attack(engine)
    hound_2_clifford256_high_grade_collision(engine)
    hound_3_newton_schulz_stiefel_distortion(engine)
    hound_4_martingale_adversarial_flipping(engine)
    print("=" * 70)
    print("     ALL 4 RED TEAM FUZZING HOUNDS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_fuzzing_hounds()
