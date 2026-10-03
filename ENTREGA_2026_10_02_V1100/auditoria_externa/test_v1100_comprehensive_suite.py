# ============================================================================
# SUITE COMPLETA DE PRUEBAS UNITARIAS Y GEOMÉTRICAS V1100
# ============================================================================

import os
import sys
import unittest
import numpy as np

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _DIR)

from polydim_v1100_monolito import PolydimV1100Engine

class TestPolydimV1100Suite(unittest.TestCase):

    def test_01_e8_lattice_quantize(self):
        np.random.seed(1100)
        vec = np.random.randn(16).astype(np.float32)
        q = PolydimV1100Engine.e8_lattice_quantize(vec)
        self.assertEqual(q.shape[0], 16)
        # Verificar que la suma en bloques de 8 sea entera par o semientera par
        for b in range(2):
            block = q[b*8:(b+1)*8]
            is_half = np.allclose(block % 1.0, 0.5)
            is_int = np.allclose(block % 1.0, 0.0)
            self.assertTrue(is_half or is_int, "E8 coordinates must be either all integer or all half-integer")
            if is_int:
                self.assertEqual(int(np.sum(block)) % 2, 0, "D8 lattice sum must be even")

    def test_02_calogero_sutherland_integrals(self):
        N = 4
        pos = np.array([0.1, 0.5, 1.2, 2.0], dtype=np.float32)
        mom = np.array([1.0, -0.5, 0.8, -1.3], dtype=np.float32)
        integrals = PolydimV1100Engine.calogero_sutherland_integrals(pos, mom, g_coupling=1.0)
        self.assertAlmostEqual(integrals[0], float(np.sum(mom)), places=4)
        self.assertGreater(integrals[1], 0.0, "I2 second invariant must be strictly positive")

    def test_03_parallel_transport_householder(self):
        D = 32
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        y = np.random.randn(D).astype(np.float32)
        y /= np.linalg.norm(y)
        v = np.random.randn(D).astype(np.float32)
        v -= np.dot(x, v) * x  # v in Tx S^{D-1}
        
        v_trans = PolydimV1100Engine.parallel_transport_householder(x, y, v)
        # Verificar ortogonalidad con y
        self.assertAlmostEqual(float(np.dot(y, v_trans)), 0.0, places=5)
        # Preservación de norma
        self.assertAlmostEqual(float(np.linalg.norm(v_trans)), float(np.linalg.norm(v)), places=5)

    def test_04_betti1_rips(self):
        # 4 puntos formando un ciclo simple (cuadrado)
        pts = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0]
        ], dtype=np.float32)
        b1 = PolydimV1100Engine.betti1_rips(pts, eps=1.1)
        self.assertEqual(b1, 1, "Square with side 1.0 at eps=1.1 should have Betti-1 == 1")

    def test_05_clifford_rotor_spin(self):
        D = 16
        x = np.random.randn(D).astype(np.float32)
        x /= np.linalg.norm(x)
        u = np.zeros(D, dtype=np.float32); u[0] = 1.0
        v = np.zeros(D, dtype=np.float32); v[1] = 1.0
        x_rot = PolydimV1100Engine.clifford_rotor_spin(x, u, v, theta=float(np.pi / 2.0))
        self.assertAlmostEqual(float(np.linalg.norm(x_rot)), 1.0, places=5)

if __name__ == "__main__":
    unittest.main()
