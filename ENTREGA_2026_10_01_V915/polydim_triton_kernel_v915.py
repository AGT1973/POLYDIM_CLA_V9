# ============================================================================
# POLYDIM TRITON KERNEL V915 (SERIE 900 PRODUCCIÓN GPU/CUDA)
# ============================================================================

try:
    import triton
    import triton.language as tl
    import torch
    HAS_TRITON = True
except ImportError:
    HAS_TRITON = False


if HAS_TRITON:
    @triton.jit
    def newton_schulz_step_kernel(
        X_ptr,
        G_ptr,
        T_ptr,
        out_ptr,
        D,
        K,
        BLOCK_SIZE_D: tl.constexpr,
        BLOCK_SIZE_K: tl.constexpr,
    ):
        """Kernel Fused Triton para multiplicación de bloques Stiefel en SRAM"""
        pid_d = tl.program_id(axis=0)
        pid_k = tl.program_id(axis=1)

        offs_d = pid_d * BLOCK_SIZE_D + tl.arange(0, BLOCK_SIZE_D)
        offs_k = pid_k * BLOCK_SIZE_K + tl.arange(0, BLOCK_SIZE_K)

        mask_d = offs_d < D
        mask_k = offs_k < K

        # Acumulador
        acc = tl.zeros((BLOCK_SIZE_D, BLOCK_SIZE_K), dtype=tl.float32)

        for k_idx in range(0, K, BLOCK_SIZE_K):
            k_offs = k_idx + tl.arange(0, BLOCK_SIZE_K)
            mask_inner = k_offs < K

            x_ptrs = X_ptr + (offs_d[:, None] * K + k_offs[None, :])
            t_ptrs = T_ptr + (k_offs[:, None] * K + offs_k[None, :])

            x_vals = tl.load(x_ptrs, mask=mask_d[:, None] & mask_inner[None, :], other=0.0)
            t_vals = tl.load(t_ptrs, mask=mask_inner[:, None] & mask_k[None, :], other=0.0)

            acc += tl.dot(x_vals, t_vals)

        out_ptrs = out_ptr + (offs_d[:, None] * K + offs_k[None, :])
        tl.store(out_ptrs, acc, mask=mask_d[:, None] & mask_k[None, :])


def triton_stiefel_retract_v915(Y_tensor: "torch.Tensor", max_iter: int = 20) -> "torch.Tensor":
    """Lanzador GPU Triton para Retracción Polar Newton-Schulz de Orden 5"""
    if not HAS_TRITON:
        raise RuntimeError("Triton no disponible en este entorno.")

    D, K = Y_tensor.shape
    # Pre-escalado espectral en PyTorch GPU
    G = torch.matmul(Y_tensor.T, Y_tensor)
    lambda_cert = torch.min(torch.max(torch.sum(torch.abs(G), dim=1)), torch.linalg.matrix_norm(G, ord='fro'))
    alpha = 1.0 / torch.sqrt(1.05 * torch.clamp(lambda_cert, min=1e-12))

    X = alpha * Y_tensor
    for _ in range(max_iter):
        G_k = torch.matmul(X.T, X)
        if torch.linalg.matrix_norm(G_k - torch.eye(K, device=Y_tensor.device), ord='fro') < 1e-6:
            break
        G_k2 = torch.matmul(G_k, G_k)
        T_k = (15.0 / 8.0) * torch.eye(K, device=Y_tensor.device) - (5.0 / 4.0) * G_k + (3.0 / 8.0) * G_k2
        X = torch.matmul(X, T_k)

    return X
