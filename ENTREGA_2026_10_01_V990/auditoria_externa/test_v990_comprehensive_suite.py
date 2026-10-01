# ============================================================================
# POLYDIM UNIT TEST COMPREHENSIVE SUITE V990 (HITO 80 QUINCUAGESIMAL)
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v990_monolito import PolydimV990Engine

class TestPolydimV990Suite(unittest.TestCase):

    def test_01_spherical_vlasov_poisson_sphere_constraint(self):
        N, D = 10, 32
        pos = np.random.randn(N, D).astype(np.float32)
        pos /= np.linalg.norm(pos, axis=1, keepdims=True)
        mom = np.random.randn(N, D).astype(np.float32)
        # Tangency for momentum: <pos, mom> = 0
        mom -= np.sum(pos * mom, axis=1, keepdims=True) * pos
        grad_phi = np.random.randn(N, D).astype(np.float32)

        out_pos, out_mom = PolydimV990Engine.spherical_vlasov_poisson_step(pos, mom, grad_phi, dt=0.01)

        # 1. Norm of position is 1
        pos_norms = np.linalg.norm(out_pos, axis=1)
        for val in pos_norms:
            self.assertAlmostEqual(val, 1.0, places=4)

        # 2. Tangency <out_pos, out_mom> = 0
        dot_xp = np.sum(out_pos * out_mom, axis=1)
        for val in dot_xp:
            self.assertAlmostEqual(val, 0.0, places=4)

    def test_02_calogero_sutherland_integrals(self):
        N = 8
        positions = np.sort(np.linspace(0.1, 3.0, N)).astype(np.float32)
        momenta = np.random.randn(N).astype(np.float32)
        integrals = PolydimV990Engine.calogero_sutherland_integrals(positions, momenta, g_coupling=0.5)
        self.assertEqual(integrals.shape, (2,))
        self.assertAlmostEqual(integrals[0], float(np.sum(momenta)), places=4)
        self.assertFalse(np.isnan(integrals).any())

    def test_03_stiefel_cayley_wen_yin_orthogonality(self):
        D, K = 32, 4
        X_raw = np.random.randn(D, K).astype(np.float32)
        X, _ = np.linalg.qr(X_raw)
        G = np.random.randn(D, K).astype(np.float32)

        out_X = PolydimV990Engine.wen_yin_stiefel_retraction(X, G, tau=0.05)
        self.assertEqual(out_X.shape, (D, K))

        # Check column normality
        for c in range(K):
            norm = np.linalg.norm(out_X[:, c])
            self.assertAlmostEqual(norm, 1.0, places=3)

    def test_04_nambu_integrator_preserves_sphere(self):
        D = 16
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        grad_V = np.random.randn(D).astype(np.float32)
        out_x = PolydimV990Engine.nambu_step(x, grad_V, dt=0.05)
        norm = np.linalg.norm(out_x)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_05_e8_quantization_even_sum(self):
        D = 64
        vec = np.random.randn(D).astype(np.float32) * 5.0
        q = PolydimV990Engine.e8_quantize(vec)
        self.assertEqual(q.shape, (D,))
        for b in range(D // 8):
            blk = q[b*8:(b+1)*8]
            self.assertEqual(int(np.sum(blk)) % 2, 0)

    def test_06_marsden_weinstein_reduction(self):
        D, K = 32, 4
        Q_raw = np.random.randn(D, K).astype(np.float32)
        Q, _ = np.linalg.qr(Q_raw)
        P = np.random.randn(D, K).astype(np.float32)

        red_Q, red_P = PolydimV990Engine.marsden_weinstein_reduce(Q, P)
        self.assertEqual(red_Q.shape, (D, K))
        self.assertEqual(red_P.shape, (D, K))

        J_red = red_Q.T @ red_P - red_P.T @ red_Q
        norm_J = np.linalg.norm(J_red)
        self.assertLess(norm_J, 1e-4)

    def test_07_householder_parallel_transport(self):
        D = 32
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        y = np.random.randn(D).astype(np.float32)
        y /= np.linalg.norm(y)
        # Vector v tangent to x: <x, v> = 0
        v = np.random.randn(D).astype(np.float32)
        v -= np.dot(x, v) * x
        norm_v = np.linalg.norm(v)

        out_v = PolydimV990Engine.parallel_transport_householder(x, y, v)

        # 1. Transported vector is tangent to y: <y, out_v> = 0
        dot_yv = np.dot(y, out_v)
        self.assertAlmostEqual(dot_yv, 0.0, places=4)

        # 2. Isometry: norm(out_v) == norm(v)
        self.assertAlmostEqual(np.linalg.norm(out_v), norm_v, places=4)

    def test_08_clifford_rotor_spin(self):
        D = 16
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        u = np.zeros(D, dtype=np.float32); u[0] = 1.0
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0
        out_x = PolydimV990Engine.clifford_rotor_spin(x, u, v, theta=0.5)
        self.assertAlmostEqual(np.linalg.norm(out_x), 1.0, places=4)

    def test_09_robbins_siegmund_conformal(self):
        T = 50
        losses = np.random.exponential(scale=0.1, size=T).astype(np.float32)
        v = PolydimV990Engine.robbins_siegmund(losses, alpha=0.1)
        self.assertEqual(len(v), T)
        self.assertTrue((v >= 0.0).all())

if __name__ == "__main__":
    unittest.main()
