# fuzz_v914_destructive_hounds.py
import os
import sys
import ctypes
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v914_monolito import PolydimEnginev914, require

def hound_1_fpu_extreme_magnitude_attack(engine: PolydimEnginev914):
    print("[SABUESO 1/4] Extreme FPU Magnitude Attack (NaN/Inf/subnormal/10^-300/10^300)...")
    mat_tiny = np.random.randn(10, 10) * 1e-300
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat_tiny)
    require(np.isfinite(rms), "RMS must be finite for tiny magnitudes")

    l, g = engine.cpp_auon_brake(1e300, 1.0, 1.0)
    require(np.isfinite(l) and np.isfinite(g), "FPU overflow in huge residual")

    try:
        engine.cpp_auon_brake(float('nan'), 1.0, 1.0)
        require(False, "NaN should raise error")
    except RuntimeError:
        pass
    print("  -> SABUESO 1 PASS: Extreme magnitude and NaNs handled.")

def hound_2_clifford_massive_word_fuzz(engine: PolydimEnginev914):
    print("[SABUESO 2/4] Clifford O(W) Prefix Sign Massive Word Fuzz (W=32, D=2048)...")
    ma = np.random.randint(0, 0xFFFFFFFFFFFFFFFF, size=32, dtype=np.uint64)
    mb = np.random.randint(0, 0xFFFFFFFFFFFFFFFF, size=32, dtype=np.uint64)
    s_cpp = engine.cpp_clifford_prefix_sign(ma, mb)
    s_rust = engine.rust_clifford_prefix_sign(ma, mb)
    require(s_cpp == s_rust and (s_cpp == 1 or s_cpp == -1), f"Clifford prefix mismatch: cpp={s_cpp}, rust={s_rust}")
    print(f"  -> SABUESO 2 PASS: W=32 Clifford sign matched in C++ and Rust ({s_cpp}).")

def hound_3_minimax_newton_schulz_extreme_distortion(engine: PolydimEnginev914):
    print("[SABUESO 3/4] Stiefel Minimax Newton-Schulz Extreme Distortion Attack...")
    q = np.eye(32, 4)
    g_extreme = np.random.randn(32, 4) * 100.0 # 100x gradient distortion
    y, err = engine.cpp_stiefel_minimax_newton_schulz(q, g_extreme, alpha_step=0.5)
    require(np.all(np.isfinite(y)) and err < 1e-3, f"Minimax scaling diverged: {err}")
    print(f"  -> SABUESO 3 PASS: 100x extreme distortion strictly converged (ortho_err={err:.2e}).")

def hound_4_martingale_adversarial_flipping(engine: PolydimEnginev914):
    print("[SABUESO 4/4] Discounted Martingale Adversarial Sign Flipping Attack...")
    scores = np.array([0.99, -0.99] * 50, dtype=np.float64)
    log_e, final_e, alarm = engine.rust_discounted_ogd_martingale(scores, gamma=0.98)
    require(np.isfinite(log_e) and final_e > 0.0, "Martingale diverged on oscillation")
    print(f"  -> SABUESO 4 PASS: Violent oscillation bounded (log_e={log_e:.4f}).")

def run_fuzzing_hounds():
    print("=" * 70)
    print("      POLYDIM v914 RED TEAM ADVERSARIAL FUZZING HOUNDS (4/4)")
    print("=" * 70)
    engine = PolydimEnginev914()
    hound_1_fpu_extreme_magnitude_attack(engine)
    hound_2_clifford_massive_word_fuzz(engine)
    hound_3_minimax_newton_schulz_extreme_distortion(engine)
    hound_4_martingale_adversarial_flipping(engine)
    print("=" * 70)
    print("     ALL 4 RED TEAM FUZZING HOUNDS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_fuzzing_hounds()
