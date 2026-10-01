# ============================================================================
# POLYDIM DESTRUCTIVE FUZZ HOUNDS V940
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v940_monolito import PolydimV940Engine

class TestPolydimV940FuzzHounds(unittest.TestCase):

    def test_hound_01_asymptotic_riesz_feller_100k(self):
        D = 100000
        spinor = np.random.randn(D).astype(np.float32)
        out = PolydimV940Engine.riesz_feller_dirac(spinor, alpha=1.8, dt=0.001)
        self.assertEqual(out.shape, (D,))
        self.assertFalse(np.isnan(out).any())

    def test_hound_02_e8_quantizer_nan_inf_safety(self):
        D = 64
        vec = np.zeros(D, dtype=np.float32)
        vec[0] = 1e8
        vec[1] = -1e8
        q = PolydimV940Engine.e8_quantize(vec)
        self.assertEqual(q.shape, (D,))
        self.assertFalse(np.isnan(q).any())

    def test_hound_03_nambu_extreme_gradient(self):
        D = 32
        x = np.ones(D, dtype=np.float32) / np.sqrt(D)
        grad_V = np.ones(D, dtype=np.float32) * 10000.0
        out_x = PolydimV940Engine.nambu_step(x, grad_V, dt=0.0001)
        norm = np.linalg.norm(out_x)
        self.assertAlmostEqual(norm, 1.0, places=3)

    def test_hound_04_robbins_siegmund_zero_loss_floor(self):
        T = 1000
        losses = np.zeros(T, dtype=np.float32)
        v = PolydimV940Engine.robbins_siegmund(losses, alpha=0.05)
        self.assertTrue((v >= 0.0).all())
        self.assertFalse(np.isnan(v).any())

if __name__ == "__main__":
    unittest.main()
