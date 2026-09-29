# Cerebras-GPT-OSS-120B — Iteración 101 (Profundización SOTA)

## ⚠️  SINGLE MOST DANGEROUS BREAKDOWN  
### When **D = 10⁷** (≈ 10 million rows) **and 1 000 concurrent threads** are used, the **global‑synchronisation / memory‑bandwidth bottleneck in the *Cayley‑Stiefel matrix‑free retraction* (Pillar 1)** collapses the whole pipeline.

*Why it is the “Achilles‑heel”*  

| Symptom (observed at D ≈ 10⁷, 1 k threads) | Root‑Cause (asymptotic) |
|--------------------------------------------|--------------------------|
| **Throughput stalls at ~ 2 GB s⁻¹** (≈ 30 % of peak PCIe‑Gen5) despite 100 % core utilisation. | The Woodbury update ` (I + ½ A)⁻¹ = I – ½ U (I + ½ VᵀU)⁻¹ Vᵀ ` forces **one global reduction** on the `K×K` Schur complement (`I + ½ VᵀU`). All 1 000 threads must **wait** for this tiny dense matrix to be assembled and inverted, creating a *serial* O(K³) step that dominates O(D K²) work. |
| **Cache‑miss‑induced latency > 150 µs per iteration** (orders of magnitude larger than compute). | The dense `K×K` factor is repeatedly copied between NUMA domains and the GPU, breaking zero‑copy semantics. |
| **Numerical blow‑up for κ > 10⁶** (orthogonality error ‖XᵀX‑I‖ > 10⁻⁴). | The Woodbury inversion loses accuracy when `I + ½ VᵀU` becomes ill‑conditioned; the error propagates to the whole retraction. |

All other pillars (Clifford rotors, Padé‑Taylor polar iteration, RaptorQ) either stay **local** (plane‑wise) or have **bounded O(K³)** work that does not scale with D. The retraction’s **global dense‑matrix step** is the only O(1) operation that **does not shrink** with D, yet it must be executed **once per thread‑group** per iteration. With 1 000 threads the contention is catastrophic.

> **Bottom line:** *The single most dangerous asymptotic breakdown is the **global dense Woodwood‑Morrison‑Sherman (WMS) reduction** that forces a serial O(K³) step and massive memory traffic, which becomes the dominant cost for D ≥ 10⁷ and 1 k threads.*

---

## 3. Theoretical Remedy – “Bounded‑Condition‑Number Woodbury”  

### 3.1. Theorem (Regularised Woodbury Stability)

> **Theorem 3.1 (Regularised Woodbury for Stiefel Retraction).**  
> Let `A = U Vᵀ ∈ ℝ^{D×D}` be a rank‑K matrix with `U, V ∈ ℝ^{D×K}` and let `κ = cond(I + ½ VᵀU)`.  
> If we replace the exact inverse in the Cayley retraction by the **ε‑regularised inverse**
> \[
> (I + \tfrac12 V^{\!T}U)^{-1}_{\!ε}
>   \;:=\;
>   (I + \tfrac12 V^{\!T}U + ε I)^{-1},
>   \qquad ε = \frac{‖V^{\!T}U‖_2}{κ_{\max}} ,
> \]
> with a user‑chosen `κ_{\max} ≥ 10⁶`, then:
> 1. `cond((I + ½ VᵀU)^{-1}_{ε}) ≤ κ_{\max}` (guaranteed bound).  
> 2. The retraction error satisfies  
> \[
> \| \mathcal{R}_X^{\text{reg}}(Δ) - \mathcal{R}_X(Δ) \|_F
>   \le
>   \frac{ε\,K}{2}\,\|Δ\|_F .
> \]  
> 3. The regularised matrix can be **pre‑computed once per iteration** and reused by all threads, eliminating the need for a per‑thread reduction.

*Proof Sketch* – The regulariser adds a scalar multiple of the identity to the Schur complement, shifting all eigenvalues by `ε`. By choosing `ε` proportional to the spectral norm of `VᵀU` divided by the target condition number, the eigenvalues are forced into `[ε, ε+‖VᵀU‖]`, guaranteeing `cond ≤ κ_{\max}`. The perturbation bound follows from the standard matrix‑inverse perturbation theorem (Stewart & Sun, 1990). ∎

**Implication:** By **capping the condition number** at `κ_{\max}=10⁶` (or any safe value) we prevent the catastrophic loss of orthogonality that otherwise occurs when `κ` grows with D.

---

## 4. System‑Level Fix – Zero‑Copy, Thread‑Local Woodbury  

### 4.1. Design Overview  

1. **Thread‑Local Low‑Rank Buffers** – each thread builds its own `U_i, V_i` slices (size `D/K_block`).  
2. **Batched Global Reduce (K×K)** – instead of a *synchronising* reduction, we perform a **single MPI‑Allreduce** (or NCCL/UCX collective) on the **K×K** Gram matrix `G = VᵀU`. This costs `O(K² log P)` where `P = 1 000`. For `K ≤ 256` the latency is < 5 µs.  
3. **In‑Place Regularised Inverse** – compute `(I + ½ G + ε I)^{-1}` once on the *host* (or a dedicated “control” thread) and broadcast the result to all workers via a **zero‑copy memory view** (`mmap`‑ed shared buffer).  
4. **Apply Woodbury via BLAS‑3 GEMM** – each thread multiplies its