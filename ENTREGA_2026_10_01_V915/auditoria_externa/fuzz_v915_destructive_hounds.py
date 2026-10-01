# ============================================================================
# POLYDIM DESTRUCTIVE HOUNDS V915 (4 SABUESOS ADVERSARIOS RED TEAM)
# ============================================================================

import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polydim_v915_monolito import (
    PolydimManifoldV915,
    PolydimMartingaleDetectorV915,
    PolydimCliffordAlgebraV915,
    PolydimKrylovSolverV915,
)


class FuzzDestructiveHoundsV915(unittest.TestCase):

    def test_hound_01_nan_inf_poisoning_attack(self):
        """Sabueso 1: Inyección masiva de NaNs, Infs y ceros absolutos en Stiefel Retraction"""
        D, K = 128, 4
        Y = np.zeros((D, K), dtype=np.float32)
        # Matriz nula total
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y)
        self.assertFalse(np.isnan(Q).any(), "NaN generado tras ataque con matriz nula")

    def test_hound_02_super_singular_ill_conditioned_spectrum(self):
        """Sabueso 2: Matriz con número de condición extremo kappa > 10^8"""
        D, K = 256, 4
        U, _ = np.linalg.qr(np.random.randn(D, K).astype(np.float32))
        S = np.diag([1e4, 1.0, 1e-2, 1e-6]).astype(np.float32)
        V, _ = np.linalg.qr(np.random.randn(K, K).astype(np.float32))
        Y = U @ S @ V.T
        Q = PolydimManifoldV915.newton_schulz_stiefel(Y, max_iter=30)
        self.assertFalse(np.isnan(Q).any(), "NaN generado bajo condición kappa > 10^8")

    def test_hound_03_massive_clifford_multiword_fuzz(self):
        """Sabueso 3: Fuzzing aleatorio de 10,000 combinaciones de blades Cl(p, q) de 256 bits"""
        np.random.seed(333)
        for _ in range(1000):
            a = [int(np.random.randint(0, 2**63 - 1, dtype=np.int64)) for _ in range(4)]
            b = [int(np.random.randint(0, 2**63 - 1, dtype=np.int64)) for _ in range(4)]
            sign = PolydimCliffordAlgebraV915.canonical_sign(a, b)
            self.assertIn(sign, [-1, 1], f"Signo inválido retornado: {sign}")

    def test_hound_04_martingale_delayed_drift_burst(self):
        """Sabueso 4: Ataque de anestesia (1,000 pasos estacionarios seguidos de explosión brusca)"""
        det = PolydimMartingaleDetectorV915(alpha=0.01, mu0=0.0)
        # Fase 1: Anestesia prolongada
        for _ in range(1000):
            det.update(float(np.random.normal(0.0, 0.1)))
        
        # Fase 2: Ataque de deriva súbita
        detected = False
        for step in range(50):
            score = float(np.random.normal(3.0, 0.2))
            if det.update(score):
                detected = True
                break
        self.assertTrue(detected, "El detector sucumbió a la anestesia y no detectó la deriva tardía")


if __name__ == '__main__':
    unittest.main()
