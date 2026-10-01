# polydim_triton_kernel_v912.py
# Triton ROCm / GPU Kernel POLYDIM v912 (Master Industrial Release)
# ============================================================================

import torch
import triton
import triton.language as tl

@triton.jit
def auon_rms_normalize_kernel_v912(
    matrix_ptr, out_ptr, rms_out_ptr,
    n_cols,
    stride_row, stride_col,
    BLOCK_SIZE: tl.constexpr
):
    """AuON Log-Space RMS Normalize Triton Kernel v912."""
    row_idx = tl.program_id(0)
    col_offsets = tl.arange(0, BLOCK_SIZE)
    mask = col_offsets < n_cols

    row_start_ptr = matrix_ptr + row_idx * stride_row
    vals = tl.load(row_start_ptr + col_offsets * stride_col, mask=mask, other=0.0)

    abs_vals = tl.abs(vals)
    ln2 = 0.6931471805599453
    lcs = tl.where(abs_vals < 20.0, tl.log(tl.cosh(abs_vals)), abs_vals - ln2)
    lcs_sq = lcs * 2.0

    max_log = tl.max(tl.where(mask, lcs_sq, -float('inf')), axis=0)
    exp_vals = tl.exp(lcs_sq - max_log)
    sum_exp = tl.sum(tl.where(mask, exp_vals, 0.0), axis=0)

    log_rms = max_log * 0.5 + 0.5 * tl.log(sum_exp / n_cols)
    rms_val = tl.exp(log_rms)
    if tl.program_id(0) == 0:
        tl.store(rms_out_ptr, rms_val)

    scale = tl.exp(-log_rms)
    out_vals = vals * scale

    out_row_start_ptr = out_ptr + row_idx * stride_row
    tl.store(out_row_start_ptr + col_offsets * stride_col, out_vals, mask=mask)
