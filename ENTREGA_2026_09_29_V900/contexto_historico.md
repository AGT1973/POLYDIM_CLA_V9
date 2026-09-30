# Contexto Histórico y Estado de Consolidación POLYDIM V900 (Regla 13 & Regla 19)

> **Fecha:** 2026-09-29  
> **Estado:** Ingesta Activa (Regla 19) — Veto de código estricto.  
> **Auditorías Vectorizadas:** Claude Red Team, GLM-5.2, Kimi K3 Sabueso Adversarial, Especificación SOTA Dion3 (arXiv:2608.11612) y CacheMuon (arXiv:2606.16371).  
> **Destino Vectorial:** `E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite` (tabla `audit_ingestion_vault`, 4 registros maestros).

---

## 🎯 Especificación Matemática SOTA Gram Newton-Schulz (BR-012)

### 1. Formulación Exacta Orientada a la Dimensión Menor
Para $X \in \mathbb{R}^{D \times K}$ con $n = \min(D, K)$ y $m = \max(D, K)$:
- Si $D \ge K$:
  $$G = X^\top X \in \mathbb{R}^{K \times K}, \quad Q_0 = I_K$$
  $$\text{Recurrencia: } Z_t = b_t R_{t-1} + c_t R_{t-1}^2, \quad P_t = a_t I + Z_t, \quad Q_t = Q_{t-1} P_t, \quad R_t = P_t R_{t-1} P_t$$
  $$\operatorname{polar}(X) = X Q_T$$
- Si $D < K$:
  $$G = X X^\top \in \mathbb{R}^{D \times D}, \quad \operatorname{polar}(X) = Q_T X$$

### 2. Complejidad de Memoria y Aritmética
- **Memoria:** $O(DK + K^2)$ (cero materialización $D \times D$).
- **Trabajo:** $O(DK^2 + T K^3)$ con $T$ iteraciones.
- **Buffers:** Doble buffering estricto con $M_{\text{peak}} \le c_X D K s_X + c_G K^2 s_G$.

### 3. Estabilización por Reinicio y Simetría
- Reinicio periódico tras $t=2$ en esquemas de $T=5$: $X_2 = X Q_2 \implies R_{\text{nuevo}} = X_2^\top X_2$, reseteando $Q \leftarrow I$.
- Kernels simétricos (cálculo de triángulo inferior reflejado al superior).
- Desacople taxonómico: GNS (exacto) vs Low-Rank Sampling vs CacheMuon (temporal).
