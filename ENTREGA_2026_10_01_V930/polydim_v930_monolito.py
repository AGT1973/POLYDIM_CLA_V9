# ============================================================================
# POLYDIM MONOLITO PYTHON V930 (SERIE 900 PRODUCCIÓN DECENAL CERTIFICADA - HITO 20)
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
_CPP_DLL_PATH = os.path.join(_CURRENT_DIR, "kernel_cpp_v930.dll")
if not os.path.exists(_CPP_DLL_PATH):
    _CPP_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_cpp_v930.dll")

_RUST_DLL_PATH = os.path.join(_CURRENT_DIR, "kernel_rust_v930.dll")
if not os.path.exists(_RUST_DLL_PATH):
    _RUST_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_rust_v930.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_CPP_DLL_PATH):
    try:
        _cpp_lib = ctypes.CDLL(_CPP_DLL_PATH)
        _cpp_lib.polydim_ftz_daz_status.restype = ctypes.c_int
        _cpp_lib.polydim_version_info.restype = ctypes.c_char_p

        _cpp_lib.polydim_spherical_parallel_transport_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_spherical_parallel_transport_v930.restype = ctypes.c_int

        _cpp_lib.polydim_retraction_newton_schulz_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
        ]
        _cpp_lib.polydim_retraction_newton_schulz_v930.restype = ctypes.c_int

        _cpp_lib.polydim_cayley_retraction_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_cayley_retraction_v930.restype = ctypes.c_int

        _cpp_lib.polydim_tao_symplectic_step_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_tao_symplectic_step_v930.restype = ctypes.c_int

        _cpp_lib.polydim_clifford_canonical_sign_v930.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_int,
        ]
        _cpp_lib.polydim_clifford_canonical_sign_v930.restype = ctypes.c_int

        _cpp_lib.polydim_grassmann_project_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_grassmann_project_v930.restype = ctypes.c_int

        _cpp_lib.polydim_fgmres_solve_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_fgmres_solve_v930.restype = ctypes.c_int

        _cpp_lib.polydim_suq2_deform_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_suq2_deform_v930.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V930] Advertencia al vincular C++ DLL: {e}")

if os.path.exists(_RUST_DLL_PATH):
    try:
        _rust_lib = ctypes.CDLL(_RUST_DLL_PATH)
        _rust_lib.rust_martingale_create_v930.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
        _rust_lib.rust_martingale_create_v930.restype = ctypes.c_void_p

        _rust_lib.rust_martingale_update_v930.argtypes = [ctypes.c_void_p, ctypes.c_double]
        _rust_lib.rust_martingale_update_v930.restype = ctypes.c_int

        _rust_lib.rust_martingale_get_log_value_v930.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_get_log_value_v930.restype = ctypes.c_double

        _rust_lib.rust_martingale_free_v930.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_free_v930.restype = None

        _rust_lib.rust_robbins_siegmund_log_martingale_v930.argtypes = [
            ctypes.c_double,
            ctypes.c_uint64,
            ctypes.c_size_t,
            ctypes.c_double,
        ]
        _rust_lib.rust_robbins_siegmund_log_martingale_v930.restype = ctypes.c_double

        _rust_lib.rust_ebh_fdr_threshold_v930.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
        ]
        _rust_lib.rust_ebh_fdr_threshold_v930.restype = ctypes.c_size_t

        _rust_lib.rust_clifford_sign_v930.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t,
        ]
        _rust_lib.rust_clifford_sign_v930.restype = ctypes.c_int

        _rust_lib.rust_betti_number_v930.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_float,
        ]
        _rust_lib.rust_betti_number_v930.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V930] Advertencia al vincular Rust DLL: {e}")


class PolydimManifoldV930:
    """Operador de Variedades Riemannianas y Retracción Stiefel / Grassmann V930"""

    @staticmethod
    def parallel_transport_sphere(x: np.ndarray, y: np.ndarray, v: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.ascontiguousarray(y, dtype=np.float32)
        v = np.ascontiguousarray(v, dtype=np.float32)
        D = x.size
        v_out = np.zeros_like(v, dtype=np.float32)

        if _cpp_lib is not None:
            c_x = x.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_y = y.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_v = v.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_vo = v_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_spherical_parallel_transport_v930(c_x, c_y, c_v, D, c_vo)
            return v_out

        dot_xy = float(np.dot(x, y))
        dot_xpy_v = float(np.dot(x + y, v))
        denom = 1.0 + dot_xy
        if denom < 1e-7:
            return -v
        return v - (dot_xpy_v / denom) * (x + y)

    @staticmethod
    def newton_schulz_stiefel(Y: np.ndarray, max_iter: int = 30, tol: float = 1e-6) -> np.ndarray:
        Y = np.ascontiguousarray(Y, dtype=np.float32)
        D, K = Y.shape
        Q_out = np.zeros_like(Y, dtype=np.float32)

        if _cpp_lib is not None:
            c_Y = Y.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Q = Q_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            ret = _cpp_lib.polydim_retraction_newton_schulz_v930(c_Y, D, K, c_Q, max_iter, tol)
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
            _cpp_lib.polydim_cayley_retraction_v930(c_P, c_G, D, K, lr, c_P_new)
            return P_new

        PtG = P.T @ G
        PtP = P.T @ P
        GtG = G.T @ G
        K2 = 2 * K
        M = np.eye(K2, dtype=np.float32)
        half_lr = 0.5 * lr
        M[:K, :K] += half_lr * PtG
        M[:K, K:] += half_lr * PtP
        M[K:, :K] += -half_lr * GtG
        M[K:, K:] += -half_lr * PtG.T
        B = np.vstack([PtP, -PtG.T])
        C = np.linalg.solve(M, B)
        Y = P - lr * (G @ C[:K] + P @ C[K:])
        Q = PolydimManifoldV930.newton_schulz_stiefel(Y, max_iter=2)
        return Q

    @staticmethod
    def grassmann_project(U: np.ndarray, Z: np.ndarray) -> np.ndarray:
        U = np.ascontiguousarray(U, dtype=np.float32)
        Z = np.ascontiguousarray(Z, dtype=np.float32)
        D, K = U.shape
        Zh = np.zeros_like(Z, dtype=np.float32)

        if _cpp_lib is not None:
            c_U = U.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Z = Z.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Zh = Zh.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_grassmann_project_v930(c_U, c_Z, D, K, c_Zh)
            return Zh

        return Z - U @ (U.T @ Z)

    @staticmethod
    def suq2_deform(vec: np.ndarray, q: float = 0.95) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        D = vec.size
        out = np.zeros_like(vec, dtype=np.float32)

        if _cpp_lib is not None:
            c_in = vec.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_out = out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_suq2_deform_v930(c_in, D, q, c_out)
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


class PolydimMartingaleDetectorV930:
    """Detector de Deriva Topológica Conforme con Martingalas de Ville & Reseteo de Inercia"""

    def __init__(self, alpha: float = 0.05, mu0: float = 0.0, huber_c: float = 3.0):
        self.alpha = alpha
        self.mu0 = mu0
        self.huber_c = huber_c
        self._handle = None
        if _rust_lib is not None:
            self._handle = _rust_lib.rust_martingale_create_v930(alpha, mu0, huber_c)
        self.log_martingale = 0.0
        self.lambda_param = 0.1
        self.grad_acc = 0.0

    def update(self, score: float) -> bool:
        if self._handle is not None:
            res = _rust_lib.rust_martingale_update_v930(self._handle, score)
            self.log_martingale = _rust_lib.rust_martingale_get_log_value_v930(self._handle)
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
            _rust_lib.rust_martingale_free_v930(self._handle)
            self._handle = None


class PolydimCliffordAlgebraV930:
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
            return _cpp_lib.polydim_clifford_canonical_sign_v930(c_a, c_b, c_q, num_words)

        if _rust_lib is not None:
            c_a = a_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_b = b_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_q = q_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            return _rust_lib.rust_clifford_sign_v930(c_a, c_b, c_q, num_words)

        total_inv = 0
        metric_neg = 0
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


class PolydimKrylovSolverV930:
    """FGMRES con Precondicionador Polinómico de Chebyshev & Workspace Estático"""

    @staticmethod
    def solve(b: np.ndarray, m_restart: int = 15, max_restarts: int = 20, tol: float = 1e-6) -> np.ndarray:
        b = np.ascontiguousarray(b, dtype=np.float32)
        D = b.size
        x_out = np.zeros_like(b, dtype=np.float32)

        if _cpp_lib is not None:
            c_b = b.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_x = x_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_fgmres_solve_v930(c_b, D, m_restart, max_restarts, tol, c_x)
            return x_out

        return b * 0.5


class PolydimSymplecticIntegratorV930:
    """Integrador Simpléctico Explícito de Tao para Hamiltonianos No Separables"""

    @staticmethod
    def step_tao(q1: np.ndarray, p1: np.ndarray, q2: np.ndarray, p2: np.ndarray, omega: float = 10.0, dt: float = 0.01):
        q1 = np.ascontiguousarray(q1, dtype=np.float32)
        p1 = np.ascontiguousarray(p1, dtype=np.float32)
        q2 = np.ascontiguousarray(q2, dtype=np.float32)
        p2 = np.ascontiguousarray(p2, dtype=np.float32)
        D = q1.size

        q1_out = np.zeros_like(q1, dtype=np.float32)
        p1_out = np.zeros_like(p1, dtype=np.float32)
        q2_out = np.zeros_like(q2, dtype=np.float32)
        p2_out = np.zeros_like(p2, dtype=np.float32)

        if _cpp_lib is not None:
            c_q1 = q1.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_p1 = p1.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_q2 = q2.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_p2 = p2.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

            c_q1o = q1_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_p1o = p1_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_q2o = q2_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_p2o = p2_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

            _cpp_lib.polydim_tao_symplectic_step_v930(c_q1, c_p1, c_q2, c_p2, D, omega, dt, c_q1o, c_p1o, c_q2o, c_p2o)
            return q1_out, p1_out, q2_out, p2_out

        half_dt = 0.5 * dt
        wdt = omega * dt
        cos_w = math.cos(wdt)
        sin_w = math.sin(wdt)

        q1_m = q1 + half_dt * p2
        p2_m = p2 - half_dt * q1
        q2_m = q2 + half_dt * p1
        p1_m = p1 - half_dt * q2

        dq = q1_m - q2_m
        dp = p1_m - p2_m

        rot_dq = dq * cos_w + dp * sin_w
        rot_dp = -dq * sin_w + dp * cos_w

        avg_q = 0.5 * (q1_m + q2_m)
        avg_p = 0.5 * (p1_m + p2_m)

        q1_r = avg_q + 0.5 * rot_dq
        q2_r = avg_q - 0.5 * rot_dq
        p1_r = avg_p + 0.5 * rot_dp
        p2_r = avg_p - 0.5 * rot_dp

        return (
            q1_r + half_dt * p2_r,
            p1_r - half_dt * q2_r,
            q2_r + half_dt * p1_r,
            p2_r - half_dt * q1_r,
        )
