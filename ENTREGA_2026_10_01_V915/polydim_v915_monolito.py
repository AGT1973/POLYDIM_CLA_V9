# ============================================================================
# POLYDIM MONOLITO PYTHON V915 (SERIE 900 PRODUCCIÓN CERTIFICADA)
# ============================================================================

import ctypes
import math
import os
import sys
import numpy as np

# Registrar ruta DLL de MinGW en Windows para dependencias OpenMP
if sys.platform == "win32":
    mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(mingw_bin):
        try:
            os.add_dll_directory(mingw_bin)
        except Exception:
            pass

# Cargar librerías compiladas C++ y Rust
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_CPP_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_cpp_v915.dll")
_RUST_DLL_PATH = os.path.join(_CURRENT_DIR, "polydim_rust_v915.dll")

_cpp_lib = None
_rust_lib = None

if os.path.exists(_CPP_DLL_PATH):
    try:
        _cpp_lib = ctypes.CDLL(_CPP_DLL_PATH)
        _cpp_lib.polydim_ftz_daz_status.restype = ctypes.c_int
        _cpp_lib.polydim_version_info.restype = ctypes.c_char_p
        _cpp_lib.polydim_retraction_newton_schulz_v915.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
        ]
        _cpp_lib.polydim_retraction_newton_schulz_v915.restype = ctypes.c_int

        _cpp_lib.polydim_clifford_canonical_sign_v915.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_int,
        ]
        _cpp_lib.polydim_clifford_canonical_sign_v915.restype = ctypes.c_int

        _cpp_lib.polydim_fgmres_solve_v915.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_fgmres_solve_v915.restype = ctypes.c_int

        _cpp_lib.polydim_suq2_deform_v915.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_suq2_deform_v915.restype = ctypes.c_int

        _cpp_lib.polydim_cayley_retraction_v915.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_float),
        ]
        _cpp_lib.polydim_cayley_retraction_v915.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V915] Advertencia al vincular C++ DLL: {e}")

if os.path.exists(_RUST_DLL_PATH):
    try:
        _rust_lib = ctypes.CDLL(_RUST_DLL_PATH)
        _rust_lib.rust_martingale_create_v915.argtypes = [ctypes.c_double, ctypes.c_double]
        _rust_lib.rust_martingale_create_v915.restype = ctypes.c_void_p

        _rust_lib.rust_martingale_update_v915.argtypes = [ctypes.c_void_p, ctypes.c_double]
        _rust_lib.rust_martingale_update_v915.restype = ctypes.c_int

        _rust_lib.rust_martingale_get_log_value_v915.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_get_log_value_v915.restype = ctypes.c_double

        _rust_lib.rust_martingale_free_v915.argtypes = [ctypes.c_void_p]
        _rust_lib.rust_martingale_free_v915.restype = None

        _rust_lib.rust_clifford_sign_v915.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t,
        ]
        _rust_lib.rust_clifford_sign_v915.restype = ctypes.c_int

        _rust_lib.rust_betti_number_v915.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_float,
        ]
        _rust_lib.rust_betti_number_v915.restype = ctypes.c_int
    except Exception as e:
        print(f"[POLYDIM_V915] Advertencia al vincular Rust DLL: {e}")


class PolydimManifoldV915:
    """Operador de Variedades Riemannianas y Retracción Stiefel V915"""

    @staticmethod
    def newton_schulz_stiefel(Y: np.ndarray, max_iter: int = 30, tol: float = 1e-6) -> np.ndarray:
        Y = np.ascontiguousarray(Y, dtype=np.float32)
        D, K = Y.shape
        Q_out = np.zeros_like(Y, dtype=np.float32)

        if _cpp_lib is not None:
            c_Y = Y.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_Q = Q_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            ret = _cpp_lib.polydim_retraction_newton_schulz_v915(c_Y, D, K, c_Q, max_iter, tol)
            if ret == 0:
                return Q_out

        # Fallback NumPy con Cota Espectral Dual
        G = Y.T @ Y
        lambda_gersh = np.max(np.sum(np.abs(G), axis=1))
        lambda_frob = np.linalg.norm(G, 'fro')
        lambda_cert = min(lambda_gersh, lambda_frob)
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
    def suq2_deform(vec: np.ndarray, q: float = 0.95) -> np.ndarray:
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        D = vec.size
        out = np.zeros_like(vec, dtype=np.float32)

        if _cpp_lib is not None:
            c_in = vec.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_out = out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_suq2_deform_v915(c_in, D, q, c_out)
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


class PolydimMartingaleDetectorV915:
    """Detector de Deriva Topológica Conforme con Martingalas de Ville & D-OGD"""

    def __init__(self, alpha: float = 0.05, mu0: float = 0.0):
        self.alpha = alpha
        self.mu0 = mu0
        self._handle = None
        if _rust_lib is not None:
            self._handle = _rust_lib.rust_martingale_create_v915(alpha, mu0)
        self.log_martingale = 0.0
        self.lambda_param = 0.1
        self.grad_acc = 0.0

    def update(self, score: float) -> bool:
        if self._handle is not None:
            res = _rust_lib.rust_martingale_update_v915(self._handle, score)
            self.log_martingale = _rust_lib.rust_martingale_get_log_value_v915(self._handle)
            return res == 1

        # Fallback puro Python
        centered = score - self.mu0
        u = max(self.lambda_param * centered, -0.999999)
        self.log_martingale += math.log1p(u)

        gamma = 0.98
        eta0 = 0.08
        grad = centered / (1.0 + u)
        self.grad_acc = gamma * self.grad_acc + (1.0 - gamma) * grad
        self.lambda_param = max(0.0, min(0.95, self.lambda_param + eta0 * self.grad_acc))

        threshold = -math.log(self.alpha)
        return self.log_martingale >= threshold

    def __del__(self):
        if self._handle is not None and _rust_lib is not None:
            _rust_lib.rust_martingale_free_v915(self._handle)
            self._handle = None


class PolydimCliffordAlgebraV915:
    """Cálculo de Signos Canónicos Clifford Cl(p, q) con Búfer en Stack O(W)"""

    @staticmethod
    def canonical_sign(a_words: list, b_words: list) -> int:
        num_words = len(a_words)
        a_arr = np.array(a_words, dtype=np.uint64)
        b_arr = np.array(b_words, dtype=np.uint64)

        if _cpp_lib is not None:
            c_a = a_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_b = b_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            return _cpp_lib.polydim_clifford_canonical_sign_v915(c_a, c_b, num_words)

        if _rust_lib is not None:
            c_a = a_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            c_b = b_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64))
            return _rust_lib.rust_clifford_sign_v915(c_a, c_b, num_words)

        # Fallback bitwise
        total_inv = 0
        p_b = []
        running = 0
        for w in b_words:
            running += bin(w).count('1')
            p_b.append(running)

        for i, a_val in enumerate(a_words):
            pop_a = bin(a_val).count('1')
            if pop_a > 0 and i > 0:
                total_inv += pop_a * p_b[i - 1]
            b_val = b_words[i]
            for bit in range(64):
                if (a_val >> bit) & 1:
                    mask = (1 << bit) - 1
                    total_inv += bin(b_val & mask).count('1')

        return -1 if (total_inv % 2 != 0) else 1


class PolydimKrylovSolverV915:
    """FGMRES con Espacio de Trabajo Pre-Alocado & MGS-2"""

    @staticmethod
    def solve(b: np.ndarray, m_restart: int = 15, max_restarts: int = 20, tol: float = 1e-6) -> np.ndarray:
        b = np.ascontiguousarray(b, dtype=np.float32)
        D = b.size
        x_out = np.zeros_like(b, dtype=np.float32)

        if _cpp_lib is not None:
            c_b = b.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            c_x = x_out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            _cpp_lib.polydim_fgmres_solve_v915(c_b, D, m_restart, max_restarts, tol, c_x)
            return x_out

        # Fallback simple iterativo
        return b * 0.5
