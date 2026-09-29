# ============================================================================
# POLYDIM V900 — KAGGLE CLOUD GPU BENCHMARK (NVIDIA TESLA T4 / P100 / A100)
# Serie 900 Axiomatic Verification: Cayley-Stiefel SMW, Clifford Cl(D), Order-5 NS
# ============================================================================

import os
import sys
import time
import json
import torch
import numpy as np

def run_v900_gpu_benchmark():
    print("=" * 80)
    print("🚀 POLYDIM V900 — KAGGLE CLOUD GPU BENCHMARK (SERIE 900)")
    print("=" * 80)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    print(f"Device: {device} | GPU: {gpu_name} (Count: {gpu_count})")

    results = {
        "version": "V900",
        "device": str(device),
        "gpu_name": gpu_name,
        "gpu_count": gpu_count,
        "timestamp": time.time(),
        "benchmarks": []
    }

    # ------------------------------------------------------------------------
    # BENCHMARK 1: Cayley-Stiefel Matrix-Free SMW Retraction O(DK^2 + K^3)
    # ------------------------------------------------------------------------
    print("\n[BENCHMARK 1] Cayley-Stiefel Matrix-Free Retraction on St(D, K) (FP64 GPU)")
    stiefel_configs = [
        (10000, 16, 0.01),
        (100000, 32, 0.005),
        (1000000, 32, 0.001),
        (5000000, 16, 0.0005)
    ]

    for D, K, tau in stiefel_configs:
        try:
            # Generar X ortonormal en St(D, K) vía QR
            raw = torch.randn(D, K, dtype=torch.float64, device=device)
            X, _ = torch.linalg.qr(raw)
            X = X[:, :K]
            G = torch.randn(D, K, dtype=torch.float64, device=device) * 0.1

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t0 = time.perf_counter()

            # Bloques KxK: A = X^T G, B = X^T X, C = G^T G
            A = torch.mm(X.t(), G)
            B = torch.mm(X.t(), X)
            C = torch.mm(G.t(), G)

            # Sistema 2K x 2K: M = I_2K - (tau/2) * [A, -B; C, -A^T]
            half_tau = 0.5 * tau
            I_k = torch.eye(K, dtype=torch.float64, device=device)
            M_top = torch.cat([I_k - half_tau * A, half_tau * B], dim=1)
            M_bot = torch.cat([-half_tau * C, I_k + half_tau * A.t()], dim=1)
            M = torch.cat([M_top, M_bot], dim=0)

            # RHS = [B; A^T]
            RHS = torch.cat([B, A.t()], dim=0)

            # Resolver M * Z = RHS
            Z = torch.linalg.solve(M, RHS)
            Z1 = Z[:K, :]
            Z2 = Z[K:, :]

            # Reconstruir Y = X + tau * (G * Z1 - X * Z2)
            Y = X + tau * (torch.mm(G, Z1) - torch.mm(X, Z2))

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t1 = time.perf_counter()

            dt_ms = (t1 - t0) * 1000.0
            ortho_err = torch.norm(torch.mm(Y.t(), Y) - I_k, p='fro').item() / np.sqrt(K)

            print(f"  -> D = {D:>9,}, K = {K:>2}: Latency = {dt_ms:>8.3f} ms | Ortho Error = {ortho_err:>.3e}")
            results["benchmarks"].append({
                "name": "Stiefel_Cayley_SMW_GPU",
                "D": D,
                "K": K,
                "tau": tau,
                "latency_ms": dt_ms,
                "ortho_error": ortho_err
            })
        except Exception as e:
            print(f"  -> D = {D:,}, K = {K} FAILED: {e}")

    # ------------------------------------------------------------------------
    # BENCHMARK 2: Clifford Cl(D) Bivector Rotors in S^(D-1)
    # ------------------------------------------------------------------------
    print("\n[BENCHMARK 2] Clifford Cl(D) Bivector Rotors (D=10^6 to 10^7, P=128 planes)")
    clifford_dims = [100000, 1000000, 10000000]
    num_planes = 128

    for D in clifford_dims:
        try:
            v = torch.randn(D, dtype=torch.float64, device=device)
            v = v / torch.norm(v)

            # Índices de planos disjuntos
            u_idx = torch.arange(0, 2 * num_planes, 2, device=device)
            w_idx = torch.arange(1, 2 * num_planes, 2, device=device)
            angles = torch.rand(num_planes, dtype=torch.float64, device=device) * 2.0 * np.pi - np.pi

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t0 = time.perf_counter()

            v_out = v.clone()
            cos_t = torch.cos(angles)
            sin_t = torch.sin(angles)

            val_u = v[u_idx]
            val_w = v[w_idx]

            v_out[u_idx] = val_u * cos_t - val_w * sin_t
            v_out[w_idx] = val_u * sin_t + val_w * cos_t

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t1 = time.perf_counter()

            dt_ms = (t1 - t0) * 1000.0
            norm_in = torch.norm(v).item()
            norm_out = torch.norm(v_out).item()
            drift = abs(norm_out - norm_in)

            print(f"  -> D = {D:>10,}, P = {num_planes}: Latency = {dt_ms:>8.3f} ms | Norm Drift = {drift:>.3e}")
            results["benchmarks"].append({
                "name": "Clifford_Bivector_Rotor_GPU",
                "D": D,
                "num_planes": num_planes,
                "latency_ms": dt_ms,
                "norm_drift": drift
            })
        except Exception as e:
            print(f"  -> D = {D:,} FAILED: {e}")

    # ------------------------------------------------------------------------
    # BENCHMARK 3: Canonical Order-5 Padé Polar vs SVD Oracle
    # ------------------------------------------------------------------------
    print("\n[BENCHMARK 3] Canonical Order-5 Padé Polar vs SVD Oracle (N=256, 512, 1024)")
    for N in [256, 512, 1024]:
        try:
            A = torch.randn(N, N, dtype=torch.float64, device=device)
            # Pre-escalado por Power Iteration
            v_spec = torch.randn(N, dtype=torch.float64, device=device)
            for _ in range(4):
                v_spec = torch.mv(A, v_spec)
                v_spec = torch.mv(A.t(), v_spec)
                v_spec = v_spec / torch.norm(v_spec)
            sigma_max = torch.norm(torch.mv(A, v_spec)).item()
            Q = A / max(sigma_max, 1e-12)

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t0 = time.perf_counter()

            a_c = 15.0 / 8.0
            b_c = -10.0 / 8.0
            c_c = 3.0 / 8.0
            I_n = torch.eye(N, dtype=torch.float64, device=device)

            for step in range(8):
                R = torch.mm(Q, Q.t())
                R2 = torch.mm(R, R)
                M = a_c * I_n + b_c * R + c_c * R2
                Q = torch.mm(M, Q)

            torch.cuda.synchronize() if torch.cuda.is_available() else None
            t1 = time.perf_counter()

            dt_ms = (t1 - t0) * 1000.0
            iso_err = torch.norm(torch.mm(Q.t(), Q) - I_n, p=2).item()

            print(f"  -> N = {N:>4}: Latency = {dt_ms:>8.3f} ms | Isometry Error ||Q^T Q - I||_2 = {iso_err:>.3e}")
            results["benchmarks"].append({
                "name": "Order5_Pade_Polar_GPU",
                "N": N,
                "latency_ms": dt_ms,
                "isometry_error": iso_err
            })
        except Exception as e:
            print(f"  -> N = {N} FAILED: {e}")

    # Guardar resultados
    out_path = "v900_gpu_benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Benchmarks V900 completados y guardados en {out_path}")

if __name__ == "__main__":
    run_v900_gpu_benchmark()
