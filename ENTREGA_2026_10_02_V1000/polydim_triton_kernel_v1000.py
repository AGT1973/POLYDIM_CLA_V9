# ============================================================================
# POLYDIM TRITON / ROCm / TPU KERNEL V1000
# Arquitectura: GPU AMD Instinct (MI300X/MI325X), NVIDIA CUDA, TPU v3-8
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
    def polydim_rms_log_space_kernel_v1000(
        x_ptr, out_ptr, n_elements, BLOCK_SIZE: tl.constexpr
    ):
        pid = tl.program_id(axis=0)
        block_start = pid * BLOCK_SIZE
        offsets = block_start + tl.arange(0, BLOCK_SIZE)
        mask = offsets < n_elements
        x = tl.load(x_ptr + offsets, mask=mask, other=0.0)
        x_clamped = tl.maximum(tl.abs(x), 1e-12)
        out = tl.log(x_clamped)
        tl.store(out_ptr + offsets, out, mask=mask)

def launch_triton_rms_v1000(x: torch.Tensor) -> torch.Tensor:
    if not TRITON_AVAILABLE or not x.is_cuda:
        return torch.log(torch.clamp(torch.abs(x), min=1e-12))
    out = torch.empty_like(x)
    n_elements = x.numel()
    BLOCK_SIZE = 1024
    grid = lambda meta: (triton.cdiv(n_elements, meta['BLOCK_SIZE']),)
    polydim_rms_log_space_kernel_v1000[grid](x, out, n_elements, BLOCK_SIZE=BLOCK_SIZE)
    return out
