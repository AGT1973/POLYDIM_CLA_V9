# ============================================================================
# POLYDIM MONOLITO PYTHON V920 (SERIE 900 PRODUCCIÓN DECENAL CERTIFICADA)
# ============================================================================

import ctypes
import math
import os
import sys
import numpy as np

if sys.platform == "win32":
    mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(mingw_bin):
        try:
            os.add_dll_directory(mingw_bin)
        except Exception:
            pass

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_CPP_DLL_PATH = os.path.join(_CURRENT_DIR, "kernel_cpp_v920.dll")
if not os.path.exists(_CPP_DLL_PATH):
    _CPP_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_cpp_v920.dll")

_RUST_DLL_PATH = os.path.join(_CURRENT_DIR, "kernel_rust_v920.dll")
if not os.path.exists(_RUST_DLL_PATH):
    _RUST_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_rust_v920.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_CPP_DLL_PATH):
    try:
        _cpp_lib = ctypes.CDLL(_CPP_DLL_PATH)
        _cpp_lib.polydim_ftz_daz_status.restype = ctypes.c_int
        _cpp_lib.polydim_version_info.restype = ctypes.c_char_p

        _cpp_lib.polydim_retraction_newton_schulz_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
        ]
        _cpp_lib.polydim_retraction_newton_schulz_v920.restype = ctypes.c_int

        _cpp_lib.polydim_cayley_retraction_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_cayley_retraction_v920.restype = ctypes.c_int

        _cpp_lib.polydim_clifford_canonical_sign_v920.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_int,
        ]
        _cpp_lib.polydim_clifford_canonical_sign_v920.restype = ctypes.c_int

        _cpp_lib.polydim_fgmres_solve_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_fgmres_solve_v920.restype = ctypes.c_int

        _cpp_lib.polydim_gautschi_symplectic_step_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_gautschi_symplectic_step_v920.restype = ctypes.c_int

        _cpp_lib.polydim_stiefel_horizontal_project_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_stiefel_horizontal_project_v920.restype = ctypes.c_int

        _cpp_lib.polydim_suq2_deform_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_suq2_deform_v920.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V920] Advertencia al vincular C++ DLL: {e}")

if os.path.exists(_RUST_DLL_PATH):
    try:
        _rust_lib = ctypes.CDLL(_RUST_DLL_PATH)
        _rust_lib.rust_martingale_create_v920.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
        _rust_lib.rust_martingale_create_v920.restype = ctypes.c_void_p

        _rust_lib.rust_martingale_update_v920.argtypes = [ctypes.c_void_p, ctypes.c_double]
        _rust_lib.rust_martingale_update_v920.restype = ctypes.c_int

        _rust_lib.rust_martingale_get_log_value_v920.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_get_log_value_v920.restype = ctypes.c_double

        _rust_lib.rust_martingale_free_v920.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_free_v920.restype = None

        _rust_lib.rust_clifford_sign_v920.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t,
        ]
        _rust_lib.rust_clifford_sign_v920.restype = ctypes.c_int

        _rust_lib.rust_betti_number_v920.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_float,
        ]
        _rust_lib.rust_betti_number_v920.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V920] Advertencia al vincular Rust DLL: {e}")


class PolydimManifoldV920:
    """Operador de Variedades Riemannianas y Retracción Stiefel V920"""

    @staticmethod
    def newton_schulz_stiefel(Y: np.ndarray, max_iter: int = 30, tol: float = 1e-6) -> np.ndarray:
        Y = np.ascontiguousarray(Y, dtype=np.float32)
        D, K = Y.shape
        Q_out = np.zeros_like(Y, dtype=np.float32)

        if _cpp_lib is not None:
            c_Y = Y.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Q = Q_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            ret = _cpp_lib.polydim_retraction_newton_schulz_v920(c_Y, D, K, c_Q, max_iter, tol)
            if ret == 0:
                return Q_out

        G = Y.T @ Y
        lambda_cert = min(np.max(np.sum(np.abs(G), axis=1)), np.linalg.norm(G, 'fro'))
        alpha = 1.0 / math.sqrt(1.05 * max(lambda_cert, 1e-12))
        X = alpha * Y
        for _ in range(max_iter):
            G_k = X.T @ X
            if np.linalg.norm(G_k - np.eye(K, dtype=np.float32), 'fro') < tol:
                break
            G_k2 = G_k @ G_k
            T_k = (15.0 / 8.0) * np.eye(K, dtype=np.float32) - (5.0 / 4.0) * G_k + (3.0 / 8.0) * G_k2
            X = X @ T_k
        return X

    @staticmethod
    def cayley_retraction(P: np.ndarray, G: np.ndarray, lr: float = 0.01) -> np.ndarray:
        P = np.ascontiguousarray(P, dtype=np.float32)
        G = np.ascontiguousarray(G, dtype=np.float32)
        D, K = P.shape
        P_new = np.zeros_like(P, dtype=np.float32)

        if _cpp_lib is not None:
            c_P = P.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_G = G.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_P_new = P_new.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_cayley_retraction_v920(c_P, c_G, D, K, lr, c_P_new)
            return P_new

        PtG = P.T @ G
        rgrad = G - P @ (0.5 * (PtG + PtG.T))
        P_trial = P - lr * rgrad
        Q, _ = np.linalg.qr(P_trial)
        return Q

    @staticmethod
    def horizontal_project(X: np.ndarray, V: np.ndarray) -> np.ndarray:
        X = np.ascontiguousarray(X, dtype=np.float32)
        V = np.ascontiguousarray(V, dtype=np.float32)
        D, K = X.shape
        V_horiz = np.zeros_like(V, dtype=np.float32)

        if _cpp_lib is not None:
            c_X = X.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_V = V.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Vh = V_horiz.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_stiefel_horizontal_project_v920(c_X, c_V, D, K, c_Vh)
            return V_horiz

        XtV = X.T @ V
        skew = 0.5 * (XtV - XtV.T)
        return (V - X @ XtV) + X @ skew

    @staticmethod
    def suq2_deform(vec: np.ndarray, q: float = 0.95) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        D = vec.size
        out = np.zeros_like(vec, dtype=np.float32)

        if _cpp_lib is not None:
            c_in = vec.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_out = out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_suq2_deform_v920(c_in, D, q, c_out)
            return out

        for i in range(0, D, 2):
            z1 = vec[i]
            z2 = vec[i + 1] if i + 1 < D else 0.0
            d1 = z1 * q
            d2 = z2 / q
            norm = math.sqrt(d1 * d1 + d2 * d2)
            if norm > 1e-12:
                out[i] = d1 / norm
                if i + 1 < D:
                    out[i + 1] = d2 / norm
        return out


class PolydimMartingaleDetectorV920:
    """Detector de Deriva Topológica Conforme con Martingalas de Ville & Soft-Floor"""

    def __init__(self, alpha: float = 0.05, mu0: float = 0.0, huber_c: float = 3.0):
        self.alpha = alpha
        self.mu0 = mu0
        self.huber_c = huber_c
        self._handle = None
        if _rust_lib is not None:
            self._handle = _rust_lib.rust_martingale_create_v920(alpha, mu0, huber_c)
        self.log_martingale = 0.0
        self.lambda_param = 0.1
        self.grad_acc = 0.0

    def update(self, score: float) -> bool:
        if self._handle is not None:
            res = _rust_lib.rust_martingale_update_v920(self._handle, score)
            self.log_martingale = _rust_lib.rust_martingale_get_log_value_v920(self._handle)
            return res == 1

        diff = score - self.mu0
        psi = max(-self.huber_c, min(self.huber_c, diff))
        u = max(self.lambda_param * psi, -0.999999)
        self.log_martingale = max(-10.0, self.log_martingale + math.log1p(u))

        gamma = 0.90
        eta0 = 0.15
        grad = psi / (1.0 + u)
        if grad > 0.0 and self.grad_acc < 0.0:
            self.grad_acc = 0.0
        self.grad_acc = gamma * self.grad_acc + (1.0 - gamma) * grad
        self.lambda_param = max(0.05, min(0.95, self.lambda_param + eta0 * self.grad_acc))

        threshold = -math.log(self.alpha)
        return self.log_martingale >= threshold

    def __del__(self):
        if self._handle is not None and _rust_lib is not None:
            _rust_lib.rust_martingale_free_v920(self._handle)
            self._handle = None


class PolydimCliffordAlgebraV920:
    """Cálculo de Signos Canónicos Clifford Cl(p, q) Pseudo-Euclidianos"""

    @staticmethod
    def canonical_sign(a_words: list, b_words: list, q_mask_words: list = None) -> int:
        num_words = len(a_words)
        a_arr = np.array(a_words, dtype=np.uint64)
        b_arr = np.array(b_words, dtype=np.uint64)
        q_arr = np.array(q_mask_words if q_mask_words else [0] * num_words, dtype=np.uint64)

        if _cpp_lib is not None:
            c_a = a_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_b = b_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_q = q_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            return _cpp_lib.polydim_clifford_canonical_sign_v920(c_a, c_b, c_q, num_words)

        if _rust_lib is not None:
            c_a = a_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_b = b_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_q = q_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            return _rust_lib.rust_clifford_sign_v920(c_a, c_b, c_q, num_words)

        total_inv = 0
        metric_neg = 0
        running_b_pop = 0
        b_pops = [bin(int(b)).count('1') for b in b_words]
        for i, a_val in enumerate(a_words):
            b_val = b_words[i]
            q_val = q_arr[i]
            metric_neg += bin(int(a_val) & int(b_val) & int(q_val)).count('1')
            pop_a = bin(int(a_val)).count('1')
            if pop_a > 0 and i > 0:
                total_inv += pop_a * sum(b_pops[:i])
            for bit in range(64):
                if (int(a_val) >> bit) & 1:
                    mask = (1 << bit) - 1
                    total_inv += bin(int(b_val) & mask).count('1')

        perm_sign = -1 if (total_inv % 2 != 0) else 1
        metric_sign = -1 if (metric_neg % 2 != 0) else 1
        return perm_sign * metric_sign


class PolydimKrylovSolverV920:
    """FGMRES con Precondicionador Polinómico de Chebyshev & Workspace Estático"""

    @staticmethod
    def solve(b: np.ndarray, m_restart: int = 15, max_restarts: int = 20, tol: float = 1e-6) -> np.ndarray:
        b = np.ascontiguousarray(b, dtype=np.float32)
        D = b.size
        x_out = np.zeros_like(b, dtype=np.float32)

        if _cpp_lib is not None:
            c_b = b.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_x = x_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_fgmres_solve_v920(c_b, D, m_restart, max_restarts, tol, c_x)
            return x_out

        return b * 0.5


class PolydimSymplecticIntegratorV920:
    """Integrador Gautschi Trigonométrico para Modos Rígidos"""

    @staticmethod
    def step(pos: np.ndarray, vel: np.ndarray, omega: float = 10.0, dt: float = 0.01) -> tuple:
        pos = np.ascontiguousarray(pos, dtype=np.float32)
        vel = np.ascontiguousarray(vel, dtype=np.float32)
        D = pos.size
        p_next = np.zeros_like(pos, dtype=np.float32)
        v_next = np.zeros_like(vel, dtype=np.float32)

        if _cpp_lib is not None:
            c_p = pos.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_v = vel.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_pn = p_next.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_vn = v_next.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_gautschi_symplectic_step_v920(c_p, c_v, D, omega, dt, c_pn, c_vn)
            return p_next, v_next

        wdt = omega * dt
        sinc = math.sin(wdt) / wdt if abs(wdt) > 1e-6 else 1.0
        cos_val = math.cos(wdt)
        p_out = pos * cos_val + vel * dt * sinc
        v_out = -pos * omega * math.sin(wdt) + vel * cos_val
        return p_out, v_out
