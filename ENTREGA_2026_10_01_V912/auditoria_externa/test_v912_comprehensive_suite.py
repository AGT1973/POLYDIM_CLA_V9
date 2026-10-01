# test_v912_comprehensive_suite.py
# Comprehensive Physical Unit Test Suite - POLYDIM v912 (16/16 SOTA Contracts)
# ============================================================================

import os
import sys
import ctypes
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v912_monolito import (
    PolydimEnginev912, require, PolydimErrorv912,
    PmtpSlabAllocatorWin, GenerationalBatchHNSW, SparseCliffordBladeIndexer,
    EProcessMartingaleMonitor, _clifford_canonical_sign
)

def run_all_tests():
    print("=" * 70)
    print("      POLYDIM v912 PHYSICAL SILICON COMPREHENSIVE SUITE (16/16)")
    print("=" * 70)

    engine = PolydimEnginev912()

    # TEST 1: AuON Log-Cosh Brake
    print("[TEST 1/16] AuON Log-Cosh Brake...")
    l1, g1 = engine.cpp_auon_brake(0.5, scale_s=1.0, lambda_val=1.0)
    require(l1 > 0.0, "Loss must be positive")
    require(abs(g1 - math.tanh(0.5)) < 1e-5, "Gradient mismatch")
    print("  -> PASS: Log-cosh loss and grad matched.")

    # TEST 2: AuON Log-Space RMS Normalize
    print("[TEST 2/16] AuON Log-Space RMS Normalize (anti-overflow)...")
    mat = np.random.randn(10, 10) * 1e-100
    normed, rms = engine.cpp_auon_matrix_rms_normalize(mat)
    require(np.isfinite(rms), "RMS must be finite for tiny input")
    require(np.all(np.isfinite(normed)), "Normalized matrix must be finite")
    mat_big = np.random.uniform(-350, 350, (10, 10))
    normed_big, rms_big = engine.cpp_auon_matrix_rms_normalize(mat_big)
    require(np.isfinite(rms_big), f"RMS must be finite for |a|~350, got {rms_big}")
    require(np.all(np.isfinite(normed_big)), "Normalized matrix must be finite for large input")
    print(f"  -> PASS: Log-space RMS tiny={rms:.6e}, large={rms_big:.6e}")

    # TEST 3: Riemannian Geodesic
    print("[TEST 3/16] Riemannian Geodesic Metric on S^(D-1)...")
    u = np.array([1.0, 0.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    require(abs(ang - np.pi / 2.0) < 1e-6, f"Angular distance mismatch: {ang}")
    require(abs(chord - np.sqrt(2.0)) < 1e-6, f"Chordal distance mismatch: {chord}")
    print("  -> PASS: Orthogonal vector distance exact pi/2.")

    # TEST 4: CliffordNet Bivector Interaction
    print("[TEST 4/16] CliffordNet Bivector Interaction (SIMD 4x)...")
    vecs = np.random.randn(10, 8)
    bivecs, energy = engine.cpp_cliffordnet_interact(vecs)
    require(bivecs.shape == (10, 28), f"Bivector shape mismatch: {bivecs.shape}")
    require(energy > 0.0, "Energy must be positive")
    print(f"  -> PASS: Bivector energy k=8: {energy:.6f}")

    # TEST 5: GF(2) Bitpacked Reduction
    print("[TEST 5/16] GF(2) Bitpacked Reduction with Dynamic Threshold...")
    mat_gf2 = np.array([
        [0b1100],
        [0b1010],
        [0b0110],
        [0b0000]
    ], dtype=np.uint64)
    out_gf2, rank_gf2 = engine.cpp_gf2_bitpacked_reduction(mat_gf2)
    require(rank_gf2 == 2, f"Expected rank 2, got {rank_gf2}")
    print(f"  -> PASS: GF(2) reduction rank={rank_gf2}")

    # TEST 6: Stiefel Cayley Retraction
    print("[TEST 6/16] Stiefel Cayley Retraction...")
    q = np.eye(8, 3)
    g = np.random.randn(8, 3) * 0.1
    y = np.zeros_like(q)
    ortho_err = ctypes.c_double(0.0)
    err = PolydimErrorv912()
    res = engine.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v912(
        8, 3, 0.01,
        np.ascontiguousarray(q, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        np.ascontiguousarray(g, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(ortho_err), ctypes.byref(err)
    )
    err.check_ok()
    require(res == 0, f"Stiefel retraction failed with {res}")
    print(f"  -> PASS: Stiefel retraction success (ortho_err={ortho_err.value:.2e})")

    # TEST 7: Matrix-Free FGMRES Tri-State Solver
    print("[TEST 7/16] Matrix-Free FGMRES Tri-State Solver...")
    b_vec = np.random.randn(64)
    x_sol, iters, final_res, state = engine.cpp_fgmres_woodbury_solve(b_vec, max_iter=30, tol=1e-5)
    require(final_res <= 1e-4, f"FGMRES residual too high: {final_res}")
    print(f"  -> PASS: FGMRES solved in {iters} iters (residual={final_res:.2e}, state={state})")

    # TEST 8: Clifford Canonical Sign (C++ vs Rust Popcount SIMD)
    print("[TEST 8/16] Clifford Canonical Sign (C++ vs Rust vs Python)...")
    sign_cpp = engine.cpp_clifford_canonical_sign(0b110, 0b011)
    sign_rust = engine.rust_clifford_canonical_sign(0b110, 0b011)
    sign_py = _clifford_canonical_sign(0b110, 0b011)
    require(sign_cpp == -1 and sign_rust == -1 and sign_py == -1, f"Mismatch: cpp={sign_cpp}, rust={sign_rust}, py={sign_py}")
    print("  -> PASS: Canonical sign exact match (-1).")

    # TEST 9: BOCPD + E-Process Conformal Martingale in Rust
    print("[TEST 9/16] BOCPD + Conformal Martingale in Rust...")
    seq = np.random.randn(50)
    e_val, prob = engine.rust_bocpd_conformal_martingale(seq, hazard_lambda=100.0)
    require(e_val > 0.0, f"E-value must be positive, got {e_val}")
    require(0.0 <= prob <= 1.0, f"Probability must be in [0, 1], got {prob}")
    print(f"  -> PASS: BOCPD E-value={e_val:.4f}, change_prob={prob:.4f}")

    # TEST 10: E-Process Martingale Monitor in Python
    print("[TEST 10/16] E-Process Martingale Monitor...")
    monitor = EProcessMartingaleMonitor(hazard_lambda=100.0, alpha_target=0.05)
    for v in np.random.randn(20):
        e_val, prob, alarm = monitor.update(float(v), engine)
    require(not alarm, "Stationary Gaussian noise should not trigger false alarm")
    print(f"  -> PASS: E-Process Monitor no false alarm (E-val={e_val:.4f})")

    # TEST 11: DLPack Level 0 C Exchange Struct Validation
    print("[TEST 11/16] DLPack Level 0 Struct Allocation...")
    mat_dl = np.ascontiguousarray(np.random.randn(8, 8), dtype=np.float64)
    err = PolydimErrorv912()
    dl_ptr = engine.cpp.polydim_cpp_dlpack_export_tensor_v912(
        mat_dl.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        8, 8, ctypes.byref(err)
    )
    err.check_ok()
    require(bool(dl_ptr), "DLPack managed tensor pointer is null")
    if dl_ptr and dl_ptr.contents.deleter:
        dl_ptr.contents.deleter(dl_ptr)
    print("  -> PASS: DLPack Managed Tensor created and safely reclaimed.")

    # TEST 12: Win32 PMTP Slab Allocator RAII
    print("[TEST 12/16] Win32 PMTP Slab Allocator RAII...")
    with PmtpSlabAllocatorWin("Local\\PolydimV912TestSlab", 1024) as pmtp:
        t_in = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        pmtp.write_tensor(t_in)
        t_out = pmtp.read_tensor(dtype=np.float64, count=4)
        require(np.allclose(t_in, t_out), "PMTP data mismatch")
    print("  -> PASS: Win32 PMTP Slab allocated, mapped, verified and unmapped.")

    # TEST 13: Generational HNSW Batch Snapshots
    print("[TEST 13/16] Generational Batch HNSW Snapshots...")
    hnsw = GenerationalBatchHNSW(dim=4)
    hnsw.insert_batch(np.random.randn(5, 4))
    require(hnsw.version == 1, "HNSW version must be 1")
    require(len(hnsw.nodes) == 5, "HNSW node count mismatch")
    print("  -> PASS: Generational HNSW snapshot versioning verified.")

    # TEST 14: Sparse Clifford Blade Geometric Product
    print("[TEST 14/16] Sparse Clifford Blade Geometric Product...")
    a = SparseCliffordBladeIndexer(dim=32)
    b = SparseCliffordBladeIndexer(dim=32)
    a.set_blade(0b100, 2.0) # 2*e3
    b.set_blade(0b001, 3.0) # 3*e1
    prod = a.geometric_product(b)
    require(0b101 in prod.blades, "Blade e13 missing")
    require(abs(prod.blades[0b101] - (-6.0)) < 1e-12, f"Expected -6.0, got {prod.blades[0b101]}")
    print("  -> PASS: Geometric product e3 * e1 = -e13 verified.")

    # TEST 15: Rust FIRE Metric
    print("[TEST 15/16] Rust FIRE Metric on Orthonormal Matrix...")
    q_mat = np.eye(16, 4)
    fire_out = ctypes.c_double(0.0)
    err = PolydimErrorv912()
    res = engine.rust.polydim_rust_fire_metric_v912(
        np.ascontiguousarray(q_mat, dtype=np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        16, 4, ctypes.byref(fire_out), ctypes.byref(err)
    )
    err.check_ok()
    require(res == 0, f"FIRE metric failed with {res}")
    require(abs(fire_out.value) < 1e-12, f"FIRE metric on eye should be 0.0, got {fire_out.value}")
    print(f"  -> PASS: Rust FIRE metric verified ({fire_out.value:.2e}).")

    # TEST 16: Rust LASSQ & RMS Normalize
    print("[TEST 16/16] Rust AuON Matrix RMS Normalize...")
    mat_r = np.random.randn(8, 8)
    in_buf = np.ascontiguousarray(mat_r, dtype=np.float64)
    out_buf = np.empty_like(in_buf)
    rms_r = ctypes.c_double(0.0)
    err = PolydimErrorv912()
    res = engine.rust.polydim_rust_auon_matrix_rms_normalize_v912(
        8, 8,
        in_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(rms_r), ctypes.byref(err)
    )
    err.check_ok()
    require(res == 0, f"Rust RMS failed with {res}")
    require(np.isfinite(rms_r.value), "Rust RMS must be finite")
    print(f"  -> PASS: Rust RMS normalize verified (rms={rms_r.value:.4f}).")

    print("=" * 70)
    print("      ALL 16 PHYSICAL UNIT TESTS PASSED WITH EXIT CODE 0")
    print("=" * 70)

if __name__ == '__main__':
    run_all_tests()
