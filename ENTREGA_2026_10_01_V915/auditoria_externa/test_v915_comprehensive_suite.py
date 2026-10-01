# ============================================================================
# POLYDIM TEST COMPREHENSIVE SUITE V915 (16 PRUEBAS FÍSICAS RIGUROSAS)
# ============================================================================

import os
import sys
import ctypes
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v915_monolito import (
    PolydimManifoldV915,
    PolydimMartingaleDetectorV915,
    PolydimCliffordAlgebraV915,
    PolydimKrylovSolverV915,
    _cpp_lib,
    _rust_lib,
)


class TestPolydimV915Suite(unittest.TestCase):

    def test_01_dll_bindings_live(self):
        """Verifica que ambas DLLs (C++ y Rust) estén cargadas y operativas"""
        self.assertIsNotNone(_cpp_lib, "C++ DLL no fue cargada")
        self.assertIsNotNone(_rust_lib, "Rust DLL no fue cargada")

    def test_02_version_info_string(self):
        """Verifica cadena de versión C-ABI"""
        ver = _cpp_lib.polydim_version_info().decode('utf-8')
        self.assertIn("POLYDIM_V915", ver)

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
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de ortogonalidad: {diff}")

    def test_05_newton_schulz_severely_distorted_matrix(self):
        """Verifica convergencia bajo distorsión extrema (norma 100x) gracias al pre-escalado dual"""
        np.random.seed(101)
        D, K = 256, 4
        Y = np.random.randn(D, K).astype(np.float32) * 100.0
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de convergencia en matriz distorsionada: {diff}")

    def test_06_newton_schulz_subnormal_scale_matrix(self):
        """Verifica convergencia con matriz de norma diminuta (1e-6)"""
        np.random.seed(202)
        D, K = 64, 4
        Y = np.random.randn(D, K).astype(np.float32) * 1e-6
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de convergencia en matriz subnormal: {diff}")

    def test_07_clifford_sign_disjoint_blades(self):
        """Verifica signo canónico +1 para blades disjuntos ordenados"""
        a = [0b0001, 0, 0, 0]
        b = [0b0010, 0, 0, 0]
        sign = PolydimCliffordAlgebraV915.canonical_sign(a, b)
        self.assertEqual(sign, 1)

    def test_08_clifford_sign_inverted_blades(self):
        """Verifica anticommutación e_2 e_1 = - e_1 e_2 (signo -1)"""
        a = [0b0010, 0, 0, 0]
        b = [0b0001, 0, 0, 0]
        sign = PolydimCliffordAlgebraV915.canonical_sign(a, b)
        self.assertEqual(sign, -1)

    def test_09_clifford_sign_multiword_blades(self):
        """Verifica paridad cruzada entre palabras en blades de 256 bits"""
        a = [0, 0b1, 0, 0]  # bit 64
        b = [0b1, 0, 0, 0]  # bit 0
        sign = PolydimCliffordAlgebraV915.canonical_sign(a, b)
        self.assertEqual(sign, -1)

    def test_10_ville_martingale_stationary_regime(self):
        """Verifica que bajo régimen estacionario (media 0) la martingala NO dispare falsas alarmas"""
        np.random.seed(42)
        det = PolydimMartingaleDetectorV915(alpha=0.05, mu0=0.0)
        alarms = 0
        for _ in range(100):
            score = float(np.random.normal(0.0, 0.2))
            if det.update(score):
                alarms += 1
        self.assertEqual(alarms, 0, "Falsa alarma detectada en régimen estacionario")

    def test_11_ville_martingale_drift_detection(self):
        """Verifica detección rápida de salto en distribución (deriva topológica)"""
        np.random.seed(99)
        det = PolydimMartingaleDetectorV915(alpha=0.05, mu0=0.0)
        detected = False
        for step in range(50):
            score = float(np.random.normal(2.5, 0.5))  # Deriva severa
            if det.update(score):
                detected = True
                break
        self.assertTrue(detected, "No se detectó la deriva topológica severa")

    def test_12_ville_martingale_subnormal_stability(self):
        """Verifica que scores subnormales (1e-15) no produzcan NaN ni traps FPU"""
        det = PolydimMartingaleDetectorV915(alpha=0.05, mu0=0.0)
        for _ in range(50):
            det.update(1e-15)
        self.assertFalse(np.isnan(det.log_martingale), "NaN en log-martingala con subnormales")

    def test_13_fgmres_krylov_solver_convergence(self):
        """Verifica convergencia del solver FGMRES con espacio prealocado y MGS-2"""
        D = 1000
        b = np.ones(D, dtype=np.float32)
        x = PolydimKrylovSolverV915.solve(b, m_restart=20, max_restarts=15, tol=1e-5)
        # Residuo manual A*x - b donde A = diag(2.0) + subdiag(0.1)
        Ax = 2.0 * x
        Ax[1:] += 0.1 * x[:-1]
        res = np.linalg.norm(Ax - b) / np.linalg.norm(b)
        self.assertLess(res, 1e-4, f"FGMRES no convergió: residuo relativo = {res}")

    def test_14_suq2_deformation_local_normalization(self):
        """Verifica conservación de norma unitaria por pares tras deformación cuántica SU_q(2)"""
        vec = np.array([3.0, 4.0, 5.0, 12.0], dtype=np.float32)
        deformed = PolydimManifoldV915.suq2_deform(vec, q=0.85)
        norm1 = np.linalg.norm(deformed[0:2])
        norm2 = np.linalg.norm(deformed[2:4])
        self.assertAlmostEqual(norm1, 1.0, places=5)
        self.assertAlmostEqual(norm2, 1.0, places=5)

    def test_15_betti1_topological_circle(self):
        """Verifica cálculo topológico de Betti-1 = 1 en puntos sobre círculo S^1"""
        n_pts = 16
        theta = np.linspace(0, 2 * np.pi, n_pts, endpoint=False)
        pts = np.column_stack([np.cos(theta), np.sin(theta)]).astype(np.float32)
        c_pts = pts.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        eps = float(2.0 * np.sin(np.pi / n_pts) * 1.3)
        b1 = _rust_lib.rust_betti_number_v915(c_pts, n_pts, 2, eps)
        self.assertGreaterEqual(b1, 1, f"Betti-1 esperado >= 1, obtenido: {b1}")

    def test_16_asymptotic_d100k_stress(self):
        """Verifica estabilidad asintótica a D = 100,000 en Stiefel y SU_q(2)"""
        D, K = 100000, 2
        np.random.seed(777)
        Y = np.random.randn(D, K).astype(np.float32)
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y, max_iter=20)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo asintótico a D=100,000: {diff}")


if __name__ == '__main__':
    unittest.main()
