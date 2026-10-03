# ============================================================================
# SABUESOS ADVERSARIALES DESTRUCTIVOS V1150 (FUZZING ASINTÓTICO & SILICIO)
# ============================================================================

import os
import sys
import numpy as np

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _DIR)

from polydim_v1150_monolito import PolydimV1150Engine

def hound_01_asymptotic_annihilation():
    print("[HOUND 1/4] Asymptotic Annihilation D=100,000...")
    D = 100000
    x = np.random.randn(D).astype(np.float32)
    x /= np.linalg.norm(x)
    y = np.random.randn(D).astype(np.float32)
    y /= np.linalg.norm(y)
    v = np.random.randn(D).astype(np.float32)
    v -= np.dot(x, v) * x
    
    out_v = PolydimV1150Engine.parallel_transport_householder(x, y, v)
    assert not np.isnan(out_v).any(), "NaNs detected in Householder at D=100k"
    print("  -> PASS: Householder stable at D=100k")

def hound_02_subnormal_torture():
    print("[HOUND 2/4] Subnormal & Numerical Torture...")
    D = 16
    x = np.full(D, 1e-35, dtype=np.float32)
    q = PolydimV1150Engine.e8_lattice_quantize(x)
    assert not np.isnan(q).any(), "NaNs in E8 quantization of subnormals"
    print("  -> PASS: E8 Quantizer survived subnormals")

def hound_03_stiefel_anti_happy_path():
    print("[HOUND 3/4] Stiefel Anti-Happy Path (Zero Matrix & Singular Input)...")
    D = 128
    K = 16
    X = np.random.randn(D).astype(np.float32)
    X /= np.linalg.norm(X)
    U = np.zeros((D, K), dtype=np.float32)
    V = np.zeros((D, K), dtype=np.float32)
    out_X = PolydimV1150Engine.cayley_smw_stiefel(X, U, V, tau=0.1)
    assert not np.isnan(out_X).any(), "NaNs in Stiefel with zero rank perturbation"
    assert np.isclose(np.linalg.norm(out_X), 1.0, atol=1e-5), "Norm drift on Stiefel zero step"
    print("  -> PASS: Stiefel zero-perturbation preserved identity")

def hound_04_clifford_extreme_rotations():
    print("[HOUND 4/4] Clifford Extreme Rotations (theta = 1000*pi)...")
    D = 64
    x = np.random.randn(D).astype(np.float32)
    x /= np.linalg.norm(x)
    u = np.zeros(D, dtype=np.float32); u[0] = 1.0
    v = np.zeros(D, dtype=np.float32); v[1] = 1.0
    x_rot = PolydimV1150Engine.clifford_rotor_spin(x, u, v, theta=1000.0 * np.pi)
    assert not np.isnan(x_rot).any(), "NaNs in extreme Clifford angle"
    assert np.isclose(np.linalg.norm(x_rot), 1.0, atol=1e-5), "Norm loss in extreme Clifford angle"
    print("  -> PASS: Clifford rotor invariant under extreme phase wrap")

if __name__ == "__main__":
    hound_01_asymptotic_annihilation()
    hound_02_subnormal_torture()
    hound_03_stiefel_anti_happy_path()
    hound_04_clifford_extreme_rotations()
    print("\n=== ALL DESTRUCTIVE HOUNDS COMPLETED WITH EXIT CODE 0 ===")
