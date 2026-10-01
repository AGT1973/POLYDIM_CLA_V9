# ============================================================================
# POLYDIM FUZZ DESTRUCTIVE HOUNDS V930 (4 SABUESOS ADVERSARIALES RED TEAM)
# ============================================================================

import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v930_monolito import (
    PolydimManifoldV930,
    PolydimMartingaleDetectorV930,
    PolydimCliffordAlgebraV930,
    PolydimKrylovSolverV930,
    PolydimSymplecticIntegratorV930,
)


class FuzzDestructiveHoundsV930(unittest.TestCase):

    def test_hound_01_nan_inf_subnormal_attack(self):
        """Sabueso 1: Inyección de NaNs, Infs y Flotantes Denormales en SU_q(2)"""
        vec = np.array([float('nan'), float('inf'), 1e-45, 0.0], dtype=np.float32)
        out = PolydimManifoldV930.suq2_deform(vec, q=0.5)
        self.assertFalse(np.isinf(out).any())

    def test_hound_02_cayley_gradient_shock_attack(self):
        """Sabueso 2: Choque de gradiente extremo ||G|| = 1000.0 en Retracción de Cayley"""
        np.random.seed(999)
        D, K = 128, 4
        P, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        G = np.random.randn(D, K).astype(np.float32) * 1000.0
        P_next = PolydimManifoldV930.cayley_retraction(P, G, lr=0.1)
        GtG = P_next.T @ P_next
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de isometría bajo choque: {diff}")

    def test_hound_03_clifford_all_ones_inversion_parity(self):
        """Sabueso 3: Paridad en multivectores saturados (64 bits en 1)"""
        a = [0xFFFFFFFFFFFFFFFF] * 4
        b = [0xFFFFFFFFFFFFFFFF] * 4
        sign = PolydimCliffordAlgebraV930.canonical_sign(a, b)
        self.assertIn(sign, [-1, 1])

    def test_hound_04_fgmres_zero_vector_and_drift_attack(self):
        """Sabueso 4: Ataque de vector nulo y perturbación extrema en FGMRES"""
        D = 100
        b_zero = np.zeros(D, dtype=np.float32)
        x_zero = PolydimKrylovSolverV930.solve(b_zero)
        self.assertEqual(np.linalg.norm(x_zero), 0.0)


if __name__ == '__main__':
    unittest.main()
