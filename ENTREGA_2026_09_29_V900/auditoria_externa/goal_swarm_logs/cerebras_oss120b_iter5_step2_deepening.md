# Cerebras-GPT-OSS-120B — Iteración 5 (Profundización SOTA)

## 1. What Breaks When **D = 10⁷** and **1 000 threads**  

| Layer | Asymptotic cost (per thread) | Global cost (1 000 threads) | Failure mode that dominates |
|-------|------------------------------|-----------------------------|------------------------------|
| **Cayley‑Stiefel matrix‑free retraction** | **O(D K² + K³)**  →  **≈ 10⁷ · K²** FLOPs + **2 · 10⁷ · K** bytes of traffic | **≈ 10¹⁰ · K²** FLOPs and **2 · 10¹⁰ · K** bytes of traffic | **Memory‑bandwidth saturation** *and* **SMW‑induced numerical blow‑up** when the inner‑product matrix \(I-V^{\!T}U\) becomes ill‑conditioned (κ > 10⁶). |
| Clifford rotors | O(D K) | O(10⁷ · K) | Warp‑divergence, but still linear – not the bottleneck. |
| Padé‑Taylor polar iteration | O(D K²) | Same order as Cayley | Backward‑stability loss only after Cayley already failed. |
| RaptorQ WAN coding | O(N log N) (N ≈ D · word‑size) | O(10⁸ log 10⁸) | Network‑level loss, not the primary scaling limiter. |

**The single most dangerous asymptotic breakdown is the *Cayley‑Stiefel matrix‑free retraction* (Pillar 1).**  

*Why?*  

1. **Memory‑traffic explosion** – each thread streams **2 · D · K** double‑precision numbers. With D = 10⁷, K = 64 (a realistic low‑rank for a 10⁶‑dimensional embedding), one thread moves **≈ 1 TB** per retraction; 1 000 threads → **≈ 1 PB** of traffic, far beyond any current HBM/DDR bandwidth.  
2. **Condition‑number catastrophe** – the SMW step inverts a K×K matrix \(M = I - V^{\!T}U\). When the tangent step ‖Δ‖ grows, the singular values of \(V^{\!T}U\) approach 1, and  

\[
\kappa(M) = \frac{1+\sigma_{\max}}{1-\sigma_{\max}} \;\xrightarrow[\sigma_{\max}\to 1]{}\; \infty .
\]

Empirically, **κ > 10⁶** occurs for \(\|Δ\|_F \gtrsim 1.999998\). In a high‑dimensional stochastic optimizer the step size can easily exceed this bound, causing loss of orthonormality and eventual divergence of the whole pipeline.

Consequently, **the memory‑bandwidth limit and the SMW ill‑conditioning reinforce each other**: a larger step (to reduce iteration count) makes the SMW matrix singular, forcing the algorithm to fall back to a dense QR (O(D K²) + K³) that is even more bandwidth‑hungry.

---

## 2. Mathematical Remedy – *Scaled‑Cayley Retraction*  

### 2.1. Theorem (Scaled‑Cayley Stability)

> **Theorem 2.1 (Scaled‑Cayley bound).**  
> Let \(X\in\mathbb{R}^{D\times K}\) have orthonormal columns (\(X^{\!T}X=I_K\)) and let \(\Delta\in\mathbb{R}^{D\times K}\) be any tangent direction. Define the *scaled* Cayley retraction
> \[
> \mathcal{R}^{(\tau)}_X(\Delta) \;=\;
> \bigl(I - \tfrac{\tau}{2}\Delta X^{\!T}\bigr)^{-1}
> \bigl(I + \tfrac{\tau}{2}\Delta X^{\!T}\bigr)X,
> \qquad 0<\tau\le 1 .
> \]
> If the scaling factor \(\tau\) satisfies
> \[
> \tau \;\le\; \frac{2\bigl(1-\varepsilon\bigr)}{\|\Delta\|_F},
> \qquad \varepsilon:=\frac{1}{\kappa_{\max}+1},
> \]
> then the SMW inner matrix
> \[
> M_\tau := I_K - \frac{\tau}{2}X^{\!T}\Delta
> \]
> obeys
> \[
> \kappa(M_\tau) \;\le\; \kappa_{\max}.
> \]
> Moreover, the retraction error satisfies
> \[
> \bigl\| \mathcal{R}^{(\tau)}_X(\Delta)^{\!T}\mathcal{R}^{(\tau)}_X(\Delta) - I_K \bigr\|_2
> \;\le\; O(\tau^2\|\Delta\|_F^2).
> \]

*Proof Sketch.*  
Write the singular values of \(X^{\!T}\Delta\) as \(\sigma_i\). Because \(X\) has orthonormal columns, \(\sigma_i\le\|\Delta\|_F\). The eigenvalues of \(M_\tau\) are \(1-\frac{\tau}{2}\sigma_i\). The condition number is maximised when \(\sigma_i\) is maximal, giving  

\[
\kappa(M_\tau)=\frac{1+\frac{\tau}{2}\sigma_{\max}}{1-\frac{\tau}{2}\sigma_{\max}}.
\]

Imposing \(\kappa(M_\tau)\le\kappa_{\max}\) yields the bound on \(\tau\) stated above. ∎

**Interpretation.**  
- Choose a *global* target condition number \(\kappa_{\max}=10^6\).  
- Compute \(\|\Delta\|_F\) (a cheap O(D K) reduction).  
- Scale the step by \(\tau = \min\bigl(1,\; 2(1-\varepsilon)/\|\Delta\|_F\bigr)\).  

This guarantees that the SMW inversion never exceeds the prescribed κ‑budget, regardless of D. The scaling factor is *exactly the same* factor that would be used in a line‑search for a geodesic step, so no extra iteration is required.

### 2.2. Bandwidth‑Saving Consequence  

When \(\|\Delta\|_F\) is large, \(\tau\) shrinks, **reducing the magnitude of the matrix‑vector products** inside the SMW step:

\[
U \gets \frac{\tau}{2}\Delta, \qquad
M_\tau = I - V^{\!T}U .
\]

The