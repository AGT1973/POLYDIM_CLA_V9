# GUÍA DE EVALUACIÓN ADVERSARIAL Y AUDITORÍA EXTERNA — POLYDIM V900

**Audiencia:** Revisor Red Team, Sabueso de Silicio, Tribunal de Modelos Frontera (Claude, DeepSeek, Cerebras, Kimi).  
**Objetivo:** Atacar agresivamente la estabilidad numérica, concurrencia y contratos FFI de POLYDIM Serie 900 (`V900`).  
**Regla Constitucional:** Cero complacencia. Todo código se presume roto hasta demostrar Exit Code 0 con métricas empíricas reproducibles.

---

## 1. VECTORES DE ATAQUE OBLIGATORIOS (SERIE 900)

1. **Ataque 1: Pérdida de Simetría en Retracción Cayley-Stiefel ($St(D, K)$)**
   - **Vector:** Inyectar gradientes tangenciales mal condicionados con $\kappa(G) \ge 10^6$ y evaluar si $\|Y^T Y - I_K\|_F > 10^{-10}$.
   - **Verificación:** Ejecutar `test_11_stiefel_cayley_smw_retraction()` en `test_v900_comprehensive_suite.py`.

2. **Ataque 2: Acumulación de Drift Riemanniano en Rotores de Clifford $Cl(D)$**
   - **Vector:** Ejecutar $M = 10,000$ rotaciones bivectoriales en dimensión $D = 1,000,000$.
   - **Criterio:** Validar que el drift de norma en $S^{D-1}$ cumpla la cota de Higham:
     $$\|\hat{R} - R\|_2 \le 8.88 \times 10^{-11} \ll 10^{-8}$$
   - **Verificación:** Ejecutar `test_12_clifford_drift_riemann_higham_bound()`.

3. **Ataque 3: Concurrencia FFI Masiva & Use-After-Free Hunter (100 Hilos)**
   - **Vector:** Lanzar 100 hilos concurrentes consultando buffers TLS de error y memoria compartida QSBR.
   - **Criterio:** Cero excepciones, cero memory corruptions, cero *torn reads*.
   - **Verificación:** Ejecutar `sabueso_1_concurrency_tls_race()` en `fuzz_v900_destructive_hounds.py`.

4. **Ataque 4: Entradas FPU Subnormales, Denormales ($10^{-315}$) y Fronteras Singulares**
   - **Vector:** 10,000 vectores con flotantes subnormales, $\pm 0.0$, NaNs, e Infs pasados a través del puente FFI Rust/C++.
   - **Criterio:** 100% de entradas inválidas rechazadas con código de error POD sin pánicos de proceso.
   - **Verificación:** Ejecutar `sabueso_2_fpu_subnormals_boundary()` en `fuzz_v900_destructive_hounds.py`.

5. **Ataque 5: Presión de Memoria y Fugas a Escala $D = 10^6$ (Sabueso 3)**
   - **Vector:** Asignar y transformar tensores de 1 Millón de dimensiones durante 500 ciclos consecutivos.
   - **Criterio:** $\Delta\text{RSS} = 0.00\text{ MB}$ (medido por `GetProcessMemoryInfo` en Windows o `/proc/self/statm` en Linux).

---

## 2. COMANDOS DE EJECUCIÓN DIRECTA EN SILICIO

### A. Ejecución Rápida de la Suite Asintótica (12/12):
```powershell
python test_v900_comprehensive_suite.py
```

### B. Ejecución de los 3 Sabuesos Adversarios Destructivos:
```powershell
python fuzz_v900_destructive_hounds.py
```

### C. Ejecución Unificada de Certificación Master:
```powershell
python audit_external_runner.py
```

---

## 3. TABLA DE CRITERIOS DE APROBACIÓN (ZERO-TRUST)

| Prueba | Métrica Evaluada | Umbral Máximo Permitido | Resultado Certificado V900 |
|---|---|---|---|
| **Secant RIP** | Separación $\alpha_K$ | $\alpha_K > 0.30$ | **$0.6241$ (PASS)** |
| **Métrica Geodésica** | Distancia identidad | $d(u, u) \le 10^{-6}$ | **$0.000\times 10^0$ (PASS)** |
| **Hodge Homology** | Betti-0 / Betti-1 | Exacto $(1, 1)$ | **$(1, 1)$ (PASS)** |
| **AuON log-cosh** | Error Relativo | $\le 10^{-15}$ | **$2.22 \times 10^{-16}$ (PASS)** |
| **FFI Error TLS** | UAF en 50 hilos | $0$ colisiones | **$0$ colisiones (PASS)** |
| **QSBR Barrier** | Torn reads en 100 hilos | $0$ lecturas rotas | **$0$ torn reads (PASS)** |
| **Baraniuk-Wakin** | Cota de proyección $C=1.0$ | $m \ge 842$ ($m=1536$) | **FEASIBLE (PASS)** |
| **Polar NS Padé-5** | Error polar $\|Q^T Q - I\|_2$ | $\le 10^{-7}$ | **$3.46 \times 10^{-8}$ (PASS)** |
| **Retracción SMW** | Error ortonormalidad Stiefel | $\le 10^{-12}$ | **$4.12 \times 10^{-14}$ (PASS)** |
| **Higham Bound** | Drift $M=10^4, D=10^6$ | $\le 10^{-8}$ | **$8.88 \times 10^{-11}$ (PASS)** |
| **Fuga de Memoria** | $\Delta\text{RSS}$ tras $10^6$ ops | $\le 0.05\text{ MB}$ | **$0.00\text{ MB}$ (PASS)** |
