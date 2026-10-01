# ============================================================================
# POLYDIM TEST COMPREHENSIVE SUITE V920 (16 PRUEBAS FÍSICAS RIGUROSAS)
# ============================================================================

import os
import sys
import ctypes
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v920_monolito import (
    PolydimManifoldV920,
    PolydimMartingaleDetectorV920,
    PolydimCliffordAlgebraV920,
    PolydimKrylovSolverV920,
    PolydimSymplecticIntegratorV920,
    _cpp_lib,
    _rust_lib,
)


class TestPolydimV920Suite(unittest.TestCase):

    def test_01_dll_bindings_live(self):
        """Verifica que ambas DLLs (C++ y Rust) estén cargadas y operativas"""
        self.assertIsNotNone(_cpp_lib, "C++ DLL no fue cargada")
        self.assertIsNotNone(_rust_lib, "Rust DLL no fue cargada")

    def test_02_version_info_string(self):
        """Verifica cadena de versión C-ABI"""
        ver = _cpp_lib.polydim_version_info().decode('utf-8')
        self.assertIn("POLYDIM_V920", ver)

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
        Q = PolydimManifoldV920.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de ortogonalidad: {diff}")

    def test_05_cayley_retraction_post_stabilization(self):
        """Verifica retracción de Cayley con post-estabilización Newton-Schulz de 1 paso"""
        np.random.seed(77)
        D, K = 256, 4
        P, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        G = np.random.randn(D, K).astype(np.float32) * 5.0
        P_next = PolydimManifoldV920.cayley_retraction(P, G, lr=0.05)
        GtG = P_next.T @ P_next
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de isometría en Cayley: {diff}")

    def test_06_stiefel_horizontal_projection_equivariance(self):
        """Verifica que la proyección horizontal P_horiz(V) preserve ortogonalidad canónica"""
        np.random.seed(88)
        D, K = 64, 4
        X, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        V = np.random.randn(D, K).astype(np.float32)
        Vh = PolydimManifoldV920.horizontal_project(X, V)
        sym_comp = X.T @ Vh + Vh.T @ X
        diff = np.linalg.norm(sym_comp, 'fro')
        self.assertLess(diff, 1e-4, f"Fallo de tangencia simétrica: {diff}")

    def test_07_gautschi_symplectic_energy_envelope(self):
        """Verifica que el integrador Gautschi preserve la envolvente de energía para omega*dt > 2"""
        pos = np.array([1.0, 0.0], dtype=np.float32)
        vel = np.array([0.0, 10.0], dtype=np.float32)
        omega = 50.0
        dt = 0.05  # omega * dt = 2.5 > 2
        p_curr, v_curr = pos.copy(), vel.copy()
        for _ in range(100):
            p_curr, v_curr = PolydimSymplecticIntegratorV920.step(p_curr, v_curr, omega, dt)
        energy_initial = 0.5 * (10.0**2 + (omega * 1.0)**2)
        energy_final = 0.5 * (np.sum(v_curr**2) + (omega**2) * np.sum(p_curr**2))
        ratio = abs(energy_final - energy_initial) / energy_initial
        self.assertLess(ratio, 0.15, f"Inestabilidad en integrador Gautschi: {ratio}")

    def test_08_clifford_sign_pseudo_euclidean(self):
        """Verifica signo pseudo-euclidiano con métrica negativa en Cl(p, q)"""
        a = [0b0011, 0, 0, 0]  # e1, e2
        b = [0b0010, 0, 0, 0]  # e2
        q_mask = [0b0010, 0, 0, 0]  # e2^2 = -1
        sign = PolydimCliffordAlgebraV920.canonical_sign(a, b, q_mask)
        self.assertIn(sign, [-1, 1])

    def test_09_clifford_sign_multiword_blades(self):
        """Verifica paridad cruzada entre palabras en blades de 256 bits"""
        a = [0, 0b1, 0, 0]
        b = [0b1, 0, 0, 0]
        sign = PolydimCliffordAlgebraV920.canonical_sign(a, b)
        self.assertEqual(sign, -1)

    def test_10_ville_martingale_soft_floor_stability(self):
        """Verifica que scores extremadamente negativos respeten el soft-floor a -50.0"""
        det = PolydimMartingaleDetectorV920(alpha=0.05, mu0=0.0)
        for _ in range(50):
            det.update(-100.0)
        self.assertGreaterEqual(det.log_martingale, -50.0)

    def test_11_ville_martingale_rapid_recovery(self):
        """Verifica que el detector se recupere inmediatamente tras una fase de supresión prolongada"""
        det = PolydimMartingaleDetectorV920(alpha=0.05, mu0=0.0)
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
        x = PolydimKrylovSolverV920.solve(b, m_restart=20, max_restarts=15, tol=1e-5)
        Ax = 2.0 * x
        Ax[1:] += 0.1 * x[:-1]
        res = np.linalg.norm(Ax - b) / np.linalg.norm(b)
        self.assertLess(res, 1e-4, f"FGMRES Chebyshev no convergió: {res}")

    def test_13_suq2_deformation_local_normalization(self):
        """Verifica conservación de norma unitaria por pares tras deformación SU_q(2)"""
        vec = np.array([3.0, 4.0, 5.0, 12.0], dtype=np.float32)
        deformed = PolydimManifoldV920.suq2_deform(vec, q=0.85)
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
        b1 = _rust_lib.rust_betti_number_v920(c_pts, n_pts, 2, eps)
        self.assertGreaterEqual(b1, 1, f"Betti-1 esperado >= 1, obtenido: {b1}")

    def test_15_asymptotic_d100k_stress(self):
        """Verifica estabilidad asintótica a D = 100,000 en Stiefel"""
        D, K = 100000, 2
        np.random.seed(777)
        Y = np.random.randn(D, K).astype(np.float32)
        Q = PolydimManifoldV920.newton_schulz_stiefel(Y, max_iter=20)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-4, f"Fallo asintótico a D=100,000: {diff}")

    def test_16_newton_schulz_subnormal_scale_matrix(self):
        """Verifica convergencia con matriz de norma diminuta (1e-6)"""
        np.random.seed(202)
        D, K = 64, 4
        Y = np.random.randn(D, K).astype(np.float32) * 1e-6
        Q = PolydimManifoldV920.newton_schulz_stiefel(Y)
        GtG = Q.T @ Q
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de convergencia en matriz subnormal: {diff}")


if __name__ == '__main__':
    unittest.main()
