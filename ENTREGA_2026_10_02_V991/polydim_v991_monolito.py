# ============================================================================
# POLYDIM MONOLITO V991 (SERIE 900 HITO DECENAL CERTIFICADO)
# ============================================================================

import ctypes
import numpy as np
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
if os.path.exists(mingw_bin) and hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(mingw_bin)
    except Exception:
        pass

_cpp_dll_path = os.path.join(_DIR, "kernel_cpp_v991.dll")
_rust_dll_path = os.path.join(_DIR, "kernel_rust_v991.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_cpp_dll_path):
    try:
        _cpp_lib = ctypes.CDLL(_cpp_dll_path)
    except Exception as e:
        print(f"[POLYDIM V991 WARN] Could not load C++ DLL: {e}", file=sys.stderr)

if os.path.exists(_rust_dll_path):
    try:
        _rust_lib = ctypes.CDLL(_rust_dll_path)
    except Exception as e:
        print(f"[POLYDIM V991 WARN] Could not load Rust DLL: {e}", file=sys.stderr)


class PolydimV991Engine:
    """Master engine for POLYDIM V991 native low-level operations."""

    @staticmethod
    def spherical_vlasov_poisson_step(pos: np.ndarray, mom: np.ndarray, grad_phi: np.ndarray, dt: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
        pos = np.ascontiguousarray(pos, dtype=np.float32)
        mom = np.ascontiguousarray(mom, dtype=np.float32)
        grad_phi = np.ascontiguousarray(grad_phi, dtype=np.float32)
        out_pos = np.zeros_like(pos)
        out_mom = np.zeros_like(mom)
        N, D = pos.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_spherical_vlasov_poisson_step_v991"):
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v991.restype = ctypes.c_int32
            res = _cpp_lib.polydim_spherical_vlasov_poisson_step_v991(
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

        if _cpp_lib and hasattr(_cpp_lib, "polydim_calogero_sutherland_integrals_v991"):
            _cpp_lib.polydim_calogero_sutherland_integrals_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_calogero_sutherland_integrals_v991.restype = ctypes.c_int32
            res = _cpp_lib.polydim_calogero_sutherland_integrals_v991(
                positions.ctypes.data_as(ctypes.c_void_p),
                momenta.ctypes.data_as(ctypes.c_void_p),
                out_integrals.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_float(g_coupling)
            )
            if res == 0:
                return out_integrals

        L = np.diag(momenta).astype(np.complex64)
        for j in range(N):
            for k in range(N):
                if j != k:
                    diff = positions[j] - positions[k]
                    sin_v = np.sin(diff)
                    cot_v = np.cos(diff) / sin_v if abs(sin_v) > 1e-6 else 0.0
                    L[j, k] = 1j * g_coupling * cot_v
        out_integrals[0] = np.real(np.trace(L))
        out_integrals[1] = 0.5 * np.real(np.trace(L @ L))
        return out_integrals

    @staticmethod
    def cayley_smw_stiefel(X: np.ndarray, U: np.ndarray, V: np.ndarray) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        U = np.ascontiguousarray(U, dtype=np.float32)
        V = np.ascontiguousarray(V, dtype=np.float32)
        out_X = np.zeros_like(X)
        D = X.shape[0]
        K = U.shape[1]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_cayley_smw_stiefel_v991"):
            _cpp_lib.polydim_cayley_smw_stiefel_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32
            ]
            _cpp_lib.polydim_cayley_smw_stiefel_v991.restype = ctypes.c_int32
            res = _cpp_lib.polydim_cayley_smw_stiefel_v991(
                X.ctypes.data_as(ctypes.c_void_p),
                U.ctypes.data_as(ctypes.c_void_p),
                V.ctypes.data_as(ctypes.c_void_p),
                out_X.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_int32(K)
            )
            if res == 0:
                return out_X

        VtX = V.T @ X
        UtX = U.T @ X
        out = X - 2.0 * (U @ VtX) + 2.0 * (V @ UtX)
        norm = np.linalg.norm(out)
        return out / max(1e-12, norm)

    @staticmethod
    def parallel_transport_householder(x: np.ndarray, y: np.ndarray, v: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        v = np.ascontiguousarray(v, dtype=np.float32)
        out_v = np.zeros_like(v)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_parallel_transport_householder_v991"):
            _cpp_lib.polydim_parallel_transport_householder_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32
            ]
            _cpp_lib.polydim_parallel_transport_householder_v991.restype = ctypes.c_int32
            res = _cpp_lib.polydim_parallel_transport_householder_v991(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                v.ctypes.data_as(ctypes.c_void_p),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_v

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

        if _cpp_lib and hasattr(_cpp_lib, "polydim_mobius_addition_v991"):
            _cpp_lib.polydim_mobius_addition_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_mobius_addition_v991.restype = ctypes.c_int32
            res = _cpp_lib.polydim_mobius_addition_v991(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                out.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_float(c)
            )
            if res == 0:
                return out

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

        if _rust_lib and hasattr(_rust_lib, "polydim_robbins_siegmund_conformal_v991"):
            _rust_lib.polydim_robbins_siegmund_conformal_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_float, ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_robbins_siegmund_conformal_v991.restype = ctypes.c_int32
            res = _rust_lib.polydim_robbins_siegmund_conformal_v991(
                losses.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(alpha),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(T)
            )
            if res == 0:
                return out_v

        v = 1.0
        for t in range(T):
            gamma = 1.0 / (t + 2)
            beta = 0.5 / (t + 2)
            psi = np.tanh(losses[t] - alpha)
            v = max(1e-6, (1.0 - gamma) * v + beta * psi)
            out_v[t] = v
        return out_v

    @staticmethod
    def betti1_rips(points: np.ndarray, eps: float = 0.5) -> int:
        points = np.ascontiguousarray(points, dtype=np.float32)
        N, D = points.shape

        if _rust_lib and hasattr(_rust_lib, "polydim_betti1_rips_v991"):
            _rust_lib.polydim_betti1_rips_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _rust_lib.polydim_betti1_rips_v991.restype = ctypes.c_int32
            return _rust_lib.polydim_betti1_rips_v991(
                points.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_int32(D),
                ctypes.c_float(eps)
            )

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

        if _rust_lib and hasattr(_rust_lib, "polydim_clifford_rotor_spin_v991"):
            _rust_lib.polydim_clifford_rotor_spin_v991.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float,
                ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_clifford_rotor_spin_v991.restype = ctypes.c_int32
            res = _rust_lib.polydim_clifford_rotor_spin_v991(
                x.ctypes.data_as(ctypes.c_void_p),
                u.ctypes.data_as(ctypes.c_void_p),
                v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(theta),
                out_x.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_x

        c = np.cos(theta)
        s = np.sin(theta)
        dot_ux = np.dot(u, x)
        dot_vx = np.dot(v, x)
        out = x + (c - 1.0) * (dot_ux * u + dot_vx * v) + s * (dot_ux * v - dot_vx * u)
        norm = np.linalg.norm(out)
        return out / max(1e-12, norm)
