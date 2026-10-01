# ============================================================================
# POLYDIM MONOLITO V940 (SERIE 900 PRODUCCION DECENAL CERTIFICADA - HITO 30)
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

# C++ DLL Loader
_cpp_dll_path = os.path.join(_DIR, "kernel_cpp_v940.dll")
_rust_dll_path = os.path.join(_DIR, "kernel_rust_v940.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_cpp_dll_path):
    try:
        _cpp_lib = ctypes.CDLL(_cpp_dll_path)
    except Exception as e:
        print(f"[POLYDIM V940 WARN] Could not load C++ DLL: {e}", file=sys.stderr)

if os.path.exists(_rust_dll_path):
    try:
        _rust_lib = ctypes.CDLL(_rust_dll_path)
    except Exception as e:
        print(f"[POLYDIM V940 WARN] Could not load Rust DLL: {e}", file=sys.stderr)


class PolydimV940Engine:
    """Master engine for POLYDIM V940 native low-level operations."""

    @staticmethod
    def riesz_feller_dirac(in_spinor: np.ndarray, alpha: float = 1.5, dt: float = 0.01) -> np.ndarray:
        in_spinor = np.ascontiguousarray(in_spinor, dtype=np.float32)
        out_spinor = np.zeros_like(in_spinor)
        D = in_spinor.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_riesz_feller_dirac_v940"):
            _cpp_lib.polydim_riesz_feller_dirac_v940.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int32, ctypes.c_float, ctypes.c_float
            ]
            _cpp_lib.polydim_riesz_feller_dirac_v940.restype = ctypes.c_int32
            res = _cpp_lib.polydim_riesz_feller_dirac_v940(
                in_spinor.ctypes.data_as(ctypes.c_char_p),
                out_spinor.ctypes.data_as(ctypes.c_char_p),
                ctypes.c_int32(D),
                ctypes.c_float(alpha),
                ctypes.c_float(dt)
            )
            if res == 0:
                return out_spinor

        # Python fallback
        prev = np.roll(in_spinor, 1)
        nxt = np.roll(in_spinor, -1)
        lap = 2.0 * in_spinor - prev - nxt
        frac_lap = np.power(np.maximum(1e-8, np.abs(lap)), (alpha - 1.0) * 0.5)
        grad = (nxt - prev) * 0.5
        return in_spinor - dt * frac_lap * grad

    @staticmethod
    def nambu_step(x: np.ndarray, grad_V: np.ndarray, dt: float = 0.01) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        grad_V = np.ascontiguousarray(grad_V, dtype=np.float32)
        out_x = np.zeros_like(x)
        D = x.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_nambu_integrator_v940"):
            _cpp_lib.polydim_nambu_integrator_v940.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int32, ctypes.c_float
            ]
            _cpp_lib.polydim_nambu_integrator_v940.restype = ctypes.c_int32
            res = _cpp_lib.polydim_nambu_integrator_v940(
                x.ctypes.data_as(ctypes.c_char_p),
                grad_V.ctypes.data_as(ctypes.c_char_p),
                out_x.ctypes.data_as(ctypes.c_char_p),
                ctypes.c_int32(D),
                ctypes.c_float(dt)
            )
            if res == 0:
                return out_x

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
    def e8_quantize(vec: np.ndarray) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        out = np.zeros_like(vec)
        D = vec.shape[0]

        if _cpp_lib and hasattr(_cpp_lib, "polydim_e8_lattice_quantize_v940") and (D % 8 == 0):
            _cpp_lib.polydim_e8_lattice_quantize_v940.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int32
            ]
            _cpp_lib.polydim_e8_lattice_quantize_v940.restype = ctypes.c_int32
            res = _cpp_lib.polydim_e8_lattice_quantize_v940(
                vec.ctypes.data_as(ctypes.c_char_p),
                out.ctypes.data_as(ctypes.c_char_p),
                ctypes.c_int32(D)
            )
            if res == 0:
                return out

        # Python fallback
        out = np.copy(vec)
        for b in range(D // 8):
            blk = vec[b*8:(b+1)*8]
            f = np.round(blk)
            if int(np.sum(f)) % 2 != 0:
                diffs = np.abs(blk - f)
                w = np.argmax(diffs)
                f[w] += 1.0 if blk[w] > f[w] else -1.0
            out[b*8:(b+1)*8] = f
        return out

    @staticmethod
    def marsden_weinstein_reduce(Q: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        Q = np.ascontiguousarray(Q, dtype=np.float32)
        P = np.ascontiguousarray(P, dtype=np.float32)
        out_Q = np.zeros_like(Q)
        out_P = np.zeros_like(P)
        D, K = Q.shape

        if _cpp_lib and hasattr(_cpp_lib, "polydim_marsden_weinstein_reduction_v940"):
            _cpp_lib.polydim_marsden_weinstein_reduction_v940.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                ctypes.c_int32, ctypes.c_int32
            ]
            _cpp_lib.polydim_marsden_weinstein_reduction_v940.restype = ctypes.c_int32
            res = _cpp_lib.polydim_marsden_weinstein_reduction_v940(
                Q.ctypes.data_as(ctypes.c_char_p),
                P.ctypes.data_as(ctypes.c_char_p),
                out_Q.ctypes.data_as(ctypes.c_char_p),
                out_P.ctypes.data_as(ctypes.c_char_p),
                ctypes.c_int32(D),
                ctypes.c_int32(K)
            )
            if res == 0:
                return out_Q, out_P

        J = Q.T @ P - P.T @ Q
        out_Q = np.copy(Q)
        out_P = P - 0.5 * (Q @ J)
        return out_Q, out_P

    @staticmethod
    def robbins_siegmund(losses: np.ndarray, alpha: float = 0.1) -> np.ndarray:
        losses = np.ascontiguousarray(losses, dtype=np.float32)
        out_v = np.zeros_like(losses)
        T = losses.shape[0]

        if _rust_lib and hasattr(_rust_lib, "polydim_robbins_siegmund_conformal_v940"):
            _rust_lib.polydim_robbins_siegmund_conformal_v940.argtypes = [
                ctypes.c_char_p, ctypes.c_float, ctypes.c_char_p, ctypes.c_int32
            ]
            _rust_lib.polydim_robbins_siegmund_conformal_v940.restype = ctypes.c_int32
            res = _rust_lib.polydim_robbins_siegmund_conformal_v940(
                losses.ctypes.data_as(ctypes.c_char_p),
                ctypes.c_float(alpha),
                out_v.ctypes.data_as(ctypes.c_char_p),
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
