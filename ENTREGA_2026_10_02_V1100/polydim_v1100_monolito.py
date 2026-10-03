# ============================================================================
# POLYDIM MONOLITO V1101 (SERIE 900 HITO DECENAL CERTIFICADO - ZERO ALLOCATION)
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

_cpp_dll_path = os.path.join(_DIR, "kernel_cpp_v1100.dll")
_rust_dll_path = os.path.join(_DIR, "kernel_rust_v1100.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_cpp_dll_path):
    try:
        _cpp_lib = ctypes.CDLL(_cpp_dll_path)
    except Exception as e:
        print(f"[POLYDIM V1101 WARN] Could not load C++ DLL: {e}", file=sys.stderr)

if os.path.exists(_rust_dll_path):
    try:
        _rust_lib = ctypes.CDLL(_rust_dll_path)
    except Exception as e:
        print(f"[POLYDIM V1101 WARN] Could not load Rust DLL: {e}", file=sys.stderr)


class NativeKernelError(RuntimeError):
    """Raised when native C++ or Rust kernel returns non-zero error code."""
    pass


class PolydimV1100Engine:
    """Master engine for POLYDIM V1101 native low-level operations with zero-allocation buffers."""

    @staticmethod
    def spherical_vlasov_poisson_step(pos: np.ndarray, mom: np.ndarray, grad_phi: np.ndarray, dt: float = 0.01, out_pos: np.ndarray = None, out_mom: np.ndarray = None) -> tuple[np.ndarray, np.ndarray]:
        pos = np.ascontiguousarray(pos, dtype=np.float32)
        mom = np.ascontiguousarray(mom, dtype=np.float32)
        grad_phi = np.ascontiguousarray(grad_phi, dtype=np.float32)
        if out_pos is None:
            out_pos = np.zeros_like(pos)
        if out_mom is None:
            out_mom = np.zeros_like(mom)
        N, D = pos.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_spherical_vlasov_poisson_step_v1101"):
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_spherical_vlasov_poisson_step_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_spherical_vlasov_poisson_step_v1101(
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
            raise NativeKernelError(f"C++ spherical_vlasov_poisson_step failed with rc={res}")

        for i in range(N):
            x = pos[i]
            p = mom[i]
            g = grad_phi[i]
            dot_gx = np.dot(g, x)
            f_tan = -(g - dot_gx * x)
            p_mid = p + dt * f_tan
            p_mid -= np.dot(x, p_mid) * x
            w = np.linalg.norm(p_mid)
            theta = w * dt
            cos_t = np.cos(theta)
            sin_t = np.sin(theta)
            sin_div_w = sin_t / w if w > 1e-6 else dt
            out_pos[i] = x * cos_t + p_mid * sin_div_w
            out_mom[i] = -x * (w * sin_t) + p_mid * cos_t
            out_pos[i] /= max(1e-12, np.linalg.norm(out_pos[i]))
        return out_pos, out_mom

    @staticmethod
    def calogero_sutherland_integrals(positions: np.ndarray, momenta: np.ndarray, g_coupling: float = 1.0, out_integrals: np.ndarray = None) -> np.ndarray:
        positions = np.ascontiguousarray(positions, dtype=np.float32)
        momenta = np.ascontiguousarray(momenta, dtype=np.float32)
        if out_integrals is None:
            out_integrals = np.zeros(2, dtype=np.float32)
        N = positions.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_calogero_sutherland_integrals_v1101"):
            _cpp_lib.polydim_calogero_sutherland_integrals_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_calogero_sutherland_integrals_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_calogero_sutherland_integrals_v1101(
                positions.ctypes.data_as(ctypes.c_void_p),
                momenta.ctypes.data_as(ctypes.c_void_p),
                out_integrals.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(N),
                ctypes.c_float(g_coupling)
            )
            if res == 0:
                return out_integrals
            raise NativeKernelError(f"C++ calogero_sutherland_integrals failed with rc={res}")

        sum_p = np.sum(momenta)
        L_real = np.diag(momenta)
        L_imag = np.zeros((N, N), dtype=np.float32)
        for j in range(N):
            for k in range(N):
                if j != k:
                    diff = positions[j] - positions[k]
                    sin_val = np.sin(diff)
                    cot_val = np.cos(diff) / sin_val if abs(sin_val) > 1e-6 else 0.0
                    L_imag[j, k] = g_coupling * cot_val
        sum_l2 = np.sum(L_real**2 + L_imag**2)
        out_integrals[0] = sum_p
        out_integrals[1] = 0.5 * sum_l2
        return out_integrals

    @staticmethod
    def cayley_smw_stiefel(X: np.ndarray, U: np.ndarray, V: np.ndarray, tau: float = 0.01, out_X: np.ndarray = None) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        U = np.ascontiguousarray(U, dtype=np.float32)
        V = np.ascontiguousarray(V, dtype=np.float32)
        if out_X is None:
            out_X = np.zeros_like(X)
        D, K = U.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_cayley_smw_stiefel_v1101"):
            _cpp_lib.polydim_cayley_smw_stiefel_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_cayley_smw_stiefel_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_cayley_smw_stiefel_v1101(
                X.ctypes.data_as(ctypes.c_void_p),
                U.ctypes.data_as(ctypes.c_void_p),
                V.ctypes.data_as(ctypes.c_void_p),
                out_X.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_int32(K),
                ctypes.c_float(tau)
            )
            if res == 0:
                return out_X
            raise NativeKernelError(f"C++ cayley_smw_stiefel failed with rc={res}")

        c = tau * 0.5
        UV = np.hstack([U, V])
        VU = np.hstack([V, -U])
        A = np.dot(UV, VU.T)
        I_D = np.eye(D, dtype=np.float32)
        inv_mat = np.linalg.inv(I_D + c * A)
        res_mat = np.dot(inv_mat, I_D - c * A)
        out = np.dot(res_mat, X)
        out /= max(1e-12, np.linalg.norm(out))
        out_X[:] = out
        return out_X

    @staticmethod
    def e8_lattice_quantize(vec: np.ndarray, out_quant: np.ndarray = None) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        if out_quant is None:
            out_quant = np.zeros_like(vec)
        D = vec.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_e8_lattice_quantize_v1101"):
            _cpp_lib.polydim_e8_lattice_quantize_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32
            ]
            _cpp_lib.polydim_e8_lattice_quantize_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_e8_lattice_quantize_v1101(
                vec.ctypes.data_as(ctypes.c_void_p),
                out_quant.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_quant
            raise NativeKernelError(f"C++ e8_lattice_quantize failed with rc={res}")

        for b in range(D // 8):
            x = vec[b*8:(b+1)*8]
            f1 = np.round(x)
            if int(np.sum(f1)) % 2 != 0:
                idx = np.argmax(np.abs(x - f1))
                f1[idx] += 1.0 if x[idx] >= f1[idx] else -1.0
            
            f2_raw = np.round(x - 0.5)
            f2 = f2_raw + 0.5
            if int(np.sum(f2_raw)) % 2 != 0:
                idx = np.argmax(np.abs(x - 0.5 - f2_raw))
                f2[idx] += 1.0 if (x[idx] - 0.5) >= f2_raw[idx] else -1.0
            
            d1 = np.sum((x - f1)**2)
            d2 = np.sum((x - f2)**2)
            out_quant[b*8:(b+1)*8] = f1 if d1 <= d2 else f2
        return out_quant

    @staticmethod
    def parallel_transport_householder(x: np.ndarray, y: np.ndarray, v: np.ndarray, out_v: np.ndarray = None) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        v = np.ascontiguousarray(v, dtype=np.float32)
        if out_v is None:
            out_v = np.zeros_like(v)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_parallel_transport_householder_v1101"):
            _cpp_lib.polydim_parallel_transport_householder_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32
            ]
            _cpp_lib.polydim_parallel_transport_householder_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_parallel_transport_householder_v1101(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                v.ctypes.data_as(ctypes.c_void_p),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out_v
            raise NativeKernelError(f"C++ parallel_transport_householder failed with rc={res}")

        dot_xy = np.dot(x, y)
        if dot_xy <= -0.999999:
            out_v[:] = -v
            return out_v
        factor = np.dot(x + y, v) / (1.0 + dot_xy)
        out_v[:] = v - factor * (x + y)
        return out_v

    @staticmethod
    def mobius_addition(x: np.ndarray, y: np.ndarray, c: float = 1.0, out_res: np.ndarray = None) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        if out_res is None:
            out_res = np.zeros_like(x)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_mobius_addition_v1101"):
            _cpp_lib.polydim_mobius_addition_v1101.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_mobius_addition_v1101.restype = ctypes.c_int32
            res = _cpp_lib.polydim_mobius_addition_v1101(
                x.ctypes.data_as(ctypes.c_void_p),
                y.ctypes.data_as(ctypes.c_void_p),
                out_res.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(D),
                ctypes.c_float(c)
            )
            if res == 0:
                return out_res
            raise NativeKernelError(f"C++ mobius_addition failed with rc={res}")

        norm_x_sq = np.dot(x, x)
        norm_y_sq = np.dot(y, y)
        dot_xy = np.dot(x, y)
        denom = max(1e-12, 1.0 + 2.0 * c * dot_xy + c * c * norm_x_sq * norm_y_sq)
        alpha = 1.0 + 2.0 * c * dot_xy + c * norm_y_sq
        beta = 1.0 - c * norm_x_sq
        out_res[:] = (alpha * x + beta * y) / denom
        return out_res

    @staticmethod
    def robbins_siegmund_conformal(losses: np.ndarray, alpha: float = 0.1, out_v: np.ndarray = None) -> np.ndarray:
        losses = np.ascontiguousarray(losses, dtype=np.float32)
        t_len = losses.shape[0]
        if out_v is None:
            out_v = np.zeros(t_len, dtype=np.float32)

        if _rust_lib and hasattr(_rust_lib, "polydim_robbins_siegmund_conformal_v1100"):
            _rust_lib.polydim_robbins_siegmund_conformal_v1100.argtypes = [
                ctypes.c_void_p, ctypes.c_float, ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_robbins_siegmund_conformal_v1100.restype = ctypes.c_int32
            res = _rust_lib.polydim_robbins_siegmund_conformal_v1100(
                losses.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(alpha),
                out_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(t_len)
            )
            if res == 0:
                return out_v
            raise NativeKernelError(f"Rust robbins_siegmund failed with rc={res}")

        v = 1.0
        for t in range(t_len):
            gamma_t = 1.0 / (t + 2)
            beta_t = 0.5 / (t + 2)
            psi = np.tanh(losses[t] - alpha)
            v = max(1e-6, (1.0 - gamma_t) * v + beta_t * psi)
            out_v[t] = v
        return out_v

    @staticmethod
    def betti1_rips(points: np.ndarray, eps: float = 0.5) -> int:
        points = np.ascontiguousarray(points, dtype=np.float32)
        n, d = points.shape

        if _rust_lib and hasattr(_rust_lib, "polydim_betti1_rips_v1100"):
            _rust_lib.polydim_betti1_rips_v1100.argtypes = [
                ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_float
            ]
            _rust_lib.polydim_betti1_rips_v1100.restype = ctypes.c_int32
            res = _rust_lib.polydim_betti1_rips_v1100(
                points.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(n),
                ctypes.c_int32(d),
                ctypes.c_float(eps)
            )
            if res >= 0:
                return res
            raise NativeKernelError(f"Rust betti1_rips failed with rc={res}")

        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                if np.sum((points[i] - points[j])**2) <= eps * eps:
                    edges.append((i, j))
        num_e = len(edges)
        return max(0, num_e - n + 1)

    @staticmethod
    def clifford_rotor_spin(x: np.ndarray, bivector_u: np.ndarray, bivector_v: np.ndarray, theta: float, out_x: np.ndarray = None) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        bivector_u = np.ascontiguousarray(bivector_u, dtype=np.float32)
        bivector_v = np.ascontiguousarray(bivector_v, dtype=np.float32)
        if out_x is None:
            out_x = np.zeros_like(x)
        d = x.shape[0]

        if _rust_lib and hasattr(_rust_lib, "polydim_clifford_rotor_spin_v1100"):
            _rust_lib.polydim_clifford_rotor_spin_v1100.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_float, ctypes.c_void_p, ctypes.c_int32
            ]
            _rust_lib.polydim_clifford_rotor_spin_v1100.restype = ctypes.c_int32
            res = _rust_lib.polydim_clifford_rotor_spin_v1100(
                x.ctypes.data_as(ctypes.c_void_p),
                bivector_u.ctypes.data_as(ctypes.c_void_p),
                bivector_v.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_float(theta),
                out_x.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int32(d)
            )
            if res == 0:
                return out_x
            raise NativeKernelError(f"Rust clifford_rotor_spin failed with rc={res}")

        dot_ux = np.dot(bivector_u, x)
        dot_vx = np.dot(bivector_v, x)
        half_t = theta * 0.5
        sin_t = 2.0 * np.sin(half_t) * np.cos(half_t)
        c_factor = -2.0 * np.sin(half_t)**2
        proj = dot_ux * bivector_u + dot_vx * bivector_v
        rot = dot_vx * bivector_u - dot_ux * bivector_v
        res = x + c_factor * proj + sin_t * rot
        res /= max(1e-12, np.linalg.norm(res))
        out_x[:] = res
        return out_x


if __name__ == "__main__":
    print("=== POLYDIM MONOLITO V1101 ZERO-ALLOCATION SELF-TEST ===")
    np.random.seed(42)
    x = np.random.randn(8).astype(np.float32)
    x = x / np.linalg.norm(x)
    q = np.zeros_like(x)
    PolydimV1100Engine.e8_lattice_quantize(x, out_quant=q)
    print("E8 Quantized (Zero-Alloc):", q)
    print("Polydim V1101 Engine Ready.")
