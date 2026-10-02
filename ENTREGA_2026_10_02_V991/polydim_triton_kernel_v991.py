# ============================================================================
# POLYDIM TRITON / ROCm ACCELERATOR KERNEL V991 (SERIE 900)
# ============================================================================

import os
import sys

try:
    import triton
    import triton.language as tl
    HAS_TRITON = True
except ImportError:
    HAS_TRITON = False

if HAS_TRITON:
    @triton.jit
    def polydim_cayley_smw_triton_kernel_v991(
        X_ptr, U_ptr, V_ptr, Out_ptr,
        D, K, BLOCK_SIZE: tl.constexpr
    ):
        pid = tl.program_id(axis=0)
        offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
        mask = offsets < D

        x_vals = tl.load(X_ptr + offsets, mask=mask, other=0.0)
        u_term = tl.zeros([BLOCK_SIZE], dtype=tl.float32)
        v_term = tl.zeros([BLOCK_SIZE], dtype=tl.float32)

        for k in range(K):
            u_k = tl.load(U_ptr + offsets * K + k, mask=mask, other=0.0)
            v_k = tl.load(V_ptr + offsets * K + k, mask=mask, other=0.0)
            u_term += u_k * x_vals
            v_term += v_k * x_vals

        out_vals = x_vals - 2.0 * u_term + 2.0 * v_term
        tl.store(Out_ptr + offsets, out_vals, mask=mask)

def run_cayley_smw_triton(x_tensor, u_tensor, v_tensor):
    if not HAS_TRITON:
        raise RuntimeError("Triton / ROCm accelerator is not available on this platform.")
    import torch
    D, K = u_tensor.shape
    out_tensor = torch.empty_like(x_tensor)
    grid = lambda meta: (triton.cdiv(D, meta['BLOCK_SIZE']),)
    polydim_cayley_smw_triton_kernel_v991[grid](
        x_tensor, u_tensor, v_tensor, out_tensor,
        D, K, BLOCK_SIZE=1024
    )
    return out_tensor
