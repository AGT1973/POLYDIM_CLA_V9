# ============================================================================
# POLYDIM TRITON KERNEL V930 (GPU ACCELERATED TENSOR CONTRACTIONS & HOUSEHOLDER)
# ============================================================================

import torch

try:
    import triton
    import triton.language as tl
    TRITON_AVAILABLE = True
except ImportError:
    TRITON_AVAILABLE = False


if TRITON_AVAILABLE:
    @triton.jit
    def parallel_transport_householder_kernel(
        x_ptr, y_ptr, v_ptr, out_ptr,
        D: tl.constexpr, BLOCK_SIZE: tl.constexpr
    ):
        pid = tl.program_id(axis=0)
        offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
        mask = offsets < D

        x = tl.load(x_ptr + offsets, mask=mask, other=0.0)
        y = tl.load(y_ptr + offsets, mask=mask, other=0.0)
        v = tl.load(v_ptr + offsets, mask=mask, other=0.0)

        # Vectorized Householder reflection
        dot_xy = tl.sum(x * y, axis=0)
        dot_xpy_v = tl.sum((x + y) * v, axis=0)

        denom = 1.0 + dot_xy
        factor = dot_xpy_v / denom

        v_out = v - factor * (x + y)
        tl.store(out_ptr + offsets, v_out, mask=mask)


def triton_spherical_transport(x: torch.Tensor, y: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    if not (TRITON_AVAILABLE and x.is_cuda):
        dot_xy = torch.dot(x, y)
        dot_xpy_v = torch.dot(x + y, v)
        denom = 1.0 + dot_xy
        if denom < 1e-7:
            return -v
        return v - (dot_xpy_v / denom) * (x + y)

    D = x.numel()
    out = torch.empty_like(v)
    BLOCK_SIZE = 1024
    grid = ((D + BLOCK_SIZE - 1) // BLOCK_SIZE,)
    parallel_transport_householder_kernel[grid](
        x, y, v, out,
        D=D, BLOCK_SIZE=BLOCK_SIZE
    )
    return out
