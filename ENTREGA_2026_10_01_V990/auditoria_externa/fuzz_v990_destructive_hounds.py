# ============================================================================
# POLYDIM DESTRUCTIVE FUZZ HOUNDS V990 (HITO 80 QUINCUAGESIMAL)
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v990_monolito import PolydimV990Engine

class TestPolydimV990FuzzHounds(unittest.TestCase):

    def test_hound_01_asymptotic_vlasov_poisson_100k(self):
        N, D = 10, 10000
        pos = np.random.randn(N, D).astype(np.float32)
        pos /= np.linalg.norm(pos, axis=1, keepdims=True)
        mom = np.random.randn(N, D).astype(np.float32)
        grad_phi = np.random.randn(N, D).astype(np.float32)
        out_pos, out_mom = PolydimV990Engine.spherical_vlasov_poisson_step(pos, mom, grad_phi, dt=0.001)
        self.assertEqual(out_pos.shape, (N, D))
        self.assertFalse(np.isnan(out_pos).any())
        self.assertFalse(np.isnan(out_mom).any())

    def test_hound_02_householder_antipodal_singularity(self):
        D = 128
        x = np.zeros(D, dtype=np.float32); x[0] = 1.0
        y = np.zeros(D, dtype=np.float32); y[0] = -1.0 # Exact antipode <x,y> = -1
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0
        out_v = PolydimV990Engine.parallel_transport_householder(x, y, v)
        self.assertEqual(out_v.shape, (D,))
        self.assertFalse(np.isnan(out_v).any())
        self.assertAlmostEqual(np.linalg.norm(out_v), 1.0, places=4)

    def test_hound_03_e8_quantizer_nan_inf_safety(self):
        D = 64
        vec = np.zeros(D, dtype=np.float32)
        vec[0] = 1e8
        vec[1] = -1e8
        q = PolydimV990Engine.e8_quantize(vec)
        self.assertEqual(q.shape, (D,))
        self.assertFalse(np.isnan(q).any())

    def test_hound_04_nambu_extreme_gradient(self):
        D = 32
        x = np.ones(D, dtype=np.float32) / np.sqrt(D)
        grad_V = np.ones(D, dtype=np.float32) * 10000.0
        out_x = PolydimV990Engine.nambu_step(x, grad_V, dt=0.0001)
        norm = np.linalg.norm(out_x)
        self.assertAlmostEqual(norm, 1.0, places=3)

    def test_hound_05_robbins_siegmund_zero_loss_floor(self):
        T = 1000
        losses = np.zeros(T, dtype=np.float32)
        v = PolydimV990Engine.robbins_siegmund(losses, alpha=0.05)
        self.assertTrue((v >= 0.0).all())
        self.assertFalse(np.isnan(v).any())

if __name__ == "__main__":
    unittest.main()
