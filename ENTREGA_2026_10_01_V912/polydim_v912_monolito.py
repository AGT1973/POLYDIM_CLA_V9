# polydim_v912_monolito.py
# Monolito Python POLYDIM v912 (Master Industrial Release)
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
    """Validation check immune to python -O optimization flag."""
    if not condition:
        raise RuntimeError(f"[POLYDIM v912 INVARIANT ERROR] {message}")

# ============================================================================
# 1. ESTRUCTURA DE ERROR POD v912 (320 BYTES, PACK 8) & DLPACK NIVEL 0
# ============================================================================
class PolydimErrorv912(ctypes.Structure):
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
            raise RuntimeError(f"POLYDIM v912 FFI Error {self.code}: {err_msg}")

require(ctypes.sizeof(PolydimErrorv912) == 320, "ABI Mismatch: PolydimErrorv912 must be 320 bytes")

class DLDevice(ctypes.Structure):
    _fields_ = [("device_type", ctypes.c_int32), ("device_id", ctypes.c_int32)]

class DLDataType(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint8), ("bits", ctypes.c_uint8), ("lanes", ctypes.c_uint16)]

class DLTensor(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("device", DLDevice),
        ("ndim", ctypes.c_int32),
        ("dtype", DLDataType),
        ("shape", ctypes.POINTER(ctypes.c_int64)),
        ("strides", ctypes.POINTER(ctypes.c_int64)),
        ("byte_offset", ctypes.c_uint64),
    ]

class DLManagedTensor(ctypes.Structure):
    pass

DLManagedTensorDeleter = ctypes.CFUNCTYPE(None, ctypes.POINTER(DLManagedTensor))

DLManagedTensor._fields_ = [
    ("dl_tensor", DLTensor),
    ("manager_ctx", ctypes.c_void_p),
    ("deleter", DLManagedTensorDeleter),
]

# ============================================================================
# 2. CARGADOR DE DLLS NATIVAS C++ Y RUST v912
# ============================================================================
class PolydimEnginev912:
    def __init__(self, dll_dir: str = None):
        if dll_dir is None:
            dll_dir = os.path.dirname(os.path.abspath(__file__))

        cpp_dll_path = os.path.join(dll_dir, "polydim_cpp_v912.dll")
        rust_dll_path = os.path.join(dll_dir, "polydim_rust_v912.dll")

        if not os.path.exists(cpp_dll_path):
            raise FileNotFoundError(f"C++ DLL not found at: {cpp_dll_path}")
        if not os.path.exists(rust_dll_path):
            raise FileNotFoundError(f"Rust DLL not found at: {rust_dll_path}")

        self.cpp = ctypes.CDLL(cpp_dll_path)
        self.rust = ctypes.CDLL(rust_dll_path)
        self._bind_ffi_signatures()

    def _bind_ffi_signatures(self):
        # 1. AuON Brake C++
        self.cpp.polydim_cpp_auon_log_cosh_brake_v912.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_auon_log_cosh_brake_v912.restype = ctypes.c_int32

        # 2. AuON RMS C++
        self.cpp.polydim_cpp_auon_matrix_rms_normalize_v912.argtypes = [
            ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_auon_matrix_rms_normalize_v912.restype = ctypes.c_int32

        # 3. Geodesic C++
        self.cpp.polydim_cpp_riemannian_geodesic_v912.argtypes = [
            ctypes.c_int64, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_riemannian_geodesic_v912.restype = ctypes.c_int32

        # 4. CliffordNet C++
        self.cpp.polydim_cpp_cliffordnet_interact_v912.argtypes = [
            ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_cliffordnet_interact_v912.restype = ctypes.c_int32

        # 5. Clifford Sign C++
        self.cpp.polydim_cpp_clifford_canonical_sign_v912.argtypes = [
            ctypes.c_uint64, ctypes.c_uint64, ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_clifford_canonical_sign_v912.restype = ctypes.c_int32

        # 6. GF(2) C++
        self.cpp.polydim_cpp_gf2_bitpacked_reduction_v912.argtypes = [
            ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_gf2_bitpacked_reduction_v912.restype = ctypes.c_int32

        # 7. Stiefel Cayley C++
        self.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v912.argtypes = [
            ctypes.c_int64, ctypes.c_int64, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_stiefel_cayley_smw_retraction_v912.restype = ctypes.c_int32

        # 8. FGMRES Woodbury C++
        self.cpp.polydim_cpp_fgmres_woodbury_solve_v912.argtypes = [
            ctypes.c_int64, ctypes.c_int32, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_fgmres_woodbury_solve_v912.restype = ctypes.c_int32

        # 9. DLPack Export C++
        self.cpp.polydim_cpp_dlpack_export_tensor_v912.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_int64, ctypes.c_int64,
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.cpp.polydim_cpp_dlpack_export_tensor_v912.restype = ctypes.POINTER(DLManagedTensor)

        # 10. Rust Signatures
        self.rust.polydim_rust_auon_log_cosh_brake_v912.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_auon_log_cosh_brake_v912.restype = ctypes.c_int32

        self.rust.polydim_rust_auon_matrix_rms_normalize_v912.argtypes = [
            ctypes.c_longlong, ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_auon_matrix_rms_normalize_v912.restype = ctypes.c_int32

        self.rust.polydim_rust_riemannian_geodesic_v912.argtypes = [
            ctypes.c_longlong, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_riemannian_geodesic_v912.restype = ctypes.c_int32

        self.rust.polydim_rust_clifford_canonical_sign_v912.argtypes = [
            ctypes.c_uint64, ctypes.c_uint64, ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_clifford_canonical_sign_v912.restype = ctypes.c_int32

        self.rust.polydim_rust_bocpd_conformal_martingale_v912.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_bocpd_conformal_martingale_v912.restype = ctypes.c_int32

        self.rust.polydim_rust_fire_metric_v912.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_longlong, ctypes.c_longlong,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(PolydimErrorv912)
        ]
        self.rust.polydim_rust_fire_metric_v912.restype = ctypes.c_int32

    # High-level Python Wrappers
    def cpp_auon_brake(self, residual: float, scale_s: float = 1.0, lambda_val: float = 1.0):
        loss = ctypes.c_double(0.0)
        grad = ctypes.c_double(0.0)
        err = PolydimErrorv912()
        res = self.cpp.polydim_cpp_auon_log_cosh_brake_v912(
            residual, scale_s, lambda_val, ctypes.byref(loss), ctypes.byref(grad), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP AuON Brake failed with {res}")
        return loss.value, grad.value

    def cpp_auon_matrix_rms_normalize(self, matrix: np.ndarray):
        require(matrix.ndim == 2, "Matrix must be 2D")
        rows, cols = matrix.shape
        in_buf = np.ascontiguousarray(matrix, dtype=np.float64)
        out_buf = np.empty_like(in_buf)
        rms = ctypes.c_double(0.0)
        err = PolydimErrorv912()
        res = self.cpp.polydim_cpp_auon_matrix_rms_normalize_v912(
            rows, cols,
            in_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(rms), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP RMS Normalize failed with {res}")
        return out_buf, rms.value

    def cpp_riemannian_geodesic(self, u: np.ndarray, v: np.ndarray):
        require(u.ndim == 1 and v.ndim == 1 and len(u) == len(v), "Vectors must be 1D of equal length")
        dim = len(u)
        u_buf = np.ascontiguousarray(u, dtype=np.float64)
        v_buf = np.ascontiguousarray(v, dtype=np.float64)
        ang = ctypes.c_double(0.0)
        chord = ctypes.c_double(0.0)
        err = PolydimErrorv912()
        res = self.cpp.polydim_cpp_riemannian_geodesic_v912(
            dim,
            u_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(ang), ctypes.byref(chord), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP Geodesic failed with {res}")
        return ang.value, chord.value

    def cpp_cliffordnet_interact(self, vecs: np.ndarray):
        require(vecs.ndim == 2, "Vecs must be 2D (n_samples, k_dim)")
        n_samples, k_dim = vecs.shape
        bivec_dim = (k_dim * (k_dim - 1)) // 2
        in_buf = np.ascontiguousarray(vecs, dtype=np.float64)
        out_buf = np.empty((n_samples, bivec_dim), dtype=np.float64)
        energy = ctypes.c_double(0.0)
        err = PolydimErrorv912()
        res = self.cpp.polydim_cpp_cliffordnet_interact_v912(
            n_samples, k_dim,
            in_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(energy), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP CliffordNet failed with {res}")
        return out_buf, energy.value

    def cpp_clifford_canonical_sign(self, mask_a: int, mask_b: int) -> int:
        err = PolydimErrorv912()
        sign = self.cpp.polydim_cpp_clifford_canonical_sign_v912(mask_a, mask_b, ctypes.byref(err))
        err.check_ok()
        return sign

    def rust_clifford_canonical_sign(self, mask_a: int, mask_b: int) -> int:
        err = PolydimErrorv912()
        sign = self.rust.polydim_rust_clifford_canonical_sign_v912(mask_a, mask_b, ctypes.byref(err))
        err.check_ok()
        return sign

    def cpp_gf2_bitpacked_reduction(self, matrix: np.ndarray):
        require(matrix.ndim == 2 and matrix.dtype == np.uint64, "Matrix must be 2D uint64")
        rows, cols = matrix.shape
        in_buf = np.ascontiguousarray(matrix, dtype=np.uint64)
        out_buf = np.empty_like(in_buf)
        rank = ctypes.c_int64(0)
        err = PolydimErrorv912()
        res = self.cpp.polydim_cpp_gf2_bitpacked_reduction_v912(
            rows, cols,
            in_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            out_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
            ctypes.byref(rank), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP GF(2) failed with {res}")
        return out_buf, rank.value

    def cpp_fgmres_woodbury_solve(self, b: np.ndarray, max_iter: int = 30, tol: float = 1e-6):
        require(b.ndim == 1, "Vector b must be 1D")
        dim = len(b)
        b_buf = np.ascontiguousarray(b, dtype=np.float64)
        x_out = np.zeros(dim, dtype=np.float64)
        iters_out = ctypes.c_int32(0)
        res_out = ctypes.c_double(0.0)
        state_out = ctypes.c_int32(0)
        err = PolydimErrorv912()

        res = self.cpp.polydim_cpp_fgmres_woodbury_solve_v912(
            dim, max_iter, tol,
            b_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            x_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(iters_out), ctypes.byref(res_out), ctypes.byref(state_out),
            ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"CPP FGMRES Solve failed with {res}")
        return x_out, iters_out.value, res_out.value, state_out.value

    def rust_bocpd_conformal_martingale(self, sequence: np.ndarray, hazard_lambda: float = 100.0):
        require(sequence.ndim == 1, "Sequence must be 1D")
        seq_buf = np.ascontiguousarray(sequence, dtype=np.float64)
        e_val = ctypes.c_double(0.0)
        prob = ctypes.c_double(0.0)
        err = PolydimErrorv912()

        res = self.rust.polydim_rust_bocpd_conformal_martingale_v912(
            seq_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            len(sequence), hazard_lambda,
            ctypes.byref(e_val), ctypes.byref(prob), ctypes.byref(err)
        )
        err.check_ok()
        require(res == 0, f"Rust BOCPD Martingale failed with {res}")
        return e_val.value, prob.value

# ============================================================================
# 3. MONITOR TOPOLÓGICO CONFORMAL MARTINGALE + BOCPD (SOTA V912)
# ============================================================================
class EProcessMartingaleMonitor:
    def __init__(self, hazard_lambda: float = 100.0, alpha_target: float = 0.05):
        self.hazard_lambda = hazard_lambda
        self.alpha_target = alpha_target
        self.threshold = 1.0 / alpha_target
        self.history = []
        self.e_values = []

    def update(self, val: float, engine: PolydimEnginev912 = None):
        self.history.append(val)
        if engine is not None and len(self.history) >= 2:
            e_val, prob = engine.rust_bocpd_conformal_martingale(
                np.array(self.history, dtype=np.float64), self.hazard_lambda
            )
            self.e_values.append(e_val)
            alarm = e_val >= self.threshold
            return e_val, prob, alarm
        return 1.0, 0.0, False

# ============================================================================
# 4. MEMORIA COMPARTIDA WIN32 PMTP RAII CON CONTABILIDAD DE HANDLES
# ============================================================================
class PmtpSlabAllocatorWin:
    def __init__(self, name: str, size_bytes: int):
        self.name = name
        self.size_bytes = size_bytes
        self.handle = None
        self.view = None
        self.is_closed = False

        if sys.platform == 'win32' and size_bytes > 0:
            FILE_MAP_ALL_ACCESS = 0xF001F
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
            PAGE_READWRITE = 0x04

            CreateFileMappingW = ctypes.windll.kernel32.CreateFileMappingW
            CreateFileMappingW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p]
            CreateFileMappingW.restype = ctypes.c_void_p

            MapViewOfFile = ctypes.windll.kernel32.MapViewOfFile
            MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
            MapViewOfFile.restype = ctypes.c_void_p

            self.handle = CreateFileMappingW(INVALID_HANDLE_VALUE, None, PAGE_READWRITE, 0, size_bytes, name)
            if not self.handle or self.handle == 0:
                raise RuntimeError(f'Failed to create FileMapping {name}')

            self.view = MapViewOfFile(self.handle, FILE_MAP_ALL_ACCESS, 0, 0, size_bytes)
            if not self.view or self.view == 0:
                ctypes.windll.kernel32.CloseHandle(self.handle)
                self.handle = None
                raise RuntimeError(f'Failed to MapViewOfFile {name}')

    def write_tensor(self, arr: np.ndarray):
        if self.is_closed or not self.view:
            raise RuntimeError('PMTP Slab is closed or unmapped')
        data_bytes = arr.tobytes()
        if len(data_bytes) > self.size_bytes:
            raise RuntimeError(f'Data size {len(data_bytes)} exceeds slab capacity {self.size_bytes}')
        ctypes.memmove(self.view, data_bytes, len(data_bytes))

    def read_tensor(self, dtype=np.float64, count: int = -1) -> np.ndarray:
        if self.is_closed or not self.view:
            raise RuntimeError('PMTP Slab is closed or unmapped')
        if count <= 0:
            count = self.size_bytes // np.dtype(dtype).itemsize
        buf = (ctypes.c_char * (count * np.dtype(dtype).itemsize)).from_address(self.view)
        return np.frombuffer(buf, dtype=dtype, count=count)

    def close(self):
        if not self.is_closed:
            if sys.platform == 'win32':
                if self.view:
                    ctypes.windll.kernel32.UnmapViewOfFile(ctypes.c_void_p(self.view))
                    self.view = None
                if self.handle:
                    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
                    self.handle = None
            self.is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class GenerationalBatchHNSW:
    def __init__(self, dim: int):
        self.dim = dim
        self.nodes = []
        self.version = 0

    def insert_batch(self, batch: np.ndarray):
        require(batch.ndim == 2 and batch.shape[1] == self.dim, "Batch dim mismatch")
        if len(batch) == 0:
            return
        # Copy-on-write snapshot update
        self.nodes.extend(batch.tolist())
        self.version += 1

# ============================================================================
# 6. INDEXADOR DE HOJAS DISPERSAS DE CLIFFORD CON SIGNO CANÓNICO
# ============================================================================
def _clifford_canonical_sign(m1: int, m2: int) -> int:
    transpositions = 0
    temp_m2 = m2
    while temp_m2 > 0:
        bit_idx = (temp_m2 & -temp_m2).bit_length() - 1
        higher_mask = ~((1 << (bit_idx + 1)) - 1)
        bits_above = m1 & higher_mask
        transpositions += bin(bits_above).count('1')
        temp_m2 &= temp_m2 - 1
    return -1 if (transpositions % 2 == 1) else 1

class SparseCliffordBladeIndexer:
    def __init__(self, dim: int):
        self.dim = dim
        self.blades = {}

    def set_blade(self, mask: int, coeff: float):
        if abs(coeff) > 1e-15:
            self.blades[mask] = coeff
        elif mask in self.blades:
            del self.blades[mask]

    def geometric_product(self, other: 'SparseCliffordBladeIndexer') -> 'SparseCliffordBladeIndexer':
        res = SparseCliffordBladeIndexer(self.dim)
        for m1, c1 in self.blades.items():
            for m2, c2 in other.blades.items():
                sign = _clifford_canonical_sign(m1, m2)
                res_mask = m1 ^ m2
                res.blades[res_mask] = res.blades.get(res_mask, 0.0) + sign * c1 * c2
        return res
