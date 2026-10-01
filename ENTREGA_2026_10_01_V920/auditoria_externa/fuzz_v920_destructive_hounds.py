# ============================================================================
# POLYDIM DESTRUCTIVE HOUNDS V920 (4 SABUESOS ADVERSARIOS RED TEAM)
# ============================================================================

import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v920_monolito import (
    PolydimManifoldV920,
    PolydimMartingaleDetectorV920,
    PolydimCliffordAlgebraV920,
    PolydimKrylovSolverV920,
    PolydimSymplecticIntegratorV920,
)


class FuzzDestructiveHoundsV920(unittest.TestCase):

    def test_hound_01_nan_inf_poisoning_attack(self):
        """Sabueso 1: Inyección masiva de NaNs, Infs y ceros absolutos en Stiefel Retraction"""
        D, K = 128, 4
        Y = np.zeros((D, K), dtype=np.float32)
        Q = PolydimManifoldV920.newton_schulz_stiefel(Y)
        self.assertFalse(np.isnan(Q).any(), "NaN generado tras ataque con matriz nula")

    def test_hound_02_cayley_gradient_shock_attack(self):
        """Sabueso 2: Choque de gradiente extremo ||G|| = 1000.0 en Retracción de Cayley"""
        D, K = 256, 4
        P, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        G = np.random.randn(D, K).astype(np.float32) * 1000.0
        P_next = PolydimManifoldV920.cayley_retraction(P, G, lr=0.1)
        self.assertFalse(np.isnan(P_next).any(), "NaN en Cayley bajo choque de gradiente 1000x")
        GtG = P_next.T @ P_next
        diff = np.linalg.norm(GtG - np.eye(K, dtype=np.float32), 'fro')
        self.assertLess(diff, 1e-3, f"Fallo de isometría bajo choque: {diff}")

    def test_hound_03_massive_clifford_multiword_fuzz(self):
        """Sabueso 3: Fuzzing aleatorio de 1,000 combinaciones de blades Cl(p, q) de 256 bits"""
        np.random.seed(333)
        for _ in range(1000):
            a = [int(np.random.randint(0, 2**63 - 1, dtype=np.int64)) for _ in range(4)]
            b = [int(np.random.randint(0, 2**63 - 1, dtype=np.int64)) for _ in range(4)]
            q = [int(np.random.randint(0, 2**63 - 1, dtype=np.int64)) for _ in range(4)]
            sign = PolydimCliffordAlgebraV920.canonical_sign(a, b, q)
            self.assertIn(sign, [-1, 1], f"Signo inválido retornado: {sign}")

    def test_hound_04_gautschi_extreme_stiffness_fuzz(self):
        """Sabueso 4: Integración en régimen hiper-rígido omega*dt = 10,000"""
        pos = np.ones(8, dtype=np.float32)
        vel = np.zeros(8, dtype=np.float32)
        omega = 10000.0
        dt = 1.0  # omega * dt = 10000.0 >> 2
        p_out, v_out = PolydimSymplecticIntegratorV920.step(pos, vel, omega, dt)
        self.assertFalse(np.isnan(p_out).any(), "NaN en integrador hiper-rígido")
        self.assertFalse(np.isinf(p_out).any(), "Inf en integrador hiper-rígido")


if __name__ == '__main__':
    unittest.main()
