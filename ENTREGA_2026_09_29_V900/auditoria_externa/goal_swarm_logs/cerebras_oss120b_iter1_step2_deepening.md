# Cerebras-GPT-OSS-120B — Iteración 1 (Profundización SOTA)

## 1️⃣  THE SINGLE MOST DANGEROUS BREAKDOWN  
### **Memory‑Bandwidth / Orthogonality Collapse** in the **Cayley‑Stiefel Matrix‑Free Retraction**  

| Scaling target | \(D = 10^{7}\) | Concurrency | 1 000 threads (shared‑memory NUMA node) |
|----------------|----------------|-------------|----------------------------------------|
| Baseline cost  | \(\mathcal{O}(DK^{2})\)  (≈ \(10^{7}K^{2}\) FLOPs) | Each thread touches the full \(D\)‑length Stiefel factor | **\( \approx 10^{7}K^{2}\) bytes of traffic per iteration** |
| Memory subsystem | 2 TB/s (peak) on a 2‑socket 256‑core server | 1 000 × simultaneous streams → **≈ 10 TB/s** required (exceeds hardware) |
| Numerical side  | Sherman‑Morrison‑Woodbury (SMW) adds a rank‑\(K\) correction \(\mathbf{U}\mathbf{V}^{\top}\) | For \(\kappa>10^{6}\) the correction term amplifies round‑off by \(\mathcal{O}(\kappa K)\) | **Loss of orthogonality** → retraction no longer stays on the Stiefel manifold → downstream optimisation diverges. |

**Why this is the *single* catastrophic failure:**  

* The **O(DK²)** term dominates all other costs (the Padé iteration, Clifford rotors, and RaptorQ are *sub‑linear* in \(D\)).  
* With 1 000 threads the **memory‑traffic pressure** grows linearly with the number of threads because each thread reads/writes the same large \(D\)‑vector (the Stiefel factor). The hardware cannot sustain the required bandwidth → **stalling** and **NUMA‑remote accesses** that add tens of microseconds per thread, breaking the sub‑millisecond latency budget.  
* Simultaneously, the **SMW update** becomes numerically unstable when the underlying linear system has \(\kappa>10^{6}\). The rank‑\(K\) correction is computed as  

\[
\mathbf{X}_{\text{new}} = \mathbf{X} - \mathbf{U}\bigl(\mathbf{I}_{K} + \mathbf{V}^{\top}\mathbf{U}\bigr)^{-1}\mathbf{V}^{\top}\mathbf{X},
\]

where \(\mathbf{U},\mathbf{V}\in\mathbb{R}^{D\times K}\).  
If \(\|\mathbf{V}^{\top}\mathbf{U}\| \approx \kappa\), the inverse term suffers from **catastrophic cancellation** and the orthogonality error grows as  

\[
\|\mathbf{X}_{\text{new}}^{\top}\mathbf{X}_{\text{new}} - \mathbf{I}\| \;\gtrsim\; \mathcal{O}\!\bigl(\epsilon_{\text{mach}}\kappa K\bigr),
\]

which for \(\kappa=10^{6}, K\ge 64\) already exceeds \(10^{-7}\) – far beyond the tolerance required for high‑precision manifold optimisation.

Hence **the memory‑bandwidth bottleneck coupled with SMW‑induced orthogonality loss** is the decisive asymptotic failure mode when \(D=10^{7}\) and 1 000 threads are employed.

---

## 2️⃣  MATHEMATICAL FIX – THEOREM‑LEVEL BOUND  

### 2.1. Replace SMW with a **Blocked QR‑Based Retraction**  

**Theorem (Blocked QR Retraction Stability).**  
Let \(\mathbf{X}\in\mathbb{R}^{D\times K}\) have full column rank and let \(\mathbf{Y}=\mathbf{X}+\Delta\) with \(\|\Delta\|_{2}\le\eta\). Perform a **blocked Householder QR** on \(\mathbf{Y}\) using block size \(b\) (e.g. \(b=\sqrt{D}\)). Then the resulting orthonormal factor \(\mathbf{Q}\) satisfies  

\[
\|\mathbf{Q}^{\top}\mathbf{Q} - \mathbf{I}_{K}\|_{2} \;\le\; c\,\epsilon_{\text{mach}}\,(1+\eta\kappa(\mathbf{X})) ,
\]

where \(c\) is a modest constant (\(c\le 5\)) independent of \(D\) and \(K\).  

*Proof sketch:* The blocked QR algorithm can be expressed as a sequence of **orthogonal transformations** each applied to a \(b\times K\) panel. Each panel operation is backward stable (Householder reflections are unitary up to \(\mathcal{O}(\epsilon_{\text{mach}})\)). The accumulation of errors across \(\lceil D/b\rceil\) panels yields the bound above because the condition number of the *panel* never exceeds \(\kappa(\mathbf{X})\) (the global condition number) and the orthogonal nature prevents error amplification. ∎  

**Implication:** The orthogonality error now grows **linearly** with \(\kappa\) (instead of \(\kappa K\) for SMW) and is **independent of the number of threads** because each thread works on a disjoint panel.

### 2.2. Reduce the **\(DK^{2}\)** traffic with a **Randomized Subspace Embedding**  

**Lemma (Subspace Embedding for Stiefel Retraction).**  
Let \(\mathbf{S}\in\mathbb{R}^{\tilde D\times D}\) be a **Johnson‑Lindenstrauss (JL) sketch** with  

\[
\tilde D = \mathcal{O}\!\bigl(K\log K / \delta^{2}\bigr),
\]

and distortion \(\delta\le 0.1\). For any \(\mathbf{X}\in\mathbb{R}^{D\times K}\),

\[
(1-\delta)\|\mathbf{X}\|_{F}^{2} \;\le\; \|\mathbf{S}\mathbf{X}\|_{F}^{2} \;\le\; (1+\delta)\|\mathbf{X}\|_{F}^{2}.
\]

If we compute the retraction on the **sketched matrix** \(\mathbf{\hat X}= \mathbf{S}\mathbf{X}\) (size \(\tilde D\times K\)) and lift the result back with \(\mathbf{S}^{\top}\), the orthogonality error is bounded by  

\[
\|\mathbf{Q}^{\top}\mathbf{Q} - \mathbf{I}\|_{2} \;\le\; \mathcal{O}(\delta) + \mathcal{O}(\epsilon_{\text{mach}}\kappa(\mathbf{X})).
\]

Thus we replace the \(\mathcal{O}(DK^{2})\) work by  

\[
\mathcal{O}(\tilde D K^{2}) = \mathcal{O}\!\bigl(K^{3}\log K\bigr),
\]

which is **independent of \(D\)** and trivially fits within the 1 000‑thread memory budget.

*Reference:*  [Mahoney, “Randomized Algorithms for Matrices and Data”, Foundations and Trends, 2011].

---

## 3️⃣  ENGINEERING IMPLEMENTATION – C++ / Rust PATCHES  

Below are **minimal, drop‑in replacements** for the two critical kernels:

1. **Blocked QR Retraction** (C++17, AVX‑512‑aware)  
2. **Fast JL Sketch** (Rust 1.73, SIMD‑accelerated)  

Both are **thread‑local**; the outer driver distributes panels across the 1 000 threads via a simple work‑stealing queue (no global synchronization needed).

---

### 3.1. C++ – Blocked Householder QR (replaces `cayley_stiefel_retract_smw`)  

```cpp
// ---------------------------------------------------------------
// file: cayley_stiefel_retract_qr.hpp
// ---------------------------------------------------------------
#pragma once
#include <immintrin.h>
#include <vector>
#include <cstddef>
#include <cassert>
#include <omp.h>

// Helper: apply a Householder reflector to a panel (b x K)
inline void apply_householder(double