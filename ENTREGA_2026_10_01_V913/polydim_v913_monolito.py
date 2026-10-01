# polydim_v913_monolito.py
# Monolito Python POLYDIM v913 (Master Industrial Release)
# ============================================================================

import os
import sys
import ctypes
import numpy as np
import math

if sys.platform == "win32":
    mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(mingw_bin):
        try:
            os.add_dll_directory(mingw_bin)
        except Exception:
            pass

def require(condition: bool, message: str = "Invariant violation"):
    if not condition:
        raise RuntimeError(f"[POLYDIM v913 INVARIANT ERROR] {message}")

class PolydimErrorv913(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("code", ctypes.c_uint32),
        ("msg", ctypes.c_char * 256),
        ("arena_id", ctypes.c_uint64),
        ("gen", ctypes.c_uint64),
        ("_pad", ctypes.c_uint8 * 40),
    ]
    def check_ok(self):
        if self.code != 0:
            err_msg = self.msg.decode("utf-8", errors="replace")
            raise RuntimeError(f"POLYDIM v913 FFI Error {self.code}: {err_msg}")

require(ctypes.sizeof(PolydimErrorv913) == 320, "ABI Mismatch: PolydimErrorv913 must be 320 bytes")

class PolydimEnginev913:
    def __init__(self, dll_dir: str = None):
        if dll_dir is None:
            dll_dir = os.path.dirname(os.path.abspath(__file__))
        cpp_dll_path = os.path.join(dll_dir, "polydim_cpp_v913.dll")
        rust_dll_path = os.path.join(dll_dir, "polydim_rust_v913.dll")
        if not os.path.exists(cpp_dll_path): raise FileNotFoundError(cpp_dll_path)
        if not os.path.exists(rust_dll_path): raise FileNotFoundError(rust_dll_path)
        self.cpp = ctypes.CDLL(cpp_dll_path)
        self.rust = ctypes.CDLL(rust_dll_path)
        self._bind_ffi_signatures()

    def _bind_ffi_signatures(self):
        # C++ Bindings
        self.cpp.polydim_cpp_auon_log_cosh_brake_v913.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_auon_log_cosh_brake_v913.restype = ctypes.c_int32

        self.cpp.polydim_cpp_auon_matrix_rms_normalize_v913.argtypes = [
            ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_auon_matrix_rms_normalize_v913.restype = ctypes.c_int32

        self.cpp.polydim_cpp_riemannian_geodesic_v913.argtypes = [
            ctypes.c_int64, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_riemannian_geodesic_v913.restype = ctypes.c_int32

        self.cpp.polydim_cpp_clifford256_canonical_sign_v913.argtypes = [
            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_clifford256_canonical_sign_v913.restype = ctypes.c_int32

        self.cpp.polydim_cpp_stiefel_newton_schulz_retraction_v913.argtypes = [
            ctypes.c_int64, ctypes.c_int64, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_stiefel_newton_schulz_retraction_v913.restype = ctypes.c_int32

        self.cpp.polydim_cpp_fgmres_woodbury_solve_v913.argtypes = [
            ctypes.c_int64, ctypes.c_int32, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(PolydimErrorv913)
        ]
        self.cpp.polydim_cpp_fgmres_woodbury_solve_v913.restype = ctypes.c_int32

        # Rust Bindings
        self.rust.polydim_rust_auon_log_cosh_brake_v913.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.rust.polydim_rust_auon_log_cosh_brake_v913.restype = ctypes.c_int32
        self.rust.polydim_rust_clifford256_canonical_sign_v913.argtypes = [
            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(PolydimErrorv913)
        ]
        self.rust.polydim_rust_clifford256_canonical_sign_v913.restype = ctypes.c_int32

        self.rust.polydim_rust_log1p_ogd_conformal_martingale_v913.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(PolydimErrorv913)
        ]
        self.rust.polydim_rust_log1p_ogd_conformal_martingale_v913.restype = ctypes.c_int32

        self.rust.polydim_rust_fire_metric_v913.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_longlong, ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv913)
        ]
        self.rust.polydim_rust_fire_metric_v913.restype = ctypes.c_int32

    def cpp_auon_brake(self, residual: float, scale_s: float = 1.0, lambda_val: float = 1.0):
        loss = ctypes.c_double(0.0)
        grad = ctypes.c_double(0.0)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_auon_log_cosh_brake_v913(
            residual, scale_s, lambda_val, ctypes.byref(loss), ctypes.byref(grad), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"AuON Brake failed: {res}")
        return loss.value, grad.value

    def cpp_auon_matrix_rms_normalize(self, matrix: np.ndarray):
        require(matrix.ndim == 2, "Matrix must be 2D")
        rows, cols = matrix.shape
        in_buf = np.ascontiguousarray(matrix, dtype=np.float64)
        out_buf = np.empty_like(in_buf)
        rms = ctypes.c_double(0.0)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_auon_matrix_rms_normalize_v913(
            rows, cols,
            in_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(rms), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"RMS Normalize failed: {res}")
        return out_buf, rms.value

    def cpp_riemannian_geodesic(self, u: np.ndarray, v: np.ndarray):
        require(u.ndim == 1 and v.ndim == 1 and len(u) == len(v), "Vectors must be 1D of equal length")
        dim = len(u)
        u_buf = np.ascontiguousarray(u, dtype=np.float64)
        v_buf = np.ascontiguousarray(v, dtype=np.float64)
        ang = ctypes.c_double(0.0)
        chord = ctypes.c_double(0.0)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_riemannian_geodesic_v913(
            dim,
            u_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(ang), ctypes.byref(chord), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"Geodesic failed: {res}")
        return ang.value, chord.value

    def cpp_stiefel_newton_schulz(self, q: np.ndarray, g: np.ndarray, alpha: float = 0.01):
        require(q.ndim == 2 and g.ndim == 2 and q.shape == g.shape, "Shape mismatch in Stiefel input")
        n, k = q.shape
        q_buf = np.ascontiguousarray(q, dtype=np.float64)
        g_buf = np.ascontiguousarray(g, dtype=np.float64)
        y_out = np.zeros_like(q_buf)
        ortho_err = ctypes.c_double(0.0)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_stiefel_newton_schulz_retraction_v913(
            n, k, alpha,
            q_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            g_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            y_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(ortho_err), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"Newton-Schulz retraction failed: {res}")
        return y_out, ortho_err.value

    def cpp_clifford256_canonical_sign(self, mask_a: np.ndarray, mask_b: np.ndarray) -> int:
        require(len(mask_a) == 4 and len(mask_b) == 4, "Masks must be uint64[4]")
        a_buf = np.ascontiguousarray(mask_a, dtype=np.uint64)
        b_buf = np.ascontiguousarray(mask_b, dtype=np.uint64)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_clifford256_canonical_sign_v913(
            a_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            b_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            ctypes.byref(err)
        )
        err.check_ok()
        return res

    def rust_clifford256_canonical_sign(self, mask_a: np.ndarray, mask_b: np.ndarray) -> int:
        require(len(mask_a) == 4 and len(mask_b) == 4, "Masks must be uint64[4]")
        a_buf = np.ascontiguousarray(mask_a, dtype=np.uint64)
        b_buf = np.ascontiguousarray(mask_b, dtype=np.uint64)
        err = PolydimErrorv913()
        res = self.rust.polydim_rust_clifford256_canonical_sign_v913(
            a_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            b_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            ctypes.byref(err)
        )
        err.check_ok()
        return res

    def rust_log1p_ogd_martingale(self, scores: np.ndarray):
        require(scores.ndim == 1, "Scores must be 1D")
        s_buf = np.ascontiguousarray(scores, dtype=np.float64)
        log_e = ctypes.c_double(0.0)
        final_e = ctypes.c_double(0.0)
        alarm = ctypes.c_int32(0)
        err = PolydimErrorv913()
        res = self.rust.polydim_rust_log1p_ogd_conformal_martingale_v913(
            s_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            len(scores),
            ctypes.byref(log_e), ctypes.byref(final_e), ctypes.byref(alarm),
            ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"Rust Martingale failed: {res}")
        return log_e.value, final_e.value, bool(alarm.value)

    def cpp_fgmres_woodbury_solve(self, b: np.ndarray, max_iter: int = 30, tol: float = 1e-6):
        require(b.ndim == 1, "Vector b must be 1D")
        dim = len(b)
        b_buf = np.ascontiguousarray(b, dtype=np.float64)
        x_out = np.zeros(dim, dtype=np.float64)
        iters_out = ctypes.c_int32(0)
        res_out = ctypes.c_double(0.0)
        state_out = ctypes.c_int32(0)
        err = PolydimErrorv913()
        res = self.cpp.polydim_cpp_fgmres_woodbury_solve_v913(
            dim, max_iter, tol,
            b_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            x_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(iters_out), ctypes.byref(res_out), ctypes.byref(state_out),
            ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"FGMRES Solve failed: {res}")
        return x_out, iters_out.value, res_out.value, state_out.value
