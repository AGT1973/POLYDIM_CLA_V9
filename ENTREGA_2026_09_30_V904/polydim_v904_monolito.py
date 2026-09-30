# polydim_v904_monolito.py
# Monolito Python POLYDIM V904 (Master Industrial Release)
# ============================================================================

import os
import sys
import ctypes
import numpy as np
import math

# Windows MinGW DLL Directory Registration
if sys.platform == "win32":
    mingw_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(mingw_bin):
        try:
            os.add_dll_directory(mingw_bin)
        except Exception:
            pass

# ============================================================================
# INVARIANTE MATEMÁTICA / CHECKER INMUNE A `python -O` (SOTA Grupo E)
# ============================================================================
def require(condition: bool, message: str = "Invariant violation"):
    """
    Validation check immune to python -O optimization flag.
    Throws RuntimeError on failure.
    """
    if not condition:
        raise RuntimeError(f"[POLYDIM V904 INVARIANT ERROR] {message}")

# ============================================================================
# 1. ESTRUCTURA DE ERROR Y CORTAFUEGOS FFI POD V904 (320 BYTES, PACK 8)
# ============================================================================
class PolydimErrorV904(ctypes.Structure):
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
            raise RuntimeError(f"POLYDIM V904 FFI Error {self.code}: {err_msg}")

require(ctypes.sizeof(PolydimErrorV904) == 320, "ABI Mismatch: PolydimErrorV904 must be 320 bytes")

# ============================================================================
# 2. CARGADOR DE DLLS NATIVAS C++ Y RUST V904
# ============================================================================
class PolydimEngineV904:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.base_dir = base_dir
        self.cpp_dll_path = os.path.join(base_dir, "polydim_cpp_v904.dll")
        self.rust_dll_path = os.path.join(base_dir, "polydim_rust_v904.dll")

        require(os.path.exists(self.cpp_dll_path), f"C++ DLL missing at {self.cpp_dll_path}")
        require(os.path.exists(self.rust_dll_path), f"Rust DLL missing at {self.rust_dll_path}")

        try:
            self.cpp = ctypes.CDLL(self.cpp_dll_path)
        except OSError:
            self.cpp = ctypes.CDLL(self.cpp_dll_path, winmode=0)

        try:
            self.rust = ctypes.CDLL(self.rust_dll_path)
        except OSError:
            self.rust = ctypes.CDLL(self.rust_dll_path, winmode=0)

        self._bind_functions()

    def _bind_functions(self):
        # C++ Binds
        self.cpp.polydim_cpp_auon_log_cosh_brake_v904.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_auon_log_cosh_brake_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_riemannian_geodesic_v904.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_riemannian_geodesic_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_two_nn_intrinsic_dim_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_two_nn_intrinsic_dim_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_baraniuk_wakin_feasibility_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_baraniuk_wakin_feasibility_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_cliffordnet_bivector_interact_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_cliffordnet_bivector_interact_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_hybrid_auon_orthogonalization_v904.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_hybrid_auon_orthogonalization_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_fire_metric_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_fire_metric_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_clifford_drift_bound_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_clifford_drift_bound_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v904.restype = ctypes.c_int

        self.cpp.polydim_cpp_gf2_bitpacked_reduction_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.cpp.polydim_cpp_gf2_bitpacked_reduction_v904.restype = ctypes.c_int

        # Rust Binds
        self.rust.polydim_rust_auon_log_cosh_brake_v904.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.rust.polydim_rust_auon_log_cosh_brake_v904.restype = ctypes.c_int

        self.rust.polydim_rust_riemannian_geodesic_v904.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.rust.polydim_rust_riemannian_geodesic_v904.restype = ctypes.c_int

        self.rust.polydim_rust_cliffordnet_bivector_interact_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.rust.polydim_rust_cliffordnet_bivector_interact_v904.restype = ctypes.c_int

        self.rust.polydim_rust_fire_metric_v904.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(PolydimErrorV904)
        ]
        self.rust.polydim_rust_fire_metric_v904.restype = ctypes.c_int

    # Python FFI Wrappers
    def cpp_auon_brake(self, residual: float, scale_s: float = 1.0, lambda_val: float = 1.0):
        loss_out = ctypes.c_double(0.0)
        grad_out = ctypes.c_double(0.0)
        err = PolydimErrorV904()
        res = self.cpp.polydim_cpp_auon_log_cosh_brake_v904(
            float(residual), float(scale_s), float(lambda_val),
            ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err)
        )
        require(res == 0, f"cpp_auon_brake returned {res}")
        err.check_ok()
        return loss_out.value, grad_out.value

    def cpp_riemannian_geodesic(self, u: np.ndarray, v: np.ndarray):
        require(u.shape == v.shape, "Vector shapes must match")
        u_c = np.ascontiguousarray(u, dtype=np.float64)
        v_c = np.ascontiguousarray(v, dtype=np.float64)
        dim = u_c.size

        ang = ctypes.c_double(0.0)
        chord = ctypes.c_double(0.0)
        err = PolydimErrorV904()

        res = self.cpp.polydim_cpp_riemannian_geodesic_v904(
            u_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            dim, ctypes.byref(ang), ctypes.byref(chord), ctypes.byref(err)
        )
        require(res == 0, f"cpp_riemannian_geodesic returned {res}")
        err.check_ok()
        return ang.value, chord.value

    def cpp_cliffordnet_interact(self, vectors: np.ndarray):
        require(vectors.ndim == 2, "Input must be 2D array (N, K)")
        n, k = vectors.shape
        require(k >= 2, "K must be >= 2")
        vec_c = np.ascontiguousarray(vectors, dtype=np.float64)
        bivec_dim = (k * (k - 1)) // 2
        bivec_out = np.zeros((n, bivec_dim), dtype=np.float64)
        energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV904()

        res = self.cpp.polydim_cpp_cliffordnet_bivector_interact_v904(
            n, k,
            vec_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivec_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(energy_out), ctypes.byref(err)
        )
        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        return bivec_out, energy_out.value

    def cpp_gf2_bitpacked_reduction(self, matrix_bitpacked: np.ndarray):
        require(matrix_bitpacked.ndim == 2, "Matrix must be 2D uint64 array")
        r, c = matrix_bitpacked.shape
        in_c = np.ascontiguousarray(matrix_bitpacked, dtype=np.uint64)
        out_c = np.zeros_like(in_c)
        rank_out = ctypes.c_uint32(0)
        err = PolydimErrorV904()

        res = self.cpp.polydim_cpp_gf2_bitpacked_reduction_v904(
            r, c,
            in_c.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            out_c.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            ctypes.byref(rank_out), ctypes.byref(err)
        )
        require(res == 0, f"cpp_gf2_bitpacked_reduction returned {res}")
        err.check_ok()
        return out_c, rank_out.value

if __name__ == "__main__":
    print("=== POLYDIM V904 MONOLITH MONITORED INITIATION ===")
    engine = PolydimEngineV904()
    l, g = engine.cpp_auon_brake(0.5, 1.0, 1.0)
    print(f"AuON Log-Cosh Brake PASS: loss={l:.6f}, grad={g:.6f}")
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([0.0, 1.0, 0.0])
    ang, chord = engine.cpp_riemannian_geodesic(u, v)
    print(f"Geodesic PASS: angle={ang:.6f}, chordal={chord:.6f}")
