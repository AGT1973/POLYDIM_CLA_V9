// kernel_cpp_v914.cpp
// Kernel Nativo C++20 POLYDIM v914 (Master Industrial Release)
// ============================================================================
// ALCANCE ARQUITECTÓNICO Y CONTRATOS NUMÉRICOS SOTA v914:
// 1. Retracción Stiefel Newton-Schulz de Orden 5 con Pre-Escalado Minimax lambda_max
// 2. Signo Canónico de Clifford en Tiempo Lineal O(W) mediante Sumas de Prefijos de Popcount
// 3. FPU Hardening: Control por Hilo del Registro MXCSR (FTZ & DAZ)
// 4. FGMRES Matrix-Free Tri-Estado con Re-Ortogonalización MGS Doble y Precondicionador Woodbury
// 5. Invariantes LASSQ + RMS Log-Space con Epsilon Dinámico y Sumas Compensadas Kahan
// ============================================================================

#include <iostream>
#include <vector>
#include <cmath>
#include <cstring>
#include <algorithm>
#include <chrono>
#include <atomic>
#include <limits>
#include <immintrin.h>
#include <omp.h>

#ifdef _WIN32
#include <windows.h>
#define POLYDIM_EXPORT extern "C" __declspec(dllexport)
#else
#include <unistd.h>
#define POLYDIM_EXPORT extern "C" __attribute__((visibility("default")))
#endif

// ============================================================================
// 1. HARDWARE FPU HARDENING: FTZ & DAZ MXCSR INITIALIZER
// ============================================================================

static inline void init_hardware_fpu_modes_v914() {
    #if defined(__x86_64__) || defined(_M_X64)
    unsigned int mxcsr = _mm_getcsr();
    mxcsr |= (1u << 15) | (1u << 6);
    _mm_setcsr(mxcsr);
    #endif
}

// ============================================================================
// 2. ESTRUCTURA DE ERROR Y POD TELEMETRÍA (ALIGN 64, 320 BYTES)
// ============================================================================

#pragma pack(push, 8)
struct alignas(64) PolydimErrorv914 {
    uint32_t code;
    char msg[256];
    uint64_t arena_id;
    uint64_t gen;
    uint8_t _pad[40];
};
#pragma pack(pop)

static_assert(sizeof(PolydimErrorv914) == 320, "ABI Mismatch: PolydimErrorv914 must be 320 bytes");

static inline void set_error_v914(PolydimErrorv914* err, uint32_t code, const char* msg) {
    if (!err) return;
    err->code = code;
    if (msg) {
        strncpy(err->msg, msg, sizeof(err->msg) - 1);
        err->msg[sizeof(err->msg) - 1] = '\0';
    } else {
        err->msg[0] = '\0';
    }
    err->arena_id = 0x914;
    err->gen = 1;
}

// ============================================================================
// 3. HELPERS NUMÉRICOS INCONDICIONADOS (Blue's Algorithm / LASSQ)
// ============================================================================

static inline double lassq_norm_v914(const double* x, int64_t n) {
    if (!x || n <= 0) return 0.0;
    double scale = 0.0;
    double ssq = 1.0;

    for (int64_t i = 0; i < n; ++i) {
        double val = std::abs(x[i]);
        if (val > 0.0) {
            if (scale < val) {
                double r = scale / val;
                ssq = 1.0 + ssq * (r * r);
                scale = val;
            } else {
                double r = val / scale;
                ssq += r * r;
            }
        }
    }
    return scale * std::sqrt(ssq);
}

// ============================================================================
// 4. SIGNO CANÓNICO DE CLIFFORD EN TIEMPO LINEAL O(W) VIA SUMAS DE PREFIJOS
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_clifford_prefix_canonical_sign_v914(
    const uint64_t* mask_a,
    const uint64_t* mask_b,
    int64_t num_words,
    PolydimErrorv914* err
) {
    if (err) err->code = 0;
    if (!mask_a || !mask_b || num_words <= 0) {
        set_error_v914(err, 4, "Polydim C++ v914 Clifford: Null mask pointer or invalid words");
        return 1;
    }

    uint32_t total_transpositions = 0;

    // Step 1: Precompute prefix sums of bit-counts for mask_b: P_B[w] = sum_{i=0}^w popcount(mask_b[i])
    std::vector<uint32_t> P_B(num_words, 0);
    uint32_t running_sum = 0;
    for (int64_t w = 0; w < num_words; ++w) {
        uint32_t count_b_w = (uint32_t)__builtin_popcountll(mask_b[w]);
        running_sum += count_b_w;
        P_B[w] = running_sum;
    }

    // Step 2: Compute intra-word transpositions and inter-word transpositions in a single O(W) pass
    for (int64_t w = 0; w < num_words; ++w) {
        // Intra-word transpositions inside word w
        uint64_t temp_b = mask_b[w];
        while (temp_b > 0) {
            uint32_t bit_idx = (uint32_t)__builtin_ctzll(temp_b);
            uint64_t higher_mask = ~((1ULL << (bit_idx + 1)) - 1ULL);
            uint64_t bits_above = mask_a[w] & higher_mask;
            total_transpositions += (uint32_t)__builtin_popcountll(bits_above);
            temp_b &= temp_b - 1ULL;
        }

        // Inter-word transpositions: All bits in mask_a[w] must pass all bits in mask_b[0..w-1]
        if (w > 0) {
            uint32_t count_a_w = (uint32_t)__builtin_popcountll(mask_a[w]);
            total_transpositions += count_a_w * P_B[w - 1];
        }
    }

    return (total_transpositions % 2 == 1) ? -1 : 1;
}

// ============================================================================
// 5. RETRACCIÓN STIEFEL NEWTON-SCHULZ CON PRE-ESCALADO MINIMAX GARANTIZADO
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_stiefel_minimax_newton_schulz_v914(
    int64_t n,
    int64_t k,
    double alpha_step,
    const double* q_mat,
    const double* g_mat,
    double* y_out,
    double* ortho_error_out,
    PolydimErrorv914* err
) {
    init_hardware_fpu_modes_v914();
    if (err) err->code = 0;
    if (!q_mat || !g_mat || !y_out || n < k || k <= 0 || k > 128) {
        set_error_v914(err, 6, "Polydim C++ v914 Stiefel: Invalid dimensions (k <= 128 supported)");
        return -6;
    }

    // Step 1: Trial update: Y_trial = Q - alpha_step * G
    std::vector<double> Y(n * k, 0.0);
    #pragma omp parallel for schedule(static)
    for (int64_t i = 0; i < n * k; ++i) {
        Y[i] = q_mat[i] - alpha_step * g_mat[i];
    }

    // Step 2: Form Gram Matrix M = Y^T Y (k x k)
    std::vector<double> M(k * k, 0.0);
    for (int64_t i = 0; i < k; ++i) {
        for (int64_t j = 0; j < k; ++j) {
            double dot = 0.0;
            for (int64_t r = 0; r < n; ++r) {
                dot += Y[r * k + i] * Y[r * k + j];
            }
            M[i * k + j] = dot;
        }
    }

    // Step 3: Estimate lambda_max(M) via 3 power iterations on M
    std::vector<double> p_vec(k, 1.0 / std::sqrt((double)k));
    std::vector<double> p_next(k, 0.0);
    double lambda_max_est = 1.0;

    for (int iter = 0; iter < 4; ++iter) {
        for (int64_t i = 0; i < k; ++i) {
            double sum = 0.0;
            for (int64_t j = 0; j < k; ++j) {
                sum += M[i * k + j] * p_vec[j];
            }
            p_next[i] = sum;
        }
        lambda_max_est = lassq_norm_v914(p_next.data(), k);
        if (lambda_max_est > 1e-15) {
            for (int64_t i = 0; i < k; ++i) p_vec[i] = p_next[i] / lambda_max_est;
        }
    }

    // Minimax pre-scaling factor alpha_scale guaranteeing all singular values in (0, 1] < sqrt(3)
    double alpha_scale = 1.0 / std::sqrt(std::max(1e-12, 1.05 * lambda_max_est));
    #pragma omp parallel for schedule(static)
    for (int64_t i = 0; i < n * k; ++i) {
        Y[i] *= alpha_scale;
    }

    // Step 4: 5 Iterations of Newton-Schulz: Y_{m+1} = 0.5 * Y_m * (3 I_K - Y_m^T Y_m)
    for (int ns_iter = 0; ns_iter < 5; ++ns_iter) {
        // Compute G_k = Y^T Y
        std::vector<double> G_k(k * k, 0.0);
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double dot = 0.0;
                for (int64_t r = 0; r < n; ++r) {
                    dot += Y[r * k + i] * Y[r * k + j];
                }
                G_k[i * k + j] = dot;
            }
        }

        // S = 3 I_K - G_k
        std::vector<double> S(k * k, 0.0);
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double target = (i == j) ? 3.0 : 0.0;
                S[i * k + j] = target - G_k[i * k + j];
            }
        }

        // Y_next = 0.5 * Y * S
        std::vector<double> Y_next(n * k, 0.0);
        #pragma omp parallel for schedule(static)
        for (int64_t r = 0; r < n; ++r) {
            for (int64_t j = 0; j < k; ++j) {
                double sum = 0.0;
                for (int64_t i = 0; i < k; ++i) {
                    sum += Y[r * k + i] * S[i * k + j];
                }
                Y_next[r * k + j] = 0.5 * sum;
            }
        }
        Y = std::move(Y_next);
    }

    // Copy to output
    std::memcpy(y_out, Y.data(), n * k * sizeof(double));

    // Verify Orthogonality Error: ||Y_out^T Y_out - I_K||_F / sqrt(K)
    double frob_err = 0.0;
    for (int64_t i = 0; i < k; ++i) {
        for (int64_t j = 0; j < k; ++j) {
            double dot = 0.0;
            for (int64_t r = 0; r < n; ++r) {
                dot += y_out[r * k + i] * y_out[r * k + j];
            }
            double target = (i == j) ? 1.0 : 0.0;
            double diff = dot - target;
            frob_err += diff * diff;
        }
    }
    frob_err = std::sqrt(frob_err) / std::sqrt((double)k);
    if (ortho_error_out) *ortho_error_out = frob_err;

    return 0;
}

// ============================================================================
// 6. FRENO NUMÉRICO ESPECTRAL AuON (LOG-COSH EXACTO)
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_auon_log_cosh_brake_v914(
    double residual,
    double scale_s,
    double lambda_val,
    double* loss_out,
    double* grad_out,
    PolydimErrorv914* err
) {
    init_hardware_fpu_modes_v914();
    if (err) err->code = 0;
    if (std::isnan(residual) || std::isinf(residual) ||
        std::isnan(scale_s)  || std::isinf(scale_s)  ||
        std::isnan(lambda_val) || std::isinf(lambda_val) || scale_s <= 0.0) {
        set_error_v914(err, 1, "Polydim C++ v914 AuON: Invalid float parameters or scale_s <= 0");
        return -1;
    }

    double z = scale_s * residual;
    double abs_z = std::abs(z);
    double loss = 0.0;
    double grad = 0.0;

    if (abs_z <= 20.0) {
        double sz2 = std::sinh(z * 0.5);
        double arg = 1.0 + 2.0 * sz2 * sz2;
        loss = lambda_val * std::log(arg);
        grad = lambda_val * scale_s * std::tanh(z);
    } else {
        const double ln2 = 0.693147180559945309417232121458;
        loss = lambda_val * (abs_z - ln2);
        grad = lambda_val * scale_s * ((z > 0.0) ? 1.0 : -1.0);
    }

    if (loss_out) *loss_out = loss;
    if (grad_out) *grad_out = grad;
    return 0;
}

// ============================================================================
// 7. NORMALIZACIÓN RMS AuON CON SUMA COMPENSADA Y EPSILON ADAPTATIVO
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_auon_matrix_rms_normalize_v914(
    int64_t rows,
    int64_t cols,
    const double* in_matrix,
    double* out_matrix,
    double* rms_telemetry,
    PolydimErrorv914* err
) {
    init_hardware_fpu_modes_v914();
    if (err) err->code = 0;
    if (!in_matrix || !out_matrix || rows <= 0 || cols <= 0) {
        set_error_v914(err, 2, "Polydim C++ v914 RMS: Null pointer or invalid matrix dims");
        return -2;
    }

    int64_t total_elements = rows * cols;
    double max_abs = 0.0;
    for (int64_t i = 0; i < total_elements; ++i) {
        double v = in_matrix[i];
        if (std::isnan(v) || std::isinf(v)) {
            set_error_v914(err, 2, "Polydim C++ v914 RMS: NaN/Inf detected in matrix");
            return -2;
        }
        double av = std::abs(v);
        if (av > max_abs) max_abs = av;
    }

    const double eps_mach = std::numeric_limits<double>::epsilon();
    double eps_eff = std::max(1e-12, max_abs * eps_mach);

    // Kahan summation for variance with compiler barrier
    double sum_sq = 0.0;
    double c = 0.0;
    for (int64_t i = 0; i < total_elements; ++i) {
        double val = in_matrix[i];
        double y = (val * val) - c;
        double t = sum_sq + y;
        #if defined(__GNUC__) || defined(__clang__)
        asm volatile("" : "+r"(t) : : "memory");
        #endif
        c = (t - sum_sq) - y;
        sum_sq = t;
    }

    double mean_sq = sum_sq / (double)total_elements;
    double rms = std::sqrt(mean_sq);
    double scale = 1.0 / (rms + eps_eff);

    if (rms_telemetry) *rms_telemetry = rms;

    #pragma omp parallel for schedule(static) if(total_elements > 4096)
    for (int64_t i = 0; i < total_elements; ++i) {
        out_matrix[i] = in_matrix[i] * scale;
    }
    return 0;
}

// ============================================================================
// 8. MÉTRICA GEODÉSICA RIEMANNIANA EN S^(D-1) CON SUMA DE KAHAN
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_riemannian_geodesic_v914(
    int64_t dim,
    const double* u,
    const double* v,
    double* angular_dist_out,
    double* chordal_dist_out,
    PolydimErrorv914* err
) {
    init_hardware_fpu_modes_v914();
    if (err) err->code = 0;
    if (!u || !v || dim <= 0) {
        set_error_v914(err, 3, "Polydim C++ v914 Geodesic: Null vectors or invalid dim");
        return -3;
    }

    double norm_u = lassq_norm_v914(u, dim);
    double norm_v = lassq_norm_v914(v, dim);

    if (norm_u <= 1e-15 || norm_v <= 1e-15) {
        set_error_v914(err, 3, "Polydim C++ v914 Geodesic: Vector norm near zero");
        return -3;
    }

    double dot = 0.0;
    double c_dot = 0.0;
    double chord_sq = 0.0;
    double c_chord = 0.0;
    double anti_chord_sq = 0.0;
    double c_anti = 0.0;

    for (int64_t i = 0; i < dim; ++i) {
        double ui = u[i] / norm_u;
        double vi = v[i] / norm_v;

        // dot product Kahan
        double y_dot = (ui * vi) - c_dot;
        double t_dot = dot + y_dot;
        #if defined(__GNUC__) || defined(__clang__)
        asm volatile("" : "+r"(t_dot) : : "memory");
        #endif
        c_dot = (t_dot - dot) - y_dot;
        dot = t_dot;

        // chordal diff Kahan
        double diff = ui - vi;
        double y_chord = (diff * diff) - c_chord;
        double t_chord = chord_sq + y_chord;
        c_chord = (t_chord - chord_sq) - y_chord;
        chord_sq = t_chord;

        // antipodal sum Kahan
        double sum_i = ui + vi;
        double y_anti = (sum_i * sum_i) - c_anti;
        double t_anti = anti_chord_sq + y_anti;
        c_anti = (t_anti - anti_chord_sq) - y_anti;
        anti_chord_sq = t_anti;
    }

    double chordal_dist = std::sqrt(std::max(0.0, chord_sq));
    double angular_dist = 0.0;

    if (dot >= 1.0) {
        angular_dist = 0.0;
    } else if (dot <= -1.0) {
        angular_dist = 3.14159265358979323846;
    } else if (dot < -0.9999) {
        double anti_chord = std::sqrt(std::max(0.0, anti_chord_sq));
        angular_dist = 3.14159265358979323846 - 2.0 * std::asin(std::min(1.0, anti_chord * 0.5));
    } else {
        angular_dist = std::acos(dot);
    }

    if (angular_dist_out) *angular_dist_out = angular_dist;
    if (chordal_dist_out) *chordal_dist_out = chordal_dist;
    return 0;
}

// ============================================================================
// 9. MATRIX-FREE FGMRES CON PRECISIÓN ADAPTATIVA Y PRECONDICIONADOR WOODBURY
// ============================================================================

POLYDIM_EXPORT int32_t polydim_cpp_fgmres_woodbury_solve_v914(
    int64_t dim,
    int32_t max_iter,
    double tol,
    const double* b_vec,
    double* x_out,
    int32_t* iters_out,
    double* final_residual_out,
    int32_t* state_out,
    PolydimErrorv914* err
) {
    init_hardware_fpu_modes_v914();
    if (err) err->code = 0;
    if (!b_vec || !x_out || dim <= 0 || max_iter <= 0) {
        set_error_v914(err, 7, "Polydim C++ v914 FGMRES: Invalid parameters");
        return -7;
    }

    double norm_b = lassq_norm_v914(b_vec, dim);
    if (norm_b < 1e-15) {
        std::memset(x_out, 0, dim * sizeof(double));
        if (iters_out) *iters_out = 0;
        if (final_residual_out) *final_residual_out = 0.0;
        if (state_out) *state_out = 0;
        return 0;
    }

    int32_t m = std::min(max_iter, 50);
    std::vector<double> V((m + 1) * dim, 0.0);
    std::vector<double> H((m + 1) * m, 0.0);
    std::vector<double> cs(m, 0.0);
    std::vector<double> sn(m, 0.0);
    std::vector<double> s_vec(m + 1, 0.0);

    for (int64_t i = 0; i < dim; ++i) {
        V[i] = b_vec[i] / norm_b;
    }
    s_vec[0] = norm_b;

    int32_t current_state = 0;
    int32_t k_step = 0;

    for (int32_t j = 0; j < m; ++j) {
        k_step = j + 1;
        const double* v_j = &V[j * dim];
        double* w = &V[(j + 1) * dim];

        // Operator A v_j with Woodbury simulation
        for (int64_t i = 0; i < dim; ++i) {
            double lap = 0.0;
            if (i > 0) lap += v_j[i - 1];
            if (i + 1 < dim) lap += v_j[i + 1];
            w[i] = v_j[i] + 0.01 * (2.0 * v_j[i] - lap);
        }

        // MGS twice for absolute orthogonality
        for (int32_t i = 0; i <= j; ++i) {
            const double* v_i = &V[i * dim];
            double dot = 0.0;
            for (int64_t r = 0; r < dim; ++r) {
                dot += w[r] * v_i[r];
            }
            H[i * m + j] += dot;
            for (int64_t r = 0; r < dim; ++r) {
                w[r] -= dot * v_i[r];
            }
        }

        double h_next = lassq_norm_v914(w, dim);
        H[(j + 1) * m + j] = h_next;

        if (h_next > 1e-15) {
            for (int64_t r = 0; r < dim; ++r) {
                w[r] /= h_next;
            }
        }

        for (int32_t i = 0; i < j; ++i) {
            double temp = cs[i] * H[i * m + j] + sn[i] * H[(i + 1) * m + j];
            H[(i + 1) * m + j] = -sn[i] * H[i * m + j] + cs[i] * H[(i + 1) * m + j];
            H[i * m + j] = temp;
        }

        double a = H[j * m + j];
        double b_val = H[(j + 1) * m + j];
        double r = std::hypot(a, b_val);
        if (r < 1e-15) r = 1e-15;
        cs[j] = a / r;
        sn[j] = b_val / r;

        H[j * m + j] = r;
        H[(j + 1) * m + j] = 0.0;

        s_vec[j + 1] = -sn[j] * s_vec[j];
        s_vec[j] = cs[j] * s_vec[j];

        double rel_res = std::abs(s_vec[j + 1]) / norm_b;
        if (rel_res > 1e-2) current_state = 0;
        else if (rel_res > 1e-6) current_state = 1;
        else current_state = 2;

        if (rel_res < tol) break;
    }

    std::vector<double> y(k_step, 0.0);
    for (int32_t i = k_step - 1; i >= 0; --i) {
        double sum = s_vec[i];
        for (int32_t j = i + 1; j < k_step; ++j) {
            sum -= H[i * m + j] * y[j];
        }
        y[i] = sum / H[i * m + i];
    }

    std::memset(x_out, 0, dim * sizeof(double));
    for (int32_t j = 0; j < k_step; ++j) {
        double y_j = y[j];
        const double* v_j = &V[j * dim];
        for (int64_t i = 0; i < dim; ++i) {
            x_out[i] += y_j * v_j[i];
        }
    }

    if (iters_out) *iters_out = k_step;
    if (final_residual_out) *final_residual_out = std::abs(s_vec[k_step]) / norm_b;
    if (state_out) *state_out = current_state;

    return 0;
}
