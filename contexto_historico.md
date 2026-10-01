
# Contexto Histórico - POLYDIM EINSOF (Checkpoint V911 -> V912)

**Estado Operativo:**
- **V911 Certificada (Fase 1 Dual-Run):** Implementa el monitor SOTATelemetryDriftMonitor (CUSUM/EWMA) en Python y el prototipo base C++ para pybind11 (polydim_pybind_v911.cpp), coexistiendo con ctypes.
- Tests físicos y Fuzz hounds: PASSED 14/14 (Exit Code 0).
- Backups en Git (V900 branch) y GDrive (I:\Mi unidad\POLYDIM_BACKUP) asegurados.

**Staging Teórico Consolidado (Hoja de Ruta V912):**
Se ingirió Propuesta para V909.md y Diagnóstico.md. La refactorización exigida (Nivel 3) consta de:
1. **FGMRES Matrix-Free & Precisión Mixta:** Solver GPU-resident con iteración Arnoldi en BF16/FP16 y refinamiento iterativo en FP64, usando la Identidad de Woodbury explícita (sin armar  	imes 2K$).
2. **DLPack / PyBind11 (Zero-Copy):** Abandono definitivo de ctypes. Intercambio de tensores HBM3 directo vía dlpack.h (Nivel 0 C Exchange API).
3. **E-Process Conformal Martingales:** Reemplazo del CUSUM estático por BOCPD acoplado a Martingalas Conformes (E-values) para detección topológica rigurosa.

**Siguiente Acción Esperada:**
Ejecución de la migración V912 (Fase 2) que reconstruirá el puente compilado y la arquitectura de Krylov.
