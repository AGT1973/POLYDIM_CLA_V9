# ============================================================================
# POLYDIM DESTRUCTIVE FUZZ HOUNDS V1050 (RED TEAM AUDIT SUITE)
# Attack vectors: NaN/Inf injection, antipodal singularities, high-D limits (D >= 10^5)
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v1050_monolito import PolydimV1050Engine

class TestFuzzDestructiveHoundsV1050(unittest.TestCase):

    def test_hound_1_nan_inf_resilience(self):
        """Hound 1: Ensure kernel returns non-crashing fallback under NaN/Inf inputs."""
        D = 16
        pos = np.full((1, D), np.nan, dtype=np.float32)
        mom = np.full((1, D), np.inf, dtype=np.float32)
        grad_phi = np.zeros((1, D), dtype=np.float32)

        out_pos, out_mom = PolydimV1050Engine.spherical_vlasov_poisson_step(pos, mom, grad_phi)
        self.assertEqual(out_pos.shape, (1, D))
        self.assertEqual(out_mom.shape, (1, D))

    def test_hound_2_antipodal_householder_singularity(self):
        """Hound 2: Antipodal transport x -> -x must not divide by zero or raise NaN."""
        D = 64
        x = np.zeros(D, dtype=np.float32); x[0] = 1.0
        y = -x
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0

        out_v = PolydimV1050Engine.parallel_transport_householder(x, y, v)
        self.assertFalse(np.isnan(out_v).any())
        self.assertFalse(np.isinf(out_v).any())
        self.assertAlmostEqual(np.linalg.norm(out_v), 1.0, places=4)

    def test_hound_3_high_dimensional_stiefel_cayley_smw(self):
        """Hound 3: High-D (D = 100,000) Cayley-SMW update execution stability."""
        D, K = 100000, 2
        X = np.random.randn(D).astype(np.float32)
        X /= np.linalg.norm(X)
        U = np.random.randn(D, K).astype(np.float32)
        V = np.random.randn(D, K).astype(np.float32)

        out_X = PolydimV1050Engine.cayley_smw_stiefel(X, U, V)
        self.assertEqual(out_X.shape, (D,))
        self.assertFalse(np.isnan(out_X).any())
        self.assertAlmostEqual(np.linalg.norm(out_X), 1.0, places=3)

    def test_hound_4_mobius_addition_boundary_singularity(self):
        """Hound 4: Mobius addition near boundary ||x|| -> 1 must remain stable."""
        D = 32
        x = np.ones(D, dtype=np.float32) / np.sqrt(D) * 0.99999
        y = -x
        res = PolydimV1050Engine.mobius_addition(x, y, c=1.0)
        self.assertFalse(np.isnan(res).any())

if __name__ == "__main__":
    unittest.main()
