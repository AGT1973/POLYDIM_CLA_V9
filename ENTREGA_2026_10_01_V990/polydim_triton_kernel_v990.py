# ============================================================================
# POLYDIM TRITON KERNEL V990 (SERIE 900 PRODUCCION QUINCUAGESIMAL CERTIFICADA - HITO 80)
# ============================================================================

import torch

try:
    import triton
    import triton.language as tl

    @triton.jit
    def riesz_feller_dirac_kernel(
        in_ptr, out_ptr, D, alpha, dt, BLOCK_SIZE: tl.constexpr
    ):
        pid = tl.program_id(axis=0)
        offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
        mask = offsets < D

        prev_offsets = (offsets - 1 + D) % D
        next_offsets = (offsets + 1) % D

        val = tl.load(in_ptr + offsets, mask=mask, other=0.0)
        val_p = tl.load(in_ptr + prev_offsets, mask=mask, other=0.0)
        val_n = tl.load(in_ptr + next_offsets, mask=mask, other=0.0)

        laplacian = 2.0 * val - val_p - val_n
        abs_lap = tl.abs(laplacian) + 1e-8
        grad = (val_n - val_p) * 0.5

        exp_factor = (alpha - 1.0) * 0.5
        frac_lap = tl.exp(exp_factor * tl.log(abs_lap))
        out_val = val - dt * frac_lap * grad

        tl.store(out_ptr + offsets, out_val, mask=mask)

    def launch_riesz_feller_dirac_triton(x: torch.Tensor, alpha: float = 1.5, dt: float = 0.01):
        D = x.numel()
        out = torch.empty_like(x)
        BLOCK_SIZE = 1024
        grid = (triton.cdiv(D, BLOCK_SIZE),)
        riesz_feller_dirac_kernel[grid](x, out, D, alpha, dt, BLOCK_SIZE=BLOCK_SIZE)
        return out

except ImportError:
    def launch_riesz_feller_dirac_triton(x: torch.Tensor, alpha: float = 1.5, dt: float = 0.01):
        # CPU PyTorch fallback
        prev = torch.roll(x, 1)
        nxt = torch.roll(x, -1)
        lap = 2.0 * x - prev - nxt
        frac_lap = torch.pow(torch.clamp(torch.abs(lap), min=1e-8), (alpha - 1.0) * 0.5)
        grad = (nxt - prev) * 0.5
        return x - dt * frac_lap * grad
