r"""
polydim_v903_monolito.py
Monolito Orquestador POLYDIM V903 (Master Industrial Release)

===============================================================================
GUÍA PEDAGÓGICA Y ALCANCE TEÓRICO PARA CIENTÍFICOS DE DATOS E INVESTIGADORES:
===============================================================================

1. ¿Cuál es el problema fundamental que resuelve POLYDIM?
   En los sistemas tradicionales de Inteligencia Artificial Multi-Agente (p. ej. AutoGen, CrewAI),
   los modelos comunican su conocimiento colapsando tensores continuos de alta dimensión
   en cadenas de texto discreto (Gusano 1D):
       Modelo A (Tensor Latente) -> Decodificación Autoregresiva -> Texto (JSON/Tokens) -> Modelo B (Lectura & Re-embedding)
   
   Este proceso destruye la geometría latente continua por la Desigualdad de Procesamiento
   de Información (DPI) de Shannon:
       I(Tarea; Texto) = I(Tarea; Latente) - I(Tarea; Latente | Texto) <= I(Tarea; Latente)
   donde el término I(Tarea; Latente | Texto) representa la pérdida irreversible de entropía útil.

2. La Solución POLYDIM: Intercambio Directo en Variedades S^(D-1) vía PMTP
   POLYDIM mantiene los estados en su variedad nativa hiperdimensional S^(D-1) y los transfiere
   directamente a través de memoria compartida (Zero-Copy IPC / PMTP) en microsegundos.

3. Teoremas y Contratos Matemáticos V903 Integrados:
   a) Secante RIP Manifold: Control de distorsión empírica en reducción de dimensión.
   b) Métrica Geodésica Riemanniana: d_S(u, v) = arccos(clip(u^T v, -1.0, 1.0)) en S^(D-1).
   c) Homología Simplicial Exacta: 1-Laplaciano de Hodge \Delta_1 y anulación de 2-símplices (\beta_1 = dim ker B_1 - rank B_2).
   d) Freno Numérico AuON: log-cosh numéricamente incondicionado con gradiente analítico acotado por \lambda * s.
   e) Multi-K MAP Bayesiano: Estimador de dimensión intrínseca con prior Gamma conjugado (\alpha=2.0, \beta=1e-3).
   f) CliffordNet 2026: Producto bivectorial exterior compacto K(K-1)/2 y Sparse Rolling Interaction (SRI, S=5).
   g) Métrica FIRE: Frobenius-Isometry Reinitialization metric tracking ||Q^T Q - I_K||_F / sqrt(K).
"""

import ctypes
import math
import os
import sys
from typing import Tuple, List, Optional, Dict, Any
import numpy as np

# Configuración de ruta de DLLs en Windows
if sys.platform == "win32":
    winlibs_bin = r"E:\winlibs_gcc14_zip\mingw64\bin"
    if os.path.exists(winlibs_bin) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(winlibs_bin)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(src_dir) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(src_dir)

# =============================================================================
# ESTRUCTURA FFI POD PARA TELEMETRÍA Y ERRORES V903 (ALIGN 64, 320 BYTES)
# =============================================================================

class PolydimErrorV903(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("code", ctypes.c_uint32),
        ("msg", ctypes.c_char * 256),
        ("arena_id", ctypes.c_uint64),
        ("gen", ctypes.c_uint64),
        ("_pad", ctypes.c_uint8 * 40),
    ]

    def is_ok(self) -> bool:
        return self.code == 0

    def message(self) -> str:
        return self.msg.decode("utf-8", errors="replace").strip("\x00")

# =============================================================================
# BINDING NATIVO RUST (polydim_rust_v903.dll)
# =============================================================================

class PolydimRustKernelV903:
    """Guardián topológico y numérico en Rust nativo."""

    def __init__(self, dll_path: Optional[str] = None):
        if dll_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(base_dir, "polydim_rust_v903.dll")

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"No se encontró la DLL de Rust en: {dll_path}")

        self.lib = ctypes.CDLL(dll_path)
        self._setup_signatures()

    def _setup_signatures(self):
        self.lib.polydim_rust_get_last_error_v903.restype = ctypes.c_void_p
        self.lib.polydim_rust_get_last_error_v903.argtypes = []

        self.lib.polydim_rust_clear_last_error_v903.restype = None
        self.lib.polydim_rust_clear_last_error_v903.argtypes = []

        self.lib.polydim_rust_auon_log_cosh_brake_v903.restype = ctypes.c_int
        self.lib.polydim_rust_auon_log_cosh_brake_v903.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_riemannian_geodesic_v903.restype = ctypes.c_int
        self.lib.polydim_rust_riemannian_geodesic_v903.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_simplicial_homology_hodge_v903.restype = ctypes.c_int
        self.lib.polydim_rust_simplicial_homology_hodge_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
            ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_longlong),
            ctypes.POINTER(ctypes.c_longlong), ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_two_nn_intrinsic_dim_v903.restype = ctypes.c_int
        self.lib.polydim_rust_two_nn_intrinsic_dim_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_baraniuk_wakin_feasibility_v903.restype = ctypes.c_int
        self.lib.polydim_rust_baraniuk_wakin_feasibility_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_double, ctypes.c_double,
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_secant_distortion_eval_v903.restype = ctypes.c_int
        self.lib.polydim_rust_secant_distortion_eval_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_qsbr_snapshot_copy_v903.restype = ctypes.c_int
        self.lib.polydim_rust_qsbr_snapshot_copy_v903.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_cliffordnet_bivector_interact_v903.restype = ctypes.c_int
        self.lib.polydim_rust_cliffordnet_bivector_interact_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_rust_fire_metric_v903.restype = ctypes.c_int
        self.lib.polydim_rust_fire_metric_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.c_double, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(PolydimErrorV903),
        ]

    def get_last_error_string(self) -> str:
        ptr = self.lib.polydim_rust_get_last_error_v903()
        if not ptr:
            return ""
        return ctypes.string_at(ptr).decode("utf-8", errors="replace")

    def auon_brake(self, residual: float, scale_s: float = 1.0, lambda_val: float = 1.0) -> Tuple[float, float]:
        loss_out = ctypes.c_double(0.0)
        grad_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_auon_log_cosh_brake_v903(
            ctypes.c_double(residual), ctypes.c_double(scale_s), ctypes.c_double(lambda_val),
            ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust auon_brake falló ({ret}): {err.message() or self.get_last_error_string()}")
        return loss_out.value, grad_out.value

    def riemannian_geodesic(self, u: np.ndarray, v: np.ndarray) -> Tuple[float, float]:
        u_arr = np.ascontiguousarray(u, dtype=np.float64)
        v_arr = np.ascontiguousarray(v, dtype=np.float64)
        dim = len(u_arr)
        ang_out = ctypes.c_double(0.0)
        chord_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_riemannian_geodesic_v903(
            u_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_uint(dim), ctypes.byref(ang_out), ctypes.byref(chord_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust riemannian_geodesic falló ({ret}): {err.message() or self.get_last_error_string()}")
        return ang_out.value, chord_out.value

    def simplicial_homology(self, num_vertices: int, edges: List[Tuple[int, int]], triangles: List[Tuple[int, int, int]]) -> Dict[str, Any]:
        ne = len(edges)
        nt = len(triangles)
        edges_flat = np.array(edges, dtype=np.uint32).flatten() if ne > 0 else np.array([], dtype=np.uint32)
        triangles_flat = np.array(triangles, dtype=np.uint32).flatten() if nt > 0 else np.array([], dtype=np.uint32)
        b0_out = ctypes.c_uint(0)
        b1_simplicial_out = ctypes.c_longlong(0)
        graph_cycle_rank_out = ctypes.c_longlong(0)
        err = PolydimErrorV903()
        edges_ptr = edges_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)) if ne > 0 else None
        triangles_ptr = triangles_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)) if nt > 0 else None
        ret = self.lib.polydim_rust_simplicial_homology_hodge_v903(
            ctypes.c_uint(num_vertices), ctypes.c_uint(ne), edges_ptr,
            ctypes.c_uint(nt), triangles_ptr,
            ctypes.byref(b0_out), ctypes.byref(b1_simplicial_out), ctypes.byref(graph_cycle_rank_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust simplicial_homology falló ({ret}): {err.message() or self.get_last_error_string()}")
        return {
            "betti_0": b0_out.value,
            "betti_1_simplicial": b1_simplicial_out.value,
            "graph_cycle_rank": graph_cycle_rank_out.value,
            "faces_filling_cycles": graph_cycle_rank_out.value - b1_simplicial_out.value,
        }

    def secant_distortion_eval(self, orig_points: np.ndarray, proj_points: np.ndarray) -> Dict[str, float]:
        orig_arr = np.ascontiguousarray(orig_points, dtype=np.float64)
        proj_arr = np.ascontiguousarray(proj_points, dtype=np.float64)
        n, din = orig_arr.shape
        _, dout = proj_arr.shape
        l_min_out = ctypes.c_double(0.0)
        l_max_out = ctypes.c_double(0.0)
        delta_max_out = ctypes.c_double(0.0)
        secant_alpha_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_secant_distortion_eval_v903(
            ctypes.c_uint(n), ctypes.c_uint(din), ctypes.c_uint(dout),
            orig_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            proj_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(l_min_out), ctypes.byref(l_max_out), ctypes.byref(delta_max_out), ctypes.byref(secant_alpha_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust secant_distortion_eval falló ({ret}): {err.message() or self.get_last_error_string()}")
        return {"l_min": l_min_out.value, "l_max": l_max_out.value, "delta_max": delta_max_out.value, "secant_alpha": secant_alpha_out.value}

    def two_nn_intrinsic_dim(self, points: np.ndarray) -> Dict[str, float]:
        pts_arr = np.ascontiguousarray(points, dtype=np.float64)
        n, dim = pts_arr.shape
        d_mle_out = ctypes.c_double(0.0)
        d_ucb_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_two_nn_intrinsic_dim_v903(
            ctypes.c_uint(n), ctypes.c_uint(dim),
            pts_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(d_mle_out), ctypes.byref(d_ucb_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust two_nn_intrinsic_dim falló ({ret}): {err.message() or self.get_last_error_string()}")
        return {"d_intrinsic_mle": d_mle_out.value, "d_intrinsic_ucb": d_ucb_out.value}

    def baraniuk_wakin_feasibility(
        self, dim_in: int, dim_out: int, intrinsic_dim: float,
        epsilon: float = 0.1, reach: float = 0.5, volume: float = 100.0, failure_rho: float = 0.01
    ) -> Tuple[float, bool]:
        m_req_out = ctypes.c_double(0.0)
        feasible_out = ctypes.c_uint8(0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_baraniuk_wakin_feasibility_v903(
            ctypes.c_uint(dim_in), ctypes.c_uint(dim_out), ctypes.c_double(intrinsic_dim),
            ctypes.c_double(epsilon), ctypes.c_double(reach), ctypes.c_double(volume), ctypes.c_double(failure_rho),
            ctypes.byref(m_req_out), ctypes.byref(feasible_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust baraniuk_wakin_feasibility falló ({ret}): {err.message() or self.get_last_error_string()}")
        return m_req_out.value, bool(feasible_out.value)

    def cliffordnet_interact(self, vectors: np.ndarray) -> Tuple[np.ndarray, float]:
        vecs_arr = np.ascontiguousarray(vectors, dtype=np.float64)
        n, k = vecs_arr.shape
        bivec_dim = (k * (k - 1)) // 2
        bivecs_out = np.zeros((n, bivec_dim), dtype=np.float64)
        energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_cliffordnet_bivector_interact_v903(
            ctypes.c_uint(n), ctypes.c_uint(k),
            vecs_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivecs_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(energy_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust cliffordnet_interact falló ({ret}): {err.message() or self.get_last_error_string()}")
        return bivecs_out, energy_out.value

    def fire_metric(self, q_matrix: np.ndarray, threshold: float = 1e-6) -> Tuple[float, bool]:
        q_arr = np.ascontiguousarray(q_matrix, dtype=np.float64)
        d, k = q_arr.shape
        drift_out = ctypes.c_double(0.0)
        reinit_out = ctypes.c_uint8(0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_rust_fire_metric_v903(
            ctypes.c_uint(d), ctypes.c_uint(k),
            q_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_double(threshold),
            ctypes.byref(drift_out), ctypes.byref(reinit_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"Rust fire_metric falló ({ret}): {err.message() or self.get_last_error_string()}")
        return drift_out.value, bool(reinit_out.value)


# =============================================================================
# BINDING NATIVO C++ (polydim_cpp_v903.dll)
# =============================================================================

class PolydimCppKernelV903:
    """Motor C++20 OpenMP / SIMD para Stiefel SMW, AuON y CliffordNet."""

    def __init__(self, dll_path: Optional[str] = None):
        if dll_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(base_dir, "polydim_cpp_v903.dll")

        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"No se encontró la DLL de C++ en: {dll_path}")

        self.lib = ctypes.CDLL(dll_path)
        self._setup_signatures()

    def _setup_signatures(self):
        self.lib.polydim_cpp_auon_log_cosh_brake_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_auon_log_cosh_brake_v903.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_riemannian_geodesic_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_riemannian_geodesic_v903.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_two_nn_intrinsic_dim_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_two_nn_intrinsic_dim_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_secant_distortion_eval_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_secant_distortion_eval_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_stiefel_cayley_smw_retraction_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_stiefel_cayley_smw_retraction_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_cliffordnet_bivector_interact_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_cliffordnet_bivector_interact_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(PolydimErrorV903),
        ]

        self.lib.polydim_cpp_fire_metric_v903.restype = ctypes.c_int
        self.lib.polydim_cpp_fire_metric_v903.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_double),
            ctypes.c_double, ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(PolydimErrorV903),
        ]

    def auon_brake(self, residual: float, scale_s: float = 1.0, lambda_val: float = 1.0) -> Tuple[float, float]:
        loss_out = ctypes.c_double(0.0)
        grad_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_auon_log_cosh_brake_v903(
            ctypes.c_double(residual), ctypes.c_double(scale_s), ctypes.c_double(lambda_val),
            ctypes.byref(loss_out), ctypes.byref(grad_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ auon_brake falló ({ret}): {err.message()}")
        return loss_out.value, grad_out.value

    def riemannian_geodesic(self, u: np.ndarray, v: np.ndarray) -> Tuple[float, float]:
        u_arr = np.ascontiguousarray(u, dtype=np.float64)
        v_arr = np.ascontiguousarray(v, dtype=np.float64)
        dim = len(u_arr)
        ang_out = ctypes.c_double(0.0)
        chord_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_riemannian_geodesic_v903(
            u_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            v_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_uint(dim), ctypes.byref(ang_out), ctypes.byref(chord_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ riemannian_geodesic falló ({ret}): {err.message()}")
        return ang_out.value, chord_out.value

    def secant_distortion_eval(self, orig_points: np.ndarray, proj_points: np.ndarray) -> Dict[str, float]:
        orig_arr = np.ascontiguousarray(orig_points, dtype=np.float64)
        proj_arr = np.ascontiguousarray(proj_points, dtype=np.float64)
        n, din = orig_arr.shape
        _, dout = proj_arr.shape
        l_min_out = ctypes.c_double(0.0)
        l_max_out = ctypes.c_double(0.0)
        delta_max_out = ctypes.c_double(0.0)
        secant_alpha_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_secant_distortion_eval_v903(
            ctypes.c_uint(n), ctypes.c_uint(din), ctypes.c_uint(dout),
            orig_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            proj_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(l_min_out), ctypes.byref(l_max_out), ctypes.byref(delta_max_out), ctypes.byref(secant_alpha_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ secant_distortion_eval falló ({ret}): {err.message()}")
        return {"l_min": l_min_out.value, "l_max": l_max_out.value, "delta_max": delta_max_out.value, "secant_alpha": secant_alpha_out.value}

    def two_nn_intrinsic_dim(self, points: np.ndarray) -> Dict[str, float]:
        pts_arr = np.ascontiguousarray(points, dtype=np.float64)
        n, dim = pts_arr.shape
        d_mle_out = ctypes.c_double(0.0)
        d_ucb_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_two_nn_intrinsic_dim_v903(
            ctypes.c_uint(n), ctypes.c_uint(dim),
            pts_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(d_mle_out), ctypes.byref(d_ucb_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ two_nn_intrinsic_dim falló ({ret}): {err.message()}")
        return {"d_intrinsic_mle": d_mle_out.value, "d_intrinsic_ucb": d_ucb_out.value}

    def stiefel_smw_retraction(self, x_mat: np.ndarray, g_mat: np.ndarray, tau: float = 0.1) -> Tuple[np.ndarray, float]:
        x_arr = np.ascontiguousarray(x_mat, dtype=np.float64)
        g_arr = np.ascontiguousarray(g_mat, dtype=np.float64)
        d, k = x_arr.shape
        y_out = np.zeros((d, k), dtype=np.float64)
        ortho_err_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()

        ret = self.lib.polydim_cpp_stiefel_cayley_smw_retraction_v903(
            ctypes.c_uint(d), ctypes.c_uint(k), ctypes.c_double(tau),
            x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            g_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            y_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(ortho_err_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ stiefel_smw_retraction falló ({ret}): {err.message()}")
        return y_out, ortho_err_out.value

    def cliffordnet_interact(self, vectors: np.ndarray) -> Tuple[np.ndarray, float]:
        vecs_arr = np.ascontiguousarray(vectors, dtype=np.float64)
        n, k = vecs_arr.shape
        bivec_dim = (k * (k - 1)) // 2
        bivecs_out = np.zeros((n, bivec_dim), dtype=np.float64)
        energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_cliffordnet_bivector_interact_v903(
            ctypes.c_uint(n), ctypes.c_uint(k),
            vecs_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivecs_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(energy_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ cliffordnet_interact falló ({ret}): {err.message()}")
        return bivecs_out, energy_out.value

    def fire_metric(self, q_matrix: np.ndarray, threshold: float = 1e-6) -> Tuple[float, bool]:
        q_arr = np.ascontiguousarray(q_matrix, dtype=np.float64)
        d, k = q_arr.shape
        drift_out = ctypes.c_double(0.0)
        reinit_out = ctypes.c_uint8(0)
        err = PolydimErrorV903()
        ret = self.lib.polydim_cpp_fire_metric_v903(
            ctypes.c_uint(d), ctypes.c_uint(k),
            q_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_double(threshold),
            ctypes.byref(drift_out), ctypes.byref(reinit_out), ctypes.byref(err),
        )
        if ret != 0:
            raise RuntimeError(f"C++ fire_metric falló ({ret}): {err.message()}")
        return drift_out.value, bool(reinit_out.value)
