# ============================================================================
# POLYDIM UNIT TEST COMPREHENSIVE SUITE V991
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v991_monolito import PolydimV991Engine

class TestPolydimV991Suite(unittest.TestCase):

    def test_01_spherical_vlasov_poisson_sphere_constraint(self):
        N, D = 10, 32
        pos = np.random.randn(N, D).astype(np.float32)
        pos /= np.linalg.norm(pos, axis=1, keepdims=True)
        mom = np.random.randn(N, D).astype(np.float32)
        mom -= np.sum(pos * mom, axis=1, keepdims=True) * pos
        grad_phi = np.random.randn(N, D).astype(np.float32)

        out_pos, out_mom = PolydimV991Engine.spherical_vlasov_poisson_step(pos, mom, grad_phi, dt=0.01)

        pos_norms = np.linalg.norm(out_pos, axis=1)
        for val in pos_norms:
            self.assertAlmostEqual(val, 1.0, places=4)

        dot_xp = np.sum(out_pos * out_mom, axis=1)
        for val in dot_xp:
            self.assertAlmostEqual(val, 0.0, places=4)

    def test_02_calogero_sutherland_integrals(self):
        N = 8
        positions = np.sort(np.linspace(0.1, 3.0, N)).astype(np.float32)
        momenta = np.random.randn(N).astype(np.float32)
        integrals = PolydimV991Engine.calogero_sutherland_integrals(positions, momenta, g_coupling=0.5)
        self.assertEqual(integrals.shape, (2,))
        self.assertAlmostEqual(integrals[0], float(np.sum(momenta)), places=4)
        self.assertFalse(np.isnan(integrals).any())

    def test_03_cayley_smw_stiefel_orthogonality(self):
        D, K = 64, 4
        X = np.random.randn(D).astype(np.float32)
        X /= np.linalg.norm(X)
        U = np.random.randn(D, K).astype(np.float32)
        V = np.random.randn(D, K).astype(np.float32)

        out_X = PolydimV991Engine.cayley_smw_stiefel(X, U, V)
        self.assertEqual(out_X.shape, (D,))
        norm = np.linalg.norm(out_X)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_04_householder_parallel_transport_antipodal(self):
        D = 32
        x = np.random.randn(D).astype(np.float32); x /= np.linalg.norm(x)
        y = -x
        v = np.random.randn(D).astype(np.float32); v -= np.dot(x, v) * x
        norm_v = np.linalg.norm(v)

        out_v = PolydimV991Engine.parallel_transport_householder(x, y, v)
        self.assertFalse(np.isnan(out_v).any())
        self.assertAlmostEqual(np.linalg.norm(out_v), norm_v, places=4)

    def test_05_mobius_addition_hyperbolic(self):
        D = 32
        x = (np.random.randn(D) * 0.1).astype(np.float32)
        y = (np.random.randn(D) * 0.1).astype(np.float32)
        res = PolydimV991Engine.mobius_addition(x, y, c=1.0)
        self.assertEqual(res.shape, (D,))
        self.assertFalse(np.isnan(res).any())

    def test_06_robbins_siegmund_conformal(self):
        T = 50
        losses = np.random.exponential(scale=0.1, size=T).astype(np.float32)
        v = PolydimV991Engine.robbins_siegmund(losses, alpha=0.1)
        self.assertEqual(len(v), T)
        self.assertTrue((v >= 0.0).all())

    def test_07_clifford_rotor_spin(self):
        D = 16
        x = np.random.randn(D).astype(np.float32); x /= np.linalg.norm(x)
        u = np.zeros(D, dtype=np.float32); u[0] = 1.0
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0
        out_x = PolydimV991Engine.clifford_rotor_spin(x, u, v, theta=0.5)
        self.assertAlmostEqual(np.linalg.norm(out_x), 1.0, places=4)

    def test_08_betti1_rips(self):
        points = np.array([[0,0],[1,0],[1,1],[0,1]], dtype=np.float32)
        b1 = PolydimV991Engine.betti1_rips(points, eps=1.1)
        self.assertEqual(b1, 1)

if __name__ == "__main__":
    unittest.main()
