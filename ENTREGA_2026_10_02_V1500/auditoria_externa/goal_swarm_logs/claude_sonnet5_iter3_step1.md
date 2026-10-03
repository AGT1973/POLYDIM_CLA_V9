# Claude-Sonnet-5 — Iteración 3 (Paso 1)

# POLYDIM Serie 900 — Red Team Audit: High-Dimensional Geometric Computing (D ≥ 10⁶)

## Executive Framing

Before pillar analysis, establish the operative regime constraints that govern everything downstream:

- **D ≥ 10⁶**, K (retraction rank / subspace dimension) typically 10²–10⁴
- **S^(D−1)** — the ambient sphere/Stiefel manifold St(D,K)
- Target: κ > 10⁶ tolerance, matrix-free (no D×D materialization), zero-copy across NUMA/WAN boundaries
- Failure taxonomy: (a) catastrophic cancellation at D-scale reductions, (b) orthogonality drift under repeated retraction, (c) network-induced desync of shared state, (d) Woodbury numerical collapse when K-rank update is near-singular

---

## Pillar 1 — Cayley–Stiefel Matrix-Free Retraction with Sherman–Morrison–Woodbury (SMW)

### Formulation
Cayley retraction on St(D,K):
$$R(X,\xi) = (I - \tfrac{1}{2}W)^{-1}(I + \tfrac{1}{2}W)X, \quad W = \xi X^T - X\xi^T$$

W is rank ≤ 2K, enabling the matrix-free trick: write W = UV^T − VU^T with U,V ∈ ℝ^{D×K}, then

$$(I - \tfrac12 W)^{-1} = I + \tfrac12 U\big(I_{2K} - \tfrac12 V^T U\big)^{-1}V^T$$

Cost: **O(DK² + K³)** — the D-linear term dominates for D ≥ 10⁶, K³ is the SMW core-solve.

### Findings

1. **Woodbury conditioning collapse.** The inner solve requires inverting the **2K×2K** capacitance matrix $C = I_{2K} - \tfrac12 V^TU$. Its condition number satisfies
$$\kappa(C) \gtrsim \kappa(X)^2 \cdot \|\xi\|^2$$
When the tangent step ξ is large (aggressive line search) or X drifts from orthogonality, κ(C) can exceed 10⁶ even when κ(X) ≈ 1, because SMW **squares** the effective conditioning through the two-sided rank update. This is the single largest hidden failure mode — Woodbury is *not* backward stable when C is ill-conditioned, unlike direct dense inversion.

2. **Asymptotic edge case at D ≥ 10⁶.** The O(DK²) term is BLAS-3 (GEMM-bound), so it scales well on hardware, but **round-off accumulates additively in D**: standard error analysis gives
$$\|\text{fl}(X^T\xi) - X^T\xi\| \le \gamma_D \|X\|\|\xi\|, \quad \gamma_D = \frac{Du}{1-Du}$$
At D=10⁶ with double precision (u≈1.1e-16), γ_D ≈ 1.1e-10 — tolerable, but if executed in mixed fp32 accumulation (common in GPU zero-copy kernels), γ_D ≈ 1.2e-1: **total loss of orthogonality guarantee**. This is a concrete, quantifiable ceiling: **fp32 accumulation is unusable for D > ~10⁴ under this scheme.**

3. **Rank-deficiency in V^TU.** If ξ is nearly tangent-degenerate (small effective rank), C becomes near-singular independent of D — a pure K-space problem, not a D-space one. Standard SMW literature (Higham 2002, Ch. 14) shows this is the classical failure: **SMW should never be applied when the rank-K correction approaches the null space of the capacitance matrix.**

### Mathematical Improvements

- **Regularized Woodbury**: solve $(C + \epsilon I_{2K})$ with $\epsilon = \sqrt{u}\,\|C\|$ (Higham's regularization heuristic) — restores backward stability at cost of O(K) bias, negligible for K≪D.
- **Iterative refinement in K-space only**: since the ill-conditioning localizes to the 2K×2K block, one extra refinement pass there (cost O(K³), free relative to O(DK²)) recovers full double-precision accuracy even when κ(C) ≈ 10⁸.
- **Compensated (Kahan) summation** for the O(DK²) GEMM reduction when mixed precision is unavoidable — reduces γ_D from O(Du) to O(u + Du²), essential for D ≥ 10⁶ fp32 pipelines.
- **Drift monitor**: track $\|X^TX - I_K\|_F$ every m retraction steps; trigger a full QR re-orthonormalization (O(DK²)) when drift > √u·κ(X)_est — a cheap circuit breaker.

---

## Pillar 2 — Clifford Cl(D) Bivector Rotors, 2D Decoupled Planes, Higham Backward Stability Bound

### Formulation
Rotation decomposed into ⌊D/2⌋ commuting bivector rotors:
$$R = \prod_{i=1}^{\lfloor D/2\rfloor} \exp(\theta_i B_i), \quad B_i^2 = -1$$
acting on orthogonal 2-planes — this is the CGA/geometric-algebra analogue of Jacobi/Givens rotation composition, generalized to S^(D−1).

### Findings

1. **Backward stability bound (Higham-style).** For a product of n plane rotations each with unit roundoff u, the standard bound is
$$\|\hat R - R\| \le c\cdot n \cdot u + O(u^2), \quad n = \lfloor D/2 \rfloor$$
At D=10⁶, n≈5×10⁵ — **linear accumulation in D is unavoidable** for sequential rotor composition. This gives an explicit ceiling:
$$\kappa_{\text{eff}} \le \frac{1}{c\, n\, u} \approx \frac{1}{5\times 10^5 \times 10^{-16}} \approx 2\times10^{10}$$
So κ > 10⁶ is *safe* under sequential composition, but **the margin shrinks by 5 orders of magnitude vs. the naive per-rotor bound** — this must be explicitly budgeted, not assumed.

2. **Non-commutativity trap.** Bivectors are only mutually commuting if the planes are exactly orthogonal and axis-aligned to the chosen decomposition. Any deviation (e.g., a rotor built from data-driven bivector estimate, not exact eigenplanes) introduces an O(θ_iθ_j) commutator term — this breaks the clean O(n) bound and reintroduces O(n²) worst-case error accumulation, a silent failure mode invisible until κ is measured empirically.

3. **Exponential map cost.** Naive exp(θB) per plane is cheap (2×2 rotation, O(1)), but assembling R as a full D×D operator is forbidden by the matrix-free constraint — **must be applied action-wise**, i.e., $Rv$ computed as ⌊D/2⌋ independent 2D rotations directly on paired coordinates of v. This is embarrassingly parallel (SIMD/GPU-friendly) — a genuine SOTA advantage over Pillar 1's approach *if* the plane pairing is fixed/static.

### Mathematical Improvements

- **Pairwise-summation-style composition tree**: instead of sequential left-to-right rotor multiplication, compose in a balanced binary tree → error bound becomes $O(u \log_2 n)$ instead of $O(un)$. At D=10⁶, this is a reduction from ~5×10⁵·u to ~20·u — a **~25,000× stability improvement**, directly analogous to Higham's pairwise summation result for floating-point sums.
- **Static plane-pair certification**: precompute and freeze the bivector plane decomposition (e.g., via one-time exact eigendecomposition of the generator), then apply as a fixed sparse permutation+rotation — guarantees exact commutativity, eliminating the O(n²) trap entirely.
- **Compensated angle accumulation**: when θ_i are accumulated incrementally (streaming rotations), use Kahan summation on the angles before each exp(θB) evaluation.

---

## Pillar 3 — Order-5 Padé–Taylor Polar Iteration vs. QDWH Fallback

### Formulation
Given $Q_{k+1} = \tfrac18 Q_k(15I - 10R_k + 3R_k^2)$,