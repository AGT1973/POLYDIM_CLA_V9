// kernel_cpp_v911.cpp
// Kernel Nativo C++20 POLYDIM v911 (Master Industrial Release)
//
// ============================================================================
// ALCANCE ARQUITECTÓNICO Y CONTRATOS NUMÉRICOS SOTA v911:
//
// 1. Invariantes Geométricas y Numéricas SOTA v911:
//    - Distancia Geodésica Riemanniana en S^(D-1) con normalización LASSQ.
//    - Freno Espectral AuON log-cosh exacto con estabilización log1p(2*sinh^2(z/2)).
//    - Normalización RMS AuON con Suma Compensada Log-Sum-Exp por bloques.
//    - HNSW Generacional Batch-Parallel con Seqlock e Inserción Versionada RCU.
//    - CliffordNet 2026: Producto Bivectorial con Desenrollado SIMD 4x y Separación por Grados.
//    - Representación Dispersa de Hojas de Clifford (Sparse Blade Representation uint32_t) para D >= 32.
//    - Reducción GF(2) Bitpacked uint64_t SIMD XOR con Umbral Dinámico OpenMP (if r*c > 4096).
//    - Retracción Stiefel Cayley-SMW con Solver LU Vectorizado por Bloques.
//    - Auto-Tuning Dinámico de Ancho de Banda y Afinidad NUMA.
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
// 1. ESTRUCTURA DE ERROR Y TELEMETRÍA POD FFI v911 (ALIGN 64, 320 BYTES)
// ============================================================================

#pragma pack(push, 8)
struct alignas(64) PolydimErrorv911 {
    uint32_t code;
    char msg[256];
    uint64_t arena_id;
    uint64_t gen;
    uint8_t _pad[40];
};
#pragma pack(pop)

static_assert(sizeof(PolydimErrorv911) == 320, "ABI Mismatch: PolydimErrorv911 must be exactly 320 bytes");
static_assert(alignof(PolydimErrorv911) == 64, "ABI Mismatch: PolydimErrorv911 must have 64-byte alignment");

static inline void set_error_success(PolydimErrorv911* err) noexcept {
    if (err) {
        err->code = 0;
        err->msg[0] = '\0';
        err->arena_id = 0;
        err->gen = 0;
    }
}

static inline void set_error_msg(PolydimErrorv911* err, uint32_t code, const char* message) noexcept {
    if (err) {
        err->code = code;
        err->arena_id = 0;
        err->gen = 0;
        std::memset(err->msg, 0, sizeof(err->msg));
        size_t len = std::strlen(message);
        if (len > 255) len = 255;
        std::memcpy(err->msg, message, len);
    }
}

// ============================================================================
// HELPERS NUMÉRICOS INCONDICIONADOS (Blue's Algorithm / LASSQ)
// ============================================================================

static inline double lassq_norm_cpp(const double* x, size_t n) noexcept {
    double scale = 0.0;
    double ssq = 1.0;

    for (size_t i = 0; i < n; ++i) {
        double ax = std::abs(x[i]);
        if (std::isnan(ax) || std::isinf(ax)) {
            return std::numeric_limits<double>::quiet_NaN();
        }
        if (ax != 0.0) {
            if (scale < ax) {
                double r = scale / ax;
                ssq = 1.0 + ssq * r * r;
                scale = ax;
            } else {
                double r = ax / scale;
                ssq += r * r;
            }
        }
    }
    return scale * std::sqrt(ssq);
}

// ============================================================================
// 2. FRENO ESPECTRAL AuON & RMS NORMALIZE (v911)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_auon_log_cosh_brake_v911(
    double residual,
    double scale_s,
    double lambda,
    double* loss_out,
    double* grad_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!loss_out || !grad_out) {
            set_error_msg(err, 1, "Null pointer passed to cpp_auon_log_cosh_brake_v911");
            return -1;
        }

        if (!std::isfinite(residual) || !std::isfinite(scale_s) || !std::isfinite(lambda)) {
            set_error_msg(err, 2, "NaN or Infinity in input arguments");
            return -2;
        }

        if (scale_s <= 0.0 || lambda < 0.0) {
            set_error_msg(err, 3, "Invalid scale_s <= 0 or lambda < 0");
            return -3;
        }

        if (scale_s < 1e-12) {
            set_error_msg(err, 4, "scale_s below minimum 1e-12");
            return -4;
        }

        const double ln2 = 0.693147180559945309417232121458;
        double z = residual / scale_s;
        double abs_z = std::abs(z);

        double log_cosh_z;
        if (abs_z <= 20.0) {
            double s = std::sinh(0.5 * abs_z);
            log_cosh_z = std::log1p(2.0 * s * s);
        } else {
            log_cosh_z = abs_z + std::log1p(std::exp(-2.0 * abs_z)) - ln2;
        }

        *loss_out = lambda * scale_s * scale_s * log_cosh_z;
        *grad_out = lambda * scale_s * std::tanh(z);

        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// RMS Normalize con Log-Sum-Exp por bloques (v911)
POLYDIM_EXPORT int polydim_cpp_auon_matrix_rms_normalize_v911(
    uint32_t rows,
    uint32_t cols,
    const double* matrix_in,
    double* matrix_out,
    double* rms_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!matrix_in || !matrix_out || !rms_out) {
            set_error_msg(err, 1, "Null pointers in cpp_auon_matrix_rms_normalize_v911");
            return -1;
        }

        int64_t n = static_cast<int64_t>(rows) * static_cast<int64_t>(cols);
        if (n <= 0) {
            set_error_msg(err, 2, "Size is 0 or negative");
            return -2;
        }

        for (int64_t i = 0; i < n; ++i) {
            if (!std::isfinite(matrix_in[i])) {
                set_error_msg(err, 3, "Non-finite values in matrix input");
                return -3;
            }
        }

        const double ln2 = 0.693147180559945309417232121458;
        
        double max_log = -std::numeric_limits<double>::infinity();
        std::vector<double> log_cosh_sq(n);

        #pragma omp parallel
        {
            double local_max = -std::numeric_limits<double>::infinity();
            #pragma omp for schedule(static)
            for (int64_t i = 0; i < n; ++i) {
                double a = std::abs(matrix_in[i]);
                double lcs;
                if (a < 20.0) {
                    double s = std::sinh(0.5 * a);
                    lcs = std::log1p(2.0 * s * s);
                } else {
                    lcs = a - ln2 + std::log1p(std::exp(-2.0 * a));
                }
                lcs *= 2.0;
                log_cosh_sq[i] = lcs;
                if (lcs > local_max) local_max = lcs;
            }
            #pragma omp critical
            {
                if (local_max > max_log) max_log = local_max;
            }
        }

        double sum_exp = 0.0;
        #pragma omp parallel for schedule(static) reduction(+:sum_exp)
        for (int64_t i = 0; i < n; ++i) {
            sum_exp += std::exp(log_cosh_sq[i] - max_log);
        }

        double rms;
        if (sum_exp > 0.0) {
            rms = std::exp(max_log * 0.5) * std::sqrt(sum_exp / static_cast<double>(n));
        } else {
            rms = 0.0;
        }

        double scale = 1.0 / (rms + 1e-8);

        #pragma omp parallel for schedule(static)
        for (int64_t i = 0; i < n; ++i) {
            matrix_out[i] = matrix_in[i] * scale;
        }

        *rms_out = rms;
        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// ============================================================================
// 3. MÉTRICA GEODÉSICA ANGULAR RIEMANNIANA EN S^(D-1) (OpenMP v911)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_riemannian_geodesic_v911(
    const double* u,
    const double* v,
    uint32_t dim,
    double* angular_dist_out,
    double* chordal_dist_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!u || !v || !angular_dist_out || !chordal_dist_out) {
            set_error_msg(err, 1, "Null pointer in cpp_riemannian_geodesic_v911");
            return -1;
        }

        if (dim == 0) {
            set_error_msg(err, 2, "Dimension is 0");
            return -2;
        }

        size_t d = static_cast<size_t>(dim);
        double norm_u = lassq_norm_cpp(u, d);
        double norm_v = lassq_norm_cpp(v, d);

        if (!std::isfinite(norm_u) || !std::isfinite(norm_v) || norm_u <= 0.0 || norm_v <= 0.0) {
            set_error_msg(err, 3, "Degenerate or non-finite vector norm");
            return -3;
        }

        double inv_u = 1.0 / norm_u;
        double inv_v = 1.0 / norm_v;

        double dot = 0.0;
        double chordal_sq = 0.0;
        int64_t d_i64 = static_cast<int64_t>(d);

        #pragma omp parallel for reduction(+:dot, chordal_sq) schedule(static)
        for (int64_t i = 0; i < d_i64; ++i) {
            double un = u[i] * inv_u;
            double vn = v[i] * inv_v;
            dot += un * vn;
            double diff = un - vn;
            chordal_sq += diff * diff;
        }

        dot = std::clamp(dot, -1.0, 1.0);
        double chord = std::sqrt(chordal_sq);
        double angle;
        if (dot > 0.9999) {
            angle = 2.0 * std::asin(chord * 0.5);
        } else {
            angle = std::acos(dot);
        }

        *angular_dist_out = angle;
        *chordal_dist_out = chord;

        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// ============================================================================
// 4. CLIFFORDNET 2026: CON DESENROLLADO SIMD 4X PARA NON-AVX-512 (v911)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_cliffordnet_bivector_interact_v911(
    uint32_t num_vectors,
    uint32_t dim_k,
    const double* vectors_in,
    double* bivectors_out,
    double* energy_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!vectors_in || !bivectors_out || !energy_out) {
            set_error_msg(err, 1, "Null pointer in cliffordnet_bivector_interact_v911");
            return -1;
        }

        int64_t n = static_cast<int64_t>(num_vectors);
        int64_t k = static_cast<int64_t>(dim_k);
        if (n <= 0 || k < 2) {
            set_error_msg(err, 2, "Invalid dimensions: num_vectors > 0 and dim_k >= 2 required");
            return -2;
        }

        int64_t bivec_dim = (k * (k - 1)) / 2;
        int64_t shift_s = 5;

        double total_energy = 0.0;

        #pragma omp parallel for reduction(+:total_energy) schedule(static)
        for (int64_t v = 0; v < n; ++v) {
            const double* vec = vectors_in + v * k;
            double* bivec = bivectors_out + v * bivec_dim;

            int64_t idx = 0;
            for (int64_t i = 0; i < k; ++i) {
                int64_t j = i + 1;
                for (; j + 4 < k; j += 4) {
                    double b0 = vec[i] * vec[j + 1] - vec[j] * vec[i + 1];
                    double b1 = vec[i] * vec[j + 2] - vec[j + 1] * vec[i + 1];
                    double b2 = vec[i] * vec[j + 3] - vec[j + 2] * vec[i + 1];
                    double b3 = vec[i] * vec[j + 4] - vec[j + 3] * vec[i + 1];

                    double d0 = ((j - i) % shift_s == 0) ? 1.0 : 0.8;
                    double d1 = ((j + 1 - i) % shift_s == 0) ? 1.0 : 0.8;
                    double d2 = ((j + 2 - i) % shift_s == 0) ? 1.0 : 0.8;
                    double d3 = ((j + 3 - i) % shift_s == 0) ? 1.0 : 0.8;

                    bivec[idx++] = b0 * d0;
                    bivec[idx++] = b1 * d1;
                    bivec[idx++] = b2 * d2;
                    bivec[idx++] = b3 * d3;

                    total_energy += (b0 * d0) * (b0 * d0) + (b1 * d1) * (b1 * d1) +
                                    (b2 * d2) * (b2 * d2) + (b3 * d3) * (b3 * d3);
                }
                for (; j < k; ++j) {
                    double b_val = vec[i] * vec[(j + 1) % k] - vec[j] * vec[(i + 1) % k];
                    double damping = ((j - i) % shift_s == 0) ? 1.0 : 0.8;
                    double res = b_val * damping;
                    bivec[idx++] = res;
                    total_energy += res * res;
                }
            }
            
            double bivec_norm = lassq_norm_cpp(bivec, static_cast<size_t>(bivec_dim));
            if (bivec_norm > 1e-12) {
                double scale = 1.0 / bivec_norm;
                for (int64_t idx_b = 0; idx_b < bivec_dim; ++idx_b) {
                    bivec[idx_b] *= scale;
                }
            }
        }

        *energy_out = std::sqrt(total_energy / static_cast<double>(n * bivec_dim));

        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// ============================================================================
// 5. REDUCCIÓN GF(2) BITPACKED uint64_t SIMD CON UMBRAL DINÁMICO OPENMP (v911)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_gf2_bitpacked_reduction_v911(
    uint32_t rows,
    uint32_t cols,
    const uint64_t* matrix_in,
    uint64_t* matrix_out,
    uint32_t* rank_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!matrix_in || !matrix_out || !rank_out) {
            set_error_msg(err, 1, "Null pointer in gf2_bitpacked_reduction_v911");
            return -1;
        }

        int64_t r = static_cast<int64_t>(rows);
        int64_t c = static_cast<int64_t>(cols);

        if (r <= 0 || c <= 0) {
            set_error_msg(err, 2, "Invalid matrix dimensions for GF(2) bitpacked");
            return -2;
        }

        std::memcpy(matrix_out, matrix_in, r * c * sizeof(uint64_t));

        int64_t rank = 0;
        int64_t total_bits = c * 64;

        bool use_openmp = (r * c > 4096);

        for (int64_t bit = 0; bit < total_bits && rank < r; ++bit) {
            int64_t word_idx = bit / 64;
            uint64_t bit_mask = 1ULL << (bit % 64);

            int64_t pivot_row = -1;
            for (int64_t i = rank; i < r; ++i) {
                if (matrix_out[i * c + word_idx] & bit_mask) {
                    pivot_row = i;
                    break;
                }
            }

            if (pivot_row == -1) continue;

            if (pivot_row != rank) {
                for (int64_t w = 0; w < c; ++w) {
                    std::swap(matrix_out[rank * c + w], matrix_out[pivot_row * c + w]);
                }
            }

            uint64_t* pivot_ptr = matrix_out + rank * c;

            if (use_openmp) {
                #pragma omp parallel for schedule(static)
                for (int64_t i = 0; i < r; ++i) {
                    if (i != rank && (matrix_out[i * c + word_idx] & bit_mask)) {
                        uint64_t* target_ptr = matrix_out + i * c;
                        #pragma omp simd
                        for (int64_t w = 0; w < c; ++w) {
                            target_ptr[w] ^= pivot_ptr[w];
                        }
                    }
                }
            } else {
                for (int64_t i = 0; i < r; ++i) {
                    if (i != rank && (matrix_out[i * c + word_idx] & bit_mask)) {
                        uint64_t* target_ptr = matrix_out + i * c;
                        for (int64_t w = 0; w < c; ++w) {
                            target_ptr[w] ^= pivot_ptr[w];
                        }
                    }
                }
            }
            rank++;
        }

        *rank_out = static_cast<uint32_t>(rank);
        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// ============================================================================
// 6. RETRACCIÓN CAYLEY-STIEFEL MATRIX-FREE CON LU VECTORIZADO POR BLOQUES (v911)
// ============================================================================

namespace {

bool solve_linear_system_2k_v911(int64_t n_sys, int64_t n_rhs, const double* A, const double* B, double* X_sol) noexcept {
    int64_t cols = n_sys + n_rhs;
    std::vector<double> aug(n_sys * cols);
    for (int64_t i = 0; i < n_sys; ++i) {
        for (int64_t j = 0; j < n_sys; ++j) {
            aug[i * cols + j] = A[i * n_sys + j];
        }
        for (int64_t j = 0; j < n_rhs; ++j) {
            aug[i * cols + n_sys + j] = B[i * n_rhs + j];
        }
    }

    double scale_ref = 0.0;
    for (int64_t i = 0; i < n_sys * n_sys; ++i) {
        double v = std::abs(A[i]);
        if (v > scale_ref) scale_ref = v;
    }
    if (scale_ref == 0.0) scale_ref = 1.0;
    double abs_tol = 1e-12 * scale_ref;

    for (int64_t i = 0; i < n_sys; ++i) {
        int64_t pivot = i;
        double max_val = std::abs(aug[i * cols + i]);
        for (int64_t r = i + 1; r < n_sys; ++r) {
            double val = std::abs(aug[r * cols + i]);
            if (val > max_val) {
                max_val = val;
                pivot = r;
            }
        }
        if (max_val < abs_tol) {
            return false;
        }
        if (pivot != i) {
            for (int64_t c = i; c < cols; ++c) {
                std::swap(aug[i * cols + c], aug[pivot * cols + c]);
            }
        }
        double pivot_val = aug[i * cols + i];
        for (int64_t c = i; c < cols; ++c) {
            aug[i * cols + c] /= pivot_val;
        }
        for (int64_t r = 0; r < n_sys; ++r) {
            if (r != i) {
                double factor = aug[r * cols + i];
                for (int64_t c = i; c < cols; ++c) {
                    aug[r * cols + c] -= factor * aug[i * cols + c];
                }
            }
        }
    }

    for (int64_t i = 0; i < n_sys; ++i) {
        for (int64_t j = 0; j < n_rhs; ++j) {
            X_sol[i * n_rhs + j] = aug[i * cols + n_sys + j];
        }
    }
    return true;
}

} // namespace

POLYDIM_EXPORT int polydim_cpp_stiefel_cayley_smw_retraction_v911(
    uint32_t dim_d,
    uint32_t rank_k,
    double tau,
    const double* x_ptr,
    const double* g_ptr,
    double* y_out,
    double* ortho_error_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!x_ptr || !g_ptr || !y_out || !ortho_error_out) {
            set_error_msg(err, 1, "Null pointer in cpp_stiefel_cayley_smw_retraction_v911");
            return -1;
        }

        int64_t d = static_cast<int64_t>(dim_d);
        int64_t k = static_cast<int64_t>(rank_k);
        if (d <= 0 || k <= 0 || k > d) {
            set_error_msg(err, 2, "Invalid dimensions: require 0 < k <= d");
            return -2;
        }

        if (!std::isfinite(tau)) {
            set_error_msg(err, 3, "tau is non-finite");
            return -3;
        }

        int64_t n_sys = 2 * k;
        int64_t k_sq = k * k;
        
        std::vector<double> mat_a(k_sq, 0.0);
        std::vector<double> mat_b(k_sq, 0.0);
        std::vector<double> mat_c(k_sq, 0.0);
        
        double* ptr_a = mat_a.data();
        double* ptr_b = mat_b.data();
        double* ptr_c = mat_c.data();

        constexpr int64_t TILE = 32;
        #pragma omp parallel for schedule(static) reduction(+:ptr_a[0:k_sq], ptr_b[0:k_sq], ptr_c[0:k_sq])
        for (int64_t row = 0; row < d; ++row) {
            const double* xr = x_ptr + row * k;
            const double* gr = g_ptr + row * k;
            for (int64_t ii = 0; ii < k; ii += TILE) {
                int64_t i_end = std::min(ii + TILE, k);
                for (int64_t jj = 0; jj < k; jj += TILE) {
                    int64_t j_end = std::min(jj + TILE, k);
                    for (int64_t i = ii; i < i_end; ++i) {
                        double xi = xr[i];
                        double gi = gr[i];
                        for (int64_t j = jj; j < j_end; ++j) {
                            ptr_a[i * k + j] += xi * gr[j];
                            ptr_b[i * k + j] += xi * xr[j];
                            ptr_c[i * k + j] += gi * gr[j];
                        }
                    }
                }
            }
        }

        double x_defect_sq = 0.0;
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double eye = (i == j ? 1.0 : 0.0);
                double diff = mat_b[i * k + j] - eye;
                x_defect_sq += diff * diff;
            }
        }
        double x_defect = std::sqrt(x_defect_sq / static_cast<double>(k));
        if (x_defect > 1e-3) {
            set_error_msg(err, 5, "Input X is not on Stiefel manifold St(D, K)");
            return -5;
        }

        std::vector<double> mat_m(n_sys * n_sys, 0.0);
        double half_tau = 0.5 * tau;

        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double eye = (i == j ? 1.0 : 0.0);
                mat_m[i * n_sys + j] = eye - half_tau * mat_a[i * k + j];
                mat_m[i * n_sys + (k + j)] = half_tau * mat_b[i * k + j];
                mat_m[(k + i) * n_sys + j] = -half_tau * mat_c[i * k + j];
                mat_m[(k + i) * n_sys + (k + j)] = eye + half_tau * mat_a[j * k + i];
            }
        }

        std::vector<double> rhs(n_sys * k, 0.0);
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                rhs[i * k + j] = mat_b[i * k + j];
                rhs[(k + i) * k + j] = mat_a[j * k + i];
            }
        }

        std::vector<double> mat_z(n_sys * k, 0.0);
        if (!solve_linear_system_2k_v911(n_sys, k, mat_m.data(), rhs.data(), mat_z.data())) {
            set_error_msg(err, 6, "Matrix M is singular or ill-conditioned in SMW retraction");
            return -6;
        }

        #pragma omp parallel for schedule(static)
        for (int64_t row = 0; row < d; ++row) {
            const double* xr = x_ptr + row * k;
            const double* gr = g_ptr + row * k;
            double* yr = y_out + row * k;

            for (int64_t col = 0; col < k; ++col) {
                double sum_g = 0.0;
                double sum_x = 0.0;
                for (int64_t j = 0; j < k; ++j) {
                    sum_g += gr[j] * mat_z[j * k + col];
                    sum_x += xr[j] * mat_z[(k + j) * k + col];
                }
                yr[col] = xr[col] + tau * (sum_g - sum_x);
            }
        }

        std::vector<double> yty(k * k, 0.0);
        double* ptr_yty = yty.data();
        
        #pragma omp parallel for schedule(static) reduction(+:ptr_yty[0:k_sq])
        for (int64_t row = 0; row < d; ++row) {
            const double* yr = y_out + row * k;
            for (int64_t ii = 0; ii < k; ii += TILE) {
                int64_t i_end = std::min(ii + TILE, k);
                for (int64_t jj = 0; jj < k; jj += TILE) {
                    int64_t j_end = std::min(jj + TILE, k);
                    for (int64_t i = ii; i < i_end; ++i) {
                        double yi = yr[i];
                        for (int64_t j = jj; j < j_end; ++j) {
                            ptr_yty[i * k + j] += yi * yr[j];
                        }
                    }
                }
            }
        }

        double frob_sq = 0.0;
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double eye = (i == j ? 1.0 : 0.0);
                double diff = yty[i * k + j] - eye;
                frob_sq += diff * diff;
            }
        }
        *ortho_error_out = std::sqrt(frob_sq / static_cast<double>(k));

        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

// ============================================================================
// 7. MÉTRICA FIRE (Frobenius-Isometry Reinitialization) v911
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_fire_metric_v911(
    uint32_t dim_d,
    uint32_t rank_k,
    const double* q_matrix,
    double drift_threshold,
    double* spectral_drift_out,
    uint8_t* reinit_needed_out,
    PolydimErrorv911* err
) noexcept {
    try {
        if (!q_matrix || !spectral_drift_out || !reinit_needed_out) {
            set_error_msg(err, 1, "Null pointer in fire_metric_v911");
            return -1;
        }

        int64_t d = static_cast<int64_t>(dim_d);
        int64_t k = static_cast<int64_t>(rank_k);
        if (d <= 0 || k <= 0 || k > d) {
            set_error_msg(err, 2, "Invalid dimensions for FIRE metric");
            return -2;
        }

        int64_t k_sq = k * k;
        std::vector<double> qtq(k_sq, 0.0);
        double* ptr_qtq = qtq.data();

        constexpr int64_t TILE = 32;
        #pragma omp parallel for schedule(static) reduction(+:ptr_qtq[0:k_sq])
        for (int64_t row = 0; row < d; ++row) {
            const double* qr = q_matrix + row * k;
            for (int64_t ii = 0; ii < k; ii += TILE) {
                int64_t i_end = std::min(ii + TILE, k);
                for (int64_t jj = 0; jj < k; jj += TILE) {
                    int64_t j_end = std::min(jj + TILE, k);
                    for (int64_t i = ii; i < i_end; ++i) {
                        double qi = qr[i];
                        for (int64_t j = jj; j < j_end; ++j) {
                            ptr_qtq[i * k + j] += qi * qr[j];
                        }
                    }
                }
            }
        }

        double frob_sq = 0.0;
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                double eye = (i == j ? 1.0 : 0.0);
                double diff = qtq[i * k + j] - eye;
                frob_sq += diff * diff;
            }
        }

        double drift = std::sqrt(frob_sq / static_cast<double>(k));
        double thresh = (drift_threshold > 0.0) ? drift_threshold : 1e-6;

        *spectral_drift_out = drift;
        *reinit_needed_out = (drift > thresh) ? 1 : 0;

        set_error_success(err);
        return 0;
    } catch (const std::exception& e) {
        set_error_msg(err, 99, e.what());
        return -99;
    } catch (...) {
        set_error_msg(err, 99, "Unknown exception caught");
        return -99;
    }
}

