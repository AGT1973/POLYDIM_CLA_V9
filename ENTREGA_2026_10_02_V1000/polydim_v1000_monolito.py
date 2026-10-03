# ============================================================================
# POLYDIM MONOLITO V1000 (SERIE 1000 GÉNESIS QUINCUAGESIMAL CERTIFICADA - HITO 100)
# ============================================================================

import ctypes
import numpy as np
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

# Add MinGW bin dir for libgomp/libwinpthread
mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
if os.path.exists(mingw_bin) and hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(mingw_bin)
    except Exception:
        pass

# C++ and Rust DLL Paths
_cpp_dll_path = os.path.join(_DIR, "kernel_cpp_v1000.dll")
_rust_dll_path = os.path.join(_DIR, "kernel_rust_v1000.dll")

_cpp_lib = None
_rust_lib = None

class NativeKernelError(RuntimeError):
    """Raised when native C++/Rust kernel returns a non-zero error code."""
    pass

if os.path.exists(_cpp_dll_path):
    try:
        _cpp_lib = ctypes.CDLL(_cpp_dll_path)
        # Pre-configure C++ argtypes and restypes
        if hasattr(_cpp_lib, "polydim_spherical_vlasov_poisson_step_v1000"):
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_calogero_sutherland_integrals_v1000"):
            _cpp_lib.polydim_calogero_sutherland_integrals_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_calogero_sutherland_integrals_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_wen_yin_stiefel_retraction_v1000"):
            _cpp_lib.polydim_wen_yin_stiefel_retraction_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_wen_yin_stiefel_retraction_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_nambu_integrator_v1000"):
            _cpp_lib.polydim_nambu_integrator_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_nambu_integrator_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_e8_lattice_quantize_v1000"):
            _cpp_lib.polydim_e8_lattice_quantize_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32
            ]
            _cpp_lib.polydim_e8_lattice_quantize_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_marsden_weinstein_reduction_v1000"):
            _cpp_lib.polydim_marsden_weinstein_reduction_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32
            ]
            _cpp_lib.polydim_marsden_weinstein_reduction_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_wilczek_zee_holonomy_v1000"):
            _cpp_lib.polydim_wilczek_zee_holonomy_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_int32
            ]
            _cpp_lib.polydim_wilczek_zee_holonomy_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_parallel_transport_householder_v1000"):
            _cpp_lib.polydim_parallel_transport_householder_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32
            ]
            _cpp_lib.polydim_parallel_transport_householder_v1000.restype = ctypes.c_int32

        if hasattr(_cpp_lib, "polydim_mobius_addition_v1000"):
            _cpp_lib.polydim_mobius_addition_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_mobius_addition_v1000.restype = ctypes.c_int32
    except Exception as e:
        print(f"[POLYDIM V1000 WARN] Could not load C++ DLL: {e}", file=sys.stderr)

if os.path.exists(_rust_dll_path):
    try:
        _rust_lib = ctypes.CDLL(_rust_dll_path)
        # Pre-configure Rust argtypes and restypes
        if hasattr(_rust_lib, "polydim_robbins_siegmund_conformal_v1000"):
            _rust_lib.polydim_robbins_siegmund_conformal_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_float, ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_robbins_siegmund_conformal_v1000.restype = ctypes.c_int32

        if hasattr(_rust_lib, "polydim_matrix_freedman_tropp_v1000"):
            _rust_lib.polydim_matrix_freedman_tropp_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.POINTER(ctypes.c_float)
            ]
            _rust_lib.polydim_matrix_freedman_tropp_v1000.restype = ctypes.c_int32

        if hasattr(_rust_lib, "polydim_qemd_sift_v1000"):
            _rust_lib.polydim_qemd_sift_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_qemd_sift_v1000.restype = ctypes.c_int32

        if hasattr(_rust_lib, "polydim_betti1_rips_v1000"):
            _rust_lib.polydim_betti1_rips_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _rust_lib.polydim_betti1_rips_v1000.restype = ctypes.c_int32

        if hasattr(_rust_lib, "polydim_clifford_rotor_spin_v1000"):
            _rust_lib.polydim_clifford_rotor_spin_v1000.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float,
                ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_clifford_rotor_spin_v1000.restype = ctypes.c_int32
    except Exception as e:
        print(f"[POLYDIM V1000 WARN] Could not load Rust DLL: {e}", file=sys.stderr)


class PolydimV1000Engine:
    """Master engine for POLYDIM V1000 native low-level operations."""

    @staticmethod
    def spherical_vlasov_poisson_step(pos: np.ndarray, mom: np.ndarray, grad_phi: np.ndarray, dt: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
        pos = np.ascontiguousarray(pos, dtype=np.float32)
        mom = np.ascontiguousarray(mom, dtype=np.float32)
        grad_phi = np.ascontiguousarray(grad_phi, dtype=np.float32)
        out_pos = np.zeros_like(pos)
        out_mom = np.zeros_like(mom)
        N, D = pos.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_spherical_vlasov_poisson_step_v1000"):
            res = _cpp_lib.polydim_spherical_vlasov_poisson_step_v1000(
                pos.ctypes.data_as(ctypes.c_void_p),
                mom.ctypes.data_as(ctypes.c_void_p),
                grad_phi.ctypes.data_as(ctypes.c_void_p),
                out_pos.ctypes.data_as(ctypes.c_void_p),
                out_mom.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_int32(D),
                ctypes.c_float(dt)
            )
            if res == 0:
                return out_pos, out_mom
            raise NativeKernelError(f"C++ spherical_vlasov_poisson_step failed with exit code {res}")

        # Python fallback
        for i in range(N):
            x = pos[i]
            p = mom[i]
            g = grad_phi[i]
            dot_gx = np.dot(g, x)
            p_norm_sq = np.dot(p, p)
            force = -(g - dot_gx * x) - p_norm_sq * x
            p_new = p + dt * force
            x_new = x + dt * p_new
            x_new = x_new / max(1e-12, np.linalg.norm(x_new))
            p_new = p_new - np.dot(x_new, p_new) * x_new
            out_pos[i] = x_new
            out_mom[i] = p_new
        return out_pos, out_mom

    @staticmethod
    def calogero_sutherland_integrals(positions: np.ndarray, momenta: np.ndarray, g_coupling: float = 1.0) -> np.ndarray:
        positions = np.ascontiguousarray(positions, dtype=np.float32)
        momenta = np.ascontiguousarray(momenta, dtype=np.float32)
        out_integrals = np.zeros(2, dtype=np.float32)
        N = positions.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_calogero_sutherland_integrals_v1000"):
            res = _cpp_lib.polydim_calogero_sutherland_integrals_v1000(
                positions.ctypes.data_as(ctypes.c_void_p),
                momenta.ctypes.data_as(ctypes.c_void_p),
                out_integrals.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_float(g_coupling)
            )
            if res == 0:
                return out_integrals
            raise NativeKernelError(f"C++ calogero_sutherland_integrals failed with exit code {res}")

        # Exact SOTA Python fallback: I_1 = \sum p_j, I_2 = 1/2 \sum p_j^2 + g^2 \sum_{j < k} cot^2(q_j - q_k)
        out_integrals[0] = float(np.sum(momenta))
        sum_p2 = float(np.sum(momenta ** 2))
        sum_pot = 0.0
        g2 = float(g_coupling ** 2)
        for j in range(N):
            for k in range(j + 1, N):
                diff = positions[j] - positions[k]
                sin_v = np.sin(diff)
                if abs(sin_v) > 1e-6:
                    cot_v = np.cos(diff) / sin_v
                    sum_pot += g2 * (cot_v ** 2)
        out_integrals[1] = 0.5 * sum_p2 + sum_pot
        return out_integrals

    @staticmethod
    def wen_yin_stiefel_retract(X: np.ndarray, G: np.ndarray, tau: float = 0.1) -> np.ndarray:
        return PolydimV1000Engine.wen_yin_stiefel_retraction(X, G, tau)

    @staticmethod
    def wen_yin_stiefel_retraction(X: np.ndarray, G: np.ndarray, tau: float = 0.1) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        G = np.ascontiguousarray(G, dtype=np.float32)
        out_X = np.zeros_like(X)
        D, K = X.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_wen_yin_stiefel_retraction_v1000"):
            res = _cpp_lib.polydim_wen_yin_stiefel_retraction_v1000(
                X.ctypes.data_as(ctypes.c_void_p),
                G.ctypes.data_as(ctypes.c_void_p),
                out_X.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_int32(K),
                ctypes.c_float(tau)
            )
            if res == 0:
                return out_X
            raise NativeKernelError(f"C++ wen_yin_stiefel_retraction failed with exit code {res}")

        # Exact SOTA Python solve: (I - tau/2 A) M = (I + tau/2 A)
        A = G.T @ X - X.T @ G
        I_k = np.eye(K, dtype=np.float64)
        A_d = A.astype(np.float64)
        LHS = I_k - 0.5 * tau * A_d
        RHS = I_k + 0.5 * tau * A_d
        M = np.linalg.solve(LHS, RHS)
        out = (X.astype(np.float64) @ M).astype(np.float32)
        for c in range(K):
            norm = np.linalg.norm(out[:, c])
            out[:, c] /= max(1e-12, norm)
        return out

    @staticmethod
    def nambu_step(x: np.ndarray, grad_V: np.ndarray, dt: float = 0.01) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        grad_V = np.ascontiguousarray(grad_V, dtype=np.float32)
        out_x = np.zeros_like(x)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_nambu_integrator_v1000"):
            res = _cpp_lib.polydim_nambu_integrator_v1000(
                x.ctypes.data_as(ctypes.c_void_p),
                grad_V.ctypes.data_as(ctypes.c_void_p),
                out_x.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_float(dt)
            )
            if res == 0:
                return out_x
            raise NativeKernelError(f"C++ nambu_step failed with exit code {res}")

        # Python fallback
        out = np.zeros_like(x)
        for i in range(D):
            j = (i + 1) % D
            k = (i + 2) % D
            bracket = x[j] * grad_V[k] - x[k] * grad_V[j]
            out[i] = x[i] + dt * bracket
        norm = np.linalg.norm(out)
        return out / max(1e-12, norm)

    @staticmethod
    def e8_lattice_quantize(vec: np.ndarray) -> np.ndarray:
        return PolydimV1000Engine.e8_quantize(vec)

    @staticmethod
    def e8_quantize(vec: np.ndarray) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        out = np.zeros_like(vec)
        D = vec.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_e8_lattice_quantize_v1000") and (D % 8 == 0):
            res = _cpp_lib.polydim_e8_lattice_quantize_v1000(
                vec.ctypes.data_as(ctypes.c_void_p),
                out.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out
            raise NativeKernelError(f"C++ e8_lattice_quantize failed with exit code {res}")

        # Exact SOTA Conway-Sloane Python Fallback (D8+ union D8-)
        out = np.copy(vec)
        for b in range(D // 8):
            blk = vec[b*8:(b+1)*8]
            # Coset 0: D8+
            f0 = np.round(blk)
            if int(np.sum(f0)) % 2 != 0:
                w0 = np.argmax(np.abs(blk - f0))
                f0[w0] += 1.0 if blk[w0] > f0[w0] else -1.0
            dist0 = np.sum((blk - f0) ** 2)

            # Coset 1: D8+ + 0.5*1
            shifted = blk - 0.5
            f1_s = np.round(shifted)
            if int(np.sum(f1_s)) % 2 != 0:
                w1 = np.argmax(np.abs(shifted - f1_s))
                f1_s[w1] += 1.0 if shifted[w1] > f1_s[w1] else -1.0
            f1 = f1_s + 0.5
            dist1 = np.sum((blk - f1) ** 2)

            out[b*8:(b+1)*8] = f1 if dist1 < dist0 else f0
        return out

    @staticmethod
    def marsden_weinstein_reduce(Q: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        Q = np.ascontiguousarray(Q, dtype=np.float32)
        P = np.ascontiguousarray(P, dtype=np.float32)
        out_Q = np.zeros_like(Q)
        out_P = np.zeros_like(P)
        D, K = Q.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_marsden_weinstein_reduction_v1000"):
            res = _cpp_lib.polydim_marsden_weinstein_reduction_v1000(
                Q.ctypes.data_as(ctypes.c_void_p),
                P.ctypes.data_as(ctypes.c_void_p),
                out_Q.ctypes.data_as(ctypes.c_void_p),
                out_P.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_int32(K)
            )
            if res == 0:
                return out_Q, out_P
            raise NativeKernelError(f"C++ marsden_weinstein_reduction failed with exit code {res}")

        J = Q.T @ P - P.T @ Q
        out_Q = np.copy(Q)
        out_P = P - 0.5 * (Q @ J)
        return out_Q, out_P

    @staticmethod
    def parallel_transport_householder(x: np.ndarray, y: np.ndarray, v: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        v = np.ascontiguousarray(v, dtype=np.float32)
        out_v = np.zeros_like(v)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_parallel_transport_householder_v1000"):
            res = _cpp_lib.polydim_parallel_transport_householder_v1000(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                v.ctypes.data_as(ctypes.c_void_p),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_v
            raise NativeKernelError(f"C++ parallel_transport_householder failed with exit code {res}")

        # Python fallback
        dot_xy = float(np.dot(x, y))
        if dot_xy <= -0.999999:
            return -v
        factor = float(np.dot(x + y, v)) / (1.0 + dot_xy)
        return v - factor * (x + y)

    @staticmethod
    def mobius_addition(x: np.ndarray, y: np.ndarray, c: float = 1.0) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        out = np.zeros_like(x)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_mobius_addition_v1000"):
            res = _cpp_lib.polydim_mobius_addition_v1000(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                out.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_float(c)
            )
            if res == 0:
                return out
            raise NativeKernelError(f"C++ mobius_addition failed with exit code {res}")

        norm_x_sq = float(np.dot(x, x))
        norm_y_sq = float(np.dot(y, y))
        dot_xy = float(np.dot(x, y))
        denom = max(1e-12, 1.0 + 2.0 * c * dot_xy + c * c * norm_x_sq * norm_y_sq)
        alpha = 1.0 + 2.0 * c * dot_xy + c * norm_y_sq
        beta = 1.0 - c * norm_x_sq
        return (alpha * x + beta * y) / denom

    @staticmethod
    def robbins_siegmund(losses: np.ndarray, alpha: float = 0.1) -> np.ndarray:
        losses = np.ascontiguousarray(losses, dtype=np.float32)
        out_v = np.zeros_like(losses)
        T = losses.shape[0]

        if _rust_lib and hasattr(_rust_lib, "polydim_robbins_siegmund_conformal_v1000"):
            res = _rust_lib.polydim_robbins_siegmund_conformal_v1000(
                losses.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(alpha),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(T)
            )
            if res == 0:
                return out_v
            raise NativeKernelError(f"Rust robbins_siegmund failed with exit code {res}")

        v = 1.0
        for t in range(T):
            gamma = 1.0 / (t + 2)
            beta = 0.5 / (t + 2)
            psi = np.tanh(losses[t] - alpha)
            v = max(1e-6, (1.0 - gamma) * v + beta * psi)
            out_v[t] = v
        return out_v

    @staticmethod
    def matrix_freedman_tropp(matrices: np.ndarray, u_thresh: float = 0.5) -> float:
        matrices = np.ascontiguousarray(matrices, dtype=np.float32)
        T, D, _ = matrices.shape
        out_drift = ctypes.c_float(0.0)

        if _rust_lib and hasattr(_rust_lib, "polydim_matrix_freedman_tropp_v1000"):
            res = _rust_lib.polydim_matrix_freedman_tropp_v1000(
                matrices.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(T),
                ctypes.c_int32(D),
                ctypes.c_float(u_thresh),
                ctypes.byref(out_drift)
            )
            if res == 0:
                return out_drift.value
            raise NativeKernelError(f"Rust matrix_freedman_tropp failed with exit code {res}")

        traces = [np.trace(matrices[t]) for t in range(T)]
        avg = np.mean(traces) / D
        return 1.0 if avg > u_thresh else 0.0

    @staticmethod
    def betti1_rips(points: np.ndarray, eps: float = 0.5) -> int:
        points = np.ascontiguousarray(points, dtype=np.float32)
        N, D = points.shape

        if _rust_lib and hasattr(_rust_lib, "polydim_betti1_rips_v1000"):
            res = _rust_lib.polydim_betti1_rips_v1000(
                points.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_int32(D),
                ctypes.c_float(eps)
            )
            if res >= 0:
                return res
            raise NativeKernelError(f"Rust betti1_rips failed with exit code {res}")

        edges = 0
        for i in range(N):
            for j in range(i + 1, N):
                if np.linalg.norm(points[i] - points[j]) <= eps:
                    edges += 1
        return max(0, edges - N + 1)

    @staticmethod
    def clifford_rotor_spin(x: np.ndarray, u: np.ndarray, v: np.ndarray, theta: float = 0.1) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        u = np.ascontiguousarray(u, dtype=np.float32)
        v = np.ascontiguousarray(v, dtype=np.float32)
        out_x = np.zeros_like(x)
        D = x.shape[0]

        if _rust_lib and hasattr(_rust_lib, "polydim_clifford_rotor_spin_v1000"):
            res = _rust_lib.polydim_clifford_rotor_spin_v1000(
                x.ctypes.data_as(ctypes.c_void_p),
                u.ctypes.data_as(ctypes.c_void_p),
                v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(theta),
                out_x.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_x
            raise NativeKernelError(f"Rust clifford_rotor_spin failed with exit code {res}")

        c = np.cos(theta)
        s = np.sin(theta)
        dot_ux = np.dot(u, x)
        dot_vx = np.dot(v, x)
        out = x + (c - 1.0) * (dot_ux * u + dot_vx * v) + s * (dot_ux * v - dot_vx * u)
        norm = np.linalg.norm(out)
        return out / max(1e-12, norm)


class PolydimRustKernelV1000:
    """Convenience wrapper for Rust V1000 kernel methods."""
    def __init__(self):
        self.engine = PolydimV1000Engine
        self.lib = _rust_lib

    def robbins_siegmund(self, losses: np.ndarray, alpha: float = 0.1) -> np.ndarray:
        return self.engine.robbins_siegmund(losses, alpha)

    def matrix_freedman_tropp(self, matrices: np.ndarray, u_thresh: float = 0.5) -> float:
        return self.engine.matrix_freedman_tropp(matrices, u_thresh)

    def betti1_rips(self, points: np.ndarray, eps: float = 0.5) -> int:
        return self.engine.betti1_rips(points, eps)

    def clifford_rotor_spin(self, x: np.ndarray, u: np.ndarray, v: np.ndarray, theta: float = 0.1) -> np.ndarray:
        return self.engine.clifford_rotor_spin(x, u, v, theta)


class PolydimCppKernelV1000:
    """Convenience wrapper for C++ V1000 kernel methods."""
    def __init__(self):
        self.engine = PolydimV1000Engine
        self.lib = _cpp_lib

    def spherical_vlasov_poisson_step(self, pos: np.ndarray, mom: np.ndarray, grad_phi: np.ndarray, dt: float = 0.01):
        return self.engine.spherical_vlasov_poisson_step(pos, mom, grad_phi, dt)

    def calogero_sutherland_integrals(self, pos: np.ndarray, mom: np.ndarray, g_coupling: float = 1.0):
        return self.engine.calogero_sutherland_integrals(pos, mom, g_coupling)

    def wen_yin_stiefel_retract(self, X: np.ndarray, G: np.ndarray, tau: float = 0.01):
        return self.engine.wen_yin_stiefel_retract(X, G, tau)

    def wen_yin_stiefel_retraction(self, X: np.ndarray, G: np.ndarray, tau: float = 0.01):
        return self.engine.wen_yin_stiefel_retraction(X, G, tau)

    def nambu_step(self, x: np.ndarray, grad_V: np.ndarray, dt: float = 0.01):
        return self.engine.nambu_step(x, grad_V, dt)

    def e8_lattice_quantize(self, vec: np.ndarray):
        return self.engine.e8_lattice_quantize(vec)

    def e8_quantize(self, vec: np.ndarray):
        return self.engine.e8_quantize(vec)

    def marsden_weinstein_reduce(self, Q: np.ndarray, P: np.ndarray):
        return self.engine.marsden_weinstein_reduce(Q, P)

    def parallel_transport_householder(self, x: np.ndarray, y: np.ndarray, v: np.ndarray):
        return self.engine.parallel_transport_householder(x, y, v)

    def mobius_addition(self, x: np.ndarray, y: np.ndarray, c: float = 1.0):
        return self.engine.mobius_addition(x, y, c)


class PolydimMonolithV1000:
    """Unified Monolith instance for POLYDIM V1000."""
    def __init__(self):
        self.rust = PolydimRustKernelV1000()
        self.cpp = PolydimCppKernelV1000()
        self.engine = PolydimV1000Engine
