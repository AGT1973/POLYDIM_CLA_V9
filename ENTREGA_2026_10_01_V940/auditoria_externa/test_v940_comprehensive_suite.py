# ============================================================================
# POLYDIM UNIT TEST COMPREHENSIVE SUITE V940
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v940_monolito import PolydimV940Engine

class TestPolydimV940Suite(unittest.TestCase):

    def test_01_riesz_feller_dirac(self):
        D = 128
        spinor = np.sin(np.linspace(0, 2*np.pi, D)).astype(np.float32)
        out = PolydimV940Engine.riesz_feller_dirac(spinor, alpha=1.5, dt=0.01)
        self.assertEqual(out.shape, (D,))
        self.assertFalse(np.isnan(out).any())
        self.assertFalse(np.isinf(out).any())

    def test_02_nambu_integrator_preserves_sphere(self):
        D = 16
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        grad_V = np.random.randn(D).astype(np.float32)
        out_x = PolydimV940Engine.nambu_step(x, grad_V, dt=0.05)
        norm = np.linalg.norm(out_x)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_03_e8_quantization_even_sum(self):
        D = 64
        vec = np.random.randn(D).astype(np.float32) * 5.0
        q = PolydimV940Engine.e8_quantize(vec)
        self.assertEqual(q.shape, (D,))
        for b in range(D // 8):
            blk = q[b*8:(b+1)*8]
            self.assertEqual(int(np.sum(blk)) % 2, 0)

    def test_04_marsden_weinstein_reduction(self):
        D, K = 32, 4
        # Orthonormal Q on Stiefel manifold
        Q_raw = np.random.randn(D, K).astype(np.float32)
        Q, _ = np.linalg.qr(Q_raw)
        P = np.random.randn(D, K).astype(np.float32)

        red_Q, red_P = PolydimV940Engine.marsden_weinstein_reduce(Q, P)
        self.assertEqual(red_Q.shape, (D, K))
        self.assertEqual(red_P.shape, (D, K))

        # Verify moment map J_red = Q^T P_red - P_red^T Q is zeroed
        J_red = red_Q.T @ red_P - red_P.T @ red_Q
        norm_J = np.linalg.norm(J_red)
        self.assertLess(norm_J, 1e-4)

    def test_05_robbins_siegmund_conformal(self):
        T = 50
        losses = np.random.exponential(scale=0.1, size=T).astype(np.float32)
        v = PolydimV940Engine.robbins_siegmund(losses, alpha=0.1)
        self.assertEqual(len(v), T)
        self.assertTrue((v >= 0.0).all())

if __name__ == "__main__":
    unittest.main()
