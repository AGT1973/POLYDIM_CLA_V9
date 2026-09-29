# Cerebras-GPT-OSS-120B — Iteración 100 (Profundización SOTA)

## 1.  The “single most dangerous” asymptotic failure  

| Metric | Value at the target scale | Why it blows up first |
|--------|---------------------------|----------------------|
| **Memory traffic per iteration** (Cayley‑Stiefel retraction) | \(\displaystyle \underbrace{D}_{10^{7}}\times\underbrace{K}_{\;{\cal O}(10^{2})}\;\approx\;10^{9}\) floats ≈ 8 GB read + 8 GB write per thread | The operation is **bandwidth‑bound**; with 1 000 threads the *aggregate* demand ≈ 16 TB per retraction, far beyond any current DDR‑5 or HBM‑2e subsystem. The kernel stalls on the memory bus long before any arithmetic or synchronization limit is reached. |
| **Condition‑number amplification** (Sherman‑Morrison‑Woodbury) | \(\kappa(A+UV^{\!\top})\le\kappa(A)\bigl(1+\|U\|\,\|V\|\,\kappa(A)\bigr)\) → for \(\kappa(A)\approx10^{6}\) and \(\|U\|,\|V\|\sim\sqrt{K}\) the factor can exceed \(10^{12}\) | The SMW formula becomes numerically unstable; the orthonormality of the Stiefel factor is lost after **one** retraction, contaminating every downstream geometry (geodesics, parallel transport, etc.). |
| **Thread‑level false sharing** | The \(D\times K\) tangent matrix is stored column‑major; 1 000 threads each write to a distinct column but the columns are interleaved in the same cache line (64 B). | Even if the memory system could keep up, the per‑core L1/L2 miss‑rate would explode, adding ~30 % latency overhead per iteration. |

**Conclusion:**  
The **memory‑bandwidth saturation of the matrix‑free Cayley‑Stiefel retraction** is the *first* asymptotic bottleneck that will cause the whole pipeline to stall when \(D=10^{7}\) and 1 000 threads are employed. The secondary, but equally fatal, problem is the **loss of numerical stability** caused by an uncontrolled condition number in the SMW update. Any fix must therefore (i) **drastically cut the amount of data moved per thread** and (ii) **regularise the SMW step** so that \(\kappa\) never exceeds the safe ceiling (≈ \(10^{5}\) for double precision).

---

## 2.  Mathematical Remedy – Block‑Sketch‑SMW with Tikhonov Regularisation  

### 2.1  Theorem (Stability of Regularised SMW)

> **Theorem 1 (Regularised SMW bound).**  
> Let \(A\in\mathbb{R}^{D\times D}\) be symmetric positive‑definite with \(\kappa(A)=\lambda_{\max}(A)/\lambda_{\min}(A)\).  
> Let \(U,V\in\mathbb{R}^{D\times K}\) and define the *regularised* update  
> \[
>   \tilde A \;=\; A \;+\; U V^{\!\top} \;+\; \lambda I_D ,
> \qquad \lambda>0 .
> \]
> Then
> \[
>   \kappa(\tilde A)\;\le\;
>   \frac{\lambda_{\max}(A)+\|U\|_2\|V\|_2+\lambda}
>        {\lambda_{\min}(A)+\lambda}
>   \;\le\;
>   \frac{\kappa(A)\bigl(1+\|U\|_2\|V\|_2/\lambda_{\min}(A)\bigr)+\lambda/\lambda_{\min}(A)}
>        {1+\lambda/\lambda_{\min}(A)} .
> \]
> Choosing
> \[
>   \lambda \;=\; \frac{\|U\|_2\|V\|_2}{\sqrt{\kappa_{\text{target}}}-1}\,
>   \lambda_{\min}(A)
> \]
> guarantees \(\kappa(\tilde A)\le\kappa_{\text{target}}\).

*Proof Sketch.*  Apply the Weyl inequality to the eigenvalues of \(A+\lambda I\) and then the matrix‑norm bound \(\|UV^{\!\top}\|_2\le\|U\|_2\|V\|_2\).  The regulariser lifts the smallest eigenvalue, limiting the condition number. ∎  

**Interpretation for POLYDIM:**  
- Set a *target* condition number \(\kappa_{\text{target}}=10^{5}\).  
- Compute \(\|U\|_2\|V\|_2\) cheaply (it is \(\mathcal{O}(DK)\) but can be approximated by a *sketch*; see §2.2).  
- Insert the scalar \(\lambda\) into the SMW formula; the inverse is now **well‑conditioned** and can be evaluated with standard BLAS without catastrophic loss of orthogonality.

### 2.2  Dimensionality‑Reducing Sketch  

Instead of forming the full \(D\times K\) tangent matrix, we replace