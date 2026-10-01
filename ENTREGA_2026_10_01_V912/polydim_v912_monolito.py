import os
import ctypes
import numpy as np

class EProcessMartingaleMonitor:
    def __init__(self):
        self.history = []
    
    def add_observation(self, val):
        self.history.append(val)
        return 0.0 # Return E-Value martingale score (dummy)

class FGMRES_MatrixFree:
    def __init__(self):
        pass
    def solve(self, b):
        return np.zeros_like(b)

class PolydimEngineV912:
    def __init__(self):
        self.monitor = EProcessMartingaleMonitor()
        self.solver = FGMRES_MatrixFree()

    def step(self, tensor):
        pass
