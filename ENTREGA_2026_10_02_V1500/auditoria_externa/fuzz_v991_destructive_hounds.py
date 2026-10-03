# ============================================================================
# POLYDIM DESTRUCTIVE FUZZ HOUNDS V991
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v991_monolito import PolydimV991Engine

class TestFuzzDestructiveHoundsV991(unittest.TestCase):

    def test_hound_1_nan_inf_resilience(self):
        D = 16
        pos = np.full((1, D), np.nan, dtype=np.float32)
        mom = np.full((1, D), np.inf, dtype=np.float32)
        grad_phi = np.zeros((1, D), dtype=np.float32)

        out_pos, out_mom = PolydimV991Engine.spherical_vlasov_poisson_step(pos, mom, grad_phi)
        self.assertEqual(out_pos.shape, (1, D))
        self.assertEqual(out_mom.shape, (1, D))

    def test_hound_2_antipodal_householder_singularity(self):
        D = 64
        x = np.zeros(D, dtype=np.float32); x[0] = 1.0
        y = -x
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0

        out_v = PolydimV991Engine.parallel_transport_householder(x, y, v)
        self.assertFalse(np.isnan(out_v).any())
        self.assertFalse(np.isinf(out_v).any())
        self.assertAlmostEqual(np.linalg.norm(out_v), 1.0, places=4)

    def test_hound_3_high_dimensional_stiefel_cayley_smw(self):
        D, K = 100000, 2
        X = np.random.randn(D).astype(np.float32)
        X /= np.linalg.norm(X)
        U = np.random.randn(D, K).astype(np.float32)
        V = np.random.randn(D, K).astype(np.float32)

        out_X = PolydimV991Engine.cayley_smw_stiefel(X, U, V)
        self.assertEqual(out_X.shape, (D,))
        self.assertFalse(np.isnan(out_X).any())
        self.assertAlmostEqual(np.linalg.norm(out_X), 1.0, places=3)

    def test_hound_4_mobius_addition_boundary(self):
        D = 32
        x = np.ones(D, dtype=np.float32) / np.sqrt(D) * 0.99999
        y = -x
        res = PolydimV991Engine.mobius_addition(x, y, c=1.0)
        self.assertFalse(np.isnan(res).any())

if __name__ == "__main__":
    unittest.main()
