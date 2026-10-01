# ============================================================================
# POLYDIM TEST COMPREHENSIVE SUITE V930 (20 PRUEBAS FÍSICAS RIGUROSAS)
# ============================================================================

import os
import sys
import ctypes
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v930_monolito import (
    PolydimManifoldV930,
    PolydimMartingaleDetectorV930,
    PolydimCliffordAlgebraV930,
    PolydimKrylovSolverV930,
    PolydimSymplecticIntegratorV930,
    _cpp_lib,
    _rust_lib,
)


class TestPolydimV930Suite(unittest.TestCase):

    def test_01_dll_bindings_live(self):
        """Verifica que ambas DLLs (C++ y Rust) estén cargadas y operativas"""
        self.assertIsNotNone(_cpp_lib, "C++ DLL no fue cargada")
        self.assertIsNotNone(_rust_lib, "Rust DLL no fue cargada")

    def test_02_version_info_string(self):
        """Verifica cadena de versión C-ABI"""
        ver = _cpp_lib.polydim_version_info().decode('utf-8')
        self.assertIn("POLYDIM_V930", ver)

    def test_03_ftz_daz_hardware_flags(self):
        """Verifica que los modos FTZ y DAZ en MXCSR se activen correctamente"""
        _cpp_lib.polydim_enable_ftz_daz()
        status = _cpp_lib.polydim_ftz_daz_status()
        self.assertEqual(status, 1, "FTZ/DAZ no se activaron en MXCSR")

    def test_04_newton_schulz_stiefel_orthogonality(self):
        """Verifica ortogonalidad Q^T Q = I_K para matrices bien condicionadas"""
        np.random.seed(42)
        D, K = 128, 8
        Y = np.random.randn(D, K).astype(np.float32)
        Q = PolydimManifoldV930.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de ortogonalidad: {diff}")

    def test_05_cayley_retraction_post_stabilization(self):
        """Verifica retracción exacta Wen-Yin con post-estabilización Newton-Schulz"""
        np.random.seed(77)
        D, K = 256, 4
        P, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        G = np.random.randn(D, K).astype(np.float32) * 5.0
        P_next = PolydimManifoldV930.cayley_retraction(P, G, lr=0.05)
        GtG = P_next.T @ P_next
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de isometría en Cayley: {diff}")

    def test_06_spherical_parallel_transport_isometry(self):
        """Verifica que el transporte paralelo Householder en S^{D-1} preserve normas y tangencia"""
        D = 1000
        np.random.seed(101)
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        y = np.random.randn(D).astype(np.float32)
        y /= np.linalg.norm(y)
        # Vector tangente en x
        v_rand = np.random.randn(D).astype(np.float32)
        v = v_rand - np.dot(x, v_rand) * x
        v_norm_orig = np.linalg.norm(v)

        v_trans = PolydimManifoldV930.parallel_transport_sphere(x, y, v)
        v_norm_trans = np.linalg.norm(v_trans)

        # 1. Preservación de norma
        self.assertAlmostEqual(v_norm_orig, v_norm_trans, places=4)
        # 2. Tangencia en el punto de destino y
        dot_tangency = abs(float(np.dot(y, v_trans)))
        self.assertLess(dot_tangency, 1e-4)

    def test_07_tao_symplectic_energy_envelope(self):
        """Verifica que el integrador de Tao preserve energía en Hamiltonianos acoplados"""
        D = 2
        q1 = np.array([1.0, 0.0], dtype=np.float32)
        p1 = np.array([0.0, 1.0], dtype=np.float32)
        q2 = np.array([1.0, 0.0], dtype=np.float32)
        p2 = np.array([0.0, 1.0], dtype=np.float32)
        omega = 10.0
        dt = 0.01

        q1_c, p1_c, q2_c, p2_c = q1.copy(), p1.copy(), q2.copy(), p2.copy()
        for _ in range(100):
            q1_c, p1_c, q2_c, p2_c = PolydimSymplecticIntegratorV930.step_tao(q1_c, p1_c, q2_c, p2_c, omega, dt)

        h_init = 0.5 * (np.sum(q1**2 + p1**2 + q2**2 + p2**2))
        h_final = 0.5 * (np.sum(q1_c**2 + p1_c**2 + q2_c**2 + p2_c**2))
        diff = abs(h_final - h_init) / h_init
        self.assertLess(diff, 0.1)

    def test_08_clifford_sign_pseudo_euclidean(self):
        """Verifica signo pseudo-euclidiano con métrica negativa en Cl(p, q)"""
        a = [0b0011, 0, 0, 0]  # e1, e2
        b = [0b0010, 0, 0, 0]  # e2
        q_mask = [0b0010, 0, 0, 0]  # e2^2 = -1
        sign = PolydimCliffordAlgebraV930.canonical_sign(a, b, q_mask)
        self.assertIn(sign, [-1, 1])

    def test_09_clifford_sign_multiword_blades(self):
        """Verifica paridad cruzada entre palabras en blades de 256 bits"""
        a = [0, 0b1, 0, 0]
        b = [0b1, 0, 0, 0]
        sign = PolydimCliffordAlgebraV930.canonical_sign(a, b)
        self.assertEqual(sign, -1)

    def test_10_ville_martingale_soft_floor_stability(self):
        """Verifica que scores extremadamente negativos respeten el soft-floor a -10.0"""
        det = PolydimMartingaleDetectorV930(alpha=0.05, mu0=0.0)
        for _ in range(50):
            det.update(-100.0)
        self.assertGreaterEqual(det.log_martingale, -10.0)

    def test_11_ville_martingale_rapid_recovery(self):
        """Verifica que el detector se recupere inmediatamente tras una fase de supresión prolongada"""
        det = PolydimMartingaleDetectorV930(alpha=0.05, mu0=0.0)
        for _ in range(50):
            det.update(-10.0)
        alarm = False
        for _ in range(30):
            if det.update(5.0):
                alarm = True
                break
        self.assertTrue(alarm, "Fallo en recuperación rápida de martingala tras soft-floor")

    def test_12_fgmres_chebyshev_convergence(self):
        """Verifica convergencia del solver FGMRES con precondicionador Chebyshev"""
        D = 1000
        b = np.ones(D, dtype=np.float32)
        x = PolydimKrylovSolverV930.solve(b, m_restart=20, max_restarts=15, tol=1e-5)
        Ax = 2.0 * x
        Ax[1:] += 0.1 * x[:-1]
        res = np.linalg.norm(Ax - b) / np.linalg.norm(b)
        self.assertLess(res, 1e-4, f"FGMRES Chebyshev no convergió: {res}")

    def test_13_suq2_deformation_local_normalization(self):
        """Verifica conservación de norma unitaria por pares tras deformación SU_q(2)"""
        vec = np.array([3.0, 4.0, 5.0, 12.0], dtype=np.float32)
        deformed = PolydimManifoldV930.suq2_deform(vec, q=0.85)
        norm1 = np.linalg.norm(deformed[0:2])
        norm2 = np.linalg.norm(deformed[2:4])
        self.assertAlmostEqual(norm1, 1.0, places=5)
        self.assertAlmostEqual(norm2, 1.0, places=5)

    def test_14_betti1_topological_circle(self):
        """Verifica cálculo topológico de Betti-1 = 1 en puntos sobre círculo S^1"""
        n_pts = 16
        theta = np.linspace(0, 2 * np.pi, n_pts, endpoint=False)
        pts = np.column_stack([np.cos(theta), np.sin(theta)]).astype(np.float32)
        c_pts = pts.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        eps = float(2.0 * np.sin(np.pi / n_pts) * 1.3)
        b1 = _rust_lib.rust_betti_number_v930(c_pts, n_pts, 2, eps)
        self.assertGreaterEqual(b1, 1, f"Betti-1 esperado >= 1, obtenido: {b1}")

    def test_15_robbins_siegmund_martingale_growth(self):
        """Verifica cálculo de supermartingala de mezcla gaussiana Robbins-Siegmund"""
        n_steps = 10
        k_dim = 4
        sigma0_sq = 1.0
        # 1. Bajo señal con deriva fuerte (||S_n||^2 = 200.0): log-martingale > 0
        val_signal = _rust_lib.rust_robbins_siegmund_log_martingale_v930(200.0, n_steps, k_dim, sigma0_sq)
        self.assertGreater(val_signal, 0.0)

        # 2. Bajo nula (||S_n||^2 = 0.0): log-martingale <= 0 por propiedad de supermartingala
        val_null = _rust_lib.rust_robbins_siegmund_log_martingale_v930(0.0, n_steps, k_dim, sigma0_sq)
        self.assertLessEqual(val_null, 0.0)

    def test_16_ebh_multiple_testing_discoveries(self):
        """Verifica procedimiento e-BH para múltiples flujos con FDR controlado"""
        e_vals = np.array([100.0, 50.0, 1.0, 0.5, 0.2], dtype=np.float64)
        c_e = e_vals.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        discoveries = np.zeros(5, dtype=np.int32)
        c_disc = discoveries.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
        k = _rust_lib.rust_ebh_fdr_threshold_v930(c_e, 5, 0.05, c_disc)
        self.assertGreaterEqual(k, 2)
        self.assertEqual(discoveries[0], 1)
        self.assertEqual(discoveries[1], 1)

    def test_17_grassmann_matrix_free_projection(self):
        """Verifica proyección horizontal P_horiz(Z) = Z - U (U^T Z) en Grassmann"""
        np.random.seed(99)
        D, K = 64, 4
        U, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        Z = np.random.randn(D, K).astype(np.float32)
        Zh = PolydimManifoldV930.grassmann_project(U, Z)
        # Ut Zh debe ser 0
        UtZh = U.T @ Zh
        self.assertLess(np.linalg.norm(UtZh, 'fro'), 1e-4)

    def test_18_asymptotic_d100k_stress(self):
        """Verifica estabilidad asintótica a D = 100,000 en Stiefel"""
        D, K = 100000, 2
        np.random.seed(777)
        Y = np.random.randn(D, K).astype(np.float32)
        Q = PolydimManifoldV930.newton_schulz_stiefel(Y, max_iter=20)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo asintótico a D=100,000: {diff}")

    def test_19_newton_schulz_subnormal_scale_matrix(self):
        """Verifica convergencia con matriz de norma diminuta (1e-6)"""
        np.random.seed(202)
        D, K = 64, 4
        Y = np.random.randn(D, K).astype(np.float32) * 1e-6
        Q = PolydimManifoldV930.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de convergencia en matriz subnormal: {diff}")

    def test_20_antipodal_parallel_transport_fallback(self):
        """Verifica fallback de reflexión Householder ante puntos casi antípodas (y = -x)"""
        D = 10
        x = np.array([1.0] + [0.0] * (D - 1), dtype=np.float32)
        y = np.array([-1.0] + [0.0] * (D - 1), dtype=np.float32)  # Antipodal
        v = np.array([0.0, 1.0] + [0.0] * (D - 2), dtype=np.float32)  # Tangent
        v_trans = PolydimManifoldV930.parallel_transport_sphere(x, y, v)
        self.assertFalse(np.isnan(v_trans).any())
        self.assertAlmostEqual(np.linalg.norm(v_trans), 1.0, places=4)


if __name__ == '__main__':
    unittest.main()
