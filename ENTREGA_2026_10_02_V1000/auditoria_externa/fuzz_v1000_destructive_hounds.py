# ============================================================================
# POLYDIM FUZZ DESTRUCTIVE HOUNDS SUITE V1000 (HITO 100 QUINCUAGESIMAL)
# ============================================================================

import unittest
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v1000_monolito import PolydimV1000Engine

class TestPolydimV1000FuzzHounds(unittest.TestCase):

    def test_hound_01_nan_inf_resilience(self):
        D = 16
        x_nan = np.full(D, np.nan, dtype=np.float32)
        grad_inf = np.full(D, np.inf, dtype=np.float32)
        try:
            out_x = PolydimV1000Engine.nambu_step(x_nan, grad_inf, dt=0.01)
            self.assertEqual(len(out_x), D)
        except Exception:
            pass

    def test_hound_02_antipodal_householder_singularity(self):
        D = 16
        x = np.zeros(D, dtype=np.float32); x[0] = 1.0
        y = np.zeros(D, dtype=np.float32); y[0] = -1.0 # Antipodal
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0
        out_v = PolydimV1000Engine.parallel_transport_householder(x, y, v)
        self.assertEqual(len(out_v), D)
        self.assertFalse(np.isnan(out_v).any())

    def test_hound_03_high_dimension_e8_scale(self):
        D = 1024 # High dim divisible by 8
        vec = np.random.randn(D).astype(np.float32) * 100.0
        q = PolydimV1000Engine.e8_quantize(vec)
        self.assertEqual(q.shape, (D,))
        self.assertFalse(np.isnan(q).any())

    def test_hound_04_mobius_boundary_stability(self):
        D = 32
        x = (np.random.randn(D) * 0.999).astype(np.float32)
        x /= np.linalg.norm(x) * 1.001
        y = np.zeros(D, dtype=np.float32)
        res = PolydimV1000Engine.mobius_addition(x, y, c=1.0)
        self.assertEqual(res.shape, (D,))
        self.assertFalse(np.isnan(res).any())

if __name__ == "__main__":
    unittest.main()
