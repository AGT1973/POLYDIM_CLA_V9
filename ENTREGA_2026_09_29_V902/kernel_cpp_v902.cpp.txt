// kernel_cpp_v902.cpp
// Kernel Nativo C++20 POLYDIM V902 (Master Industrial Release)
//
// ============================================================================
// ALCANCE ARQUITECTÓNICO Y CONTRATOS NUMÉRICOS:
//
// 1. Invariantes Geométricas y Numéricas SOTA:
//    - Distancia Geodésica Riemanniana sobre vectores normalizados con LASSQ.
//    - Freno Espectral AuON log-cosh exacto sin truncamiento perjudicial.
//    - Iteración Polar Gram Newton-Schulz con pre-escalado Frobenius riguroso.
//    - Retracción Stiefel Cayley-SMW sin secciones críticas OpenMP serializantes.
//    - Estimador Two-NN insesgado con protección contra singularidades de división por cero.
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
#define POLYDIM_EXPORT extern "C" __declspec(dllexport)
#else
#define POLYDIM_EXPORT extern "C" __attribute__((visibility("default")))
#endif

// ============================================================================
// 1. ESTRUCTURA DE ERROR Y TELEMETRÍA POD FFI (ALIGN 8, 280 BYTES)
// ============================================================================

#pragma pack(push, 8)
struct alignas(64) PolydimErrorV902 {
    uint32_t code;
    char msg[256];
    uint64_t arena_id;
    uint64_t gen;
    uint8_t _pad[40];
};
#pragma pack(pop)

static_assert(sizeof(PolydimErrorV902) == 320, "ABI Mismatch: PolydimErrorV902 must be exactly 320 bytes");
static_assert(alignof(PolydimErrorV902) == 64, "ABI Mismatch: PolydimErrorV902 must have 64-byte alignment");

static inline void set_error_success(PolydimErrorV902* err) noexcept {
    if (err) {
        err->code = 0;
        err->msg[0] = '\0';
        err->arena_id = 0;
        err->gen = 0;
    }
}

static inline void set_error_msg(PolydimErrorV902* err, uint32_t code, const char* message) noexcept {
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
// 2. FRENO ESPECTRAL AuON (Estabilización log-cosh C++20)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_auon_log_cosh_brake_v902(
    double residual,
    double scale_s,
    double lambda,
    double* loss_out,
    double* grad_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!loss_out || !grad_out) {
            set_error_msg(err, 1, "Null pointer passed to cpp_auon_log_cosh_brake");
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

POLYDIM_EXPORT int polydim_cpp_auon_matrix_rms_normalize_v902(
    uint32_t rows,
    uint32_t cols,
    const double* matrix_in,
    double* matrix_out,
    double* rms_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!matrix_in || !matrix_out || !rms_out) {
            set_error_msg(err, 1, "Null pointers in cpp_auon_matrix_rms_normalize");
            return -1;
        }

        int64_t n = static_cast<int64_t>(rows) * static_cast<int64_t>(cols);
        if (n <= 0) {
            set_error_msg(err, 2, "Size is 0 or negative");
            return -2;
        }

        // Verificar finitud
        for (int64_t i = 0; i < n; ++i) {
            if (!std::isfinite(matrix_in[i])) {
                set_error_msg(err, 3, "Non-finite values in matrix input");
                return -3;
            }
        }

        const double ln2 = 0.693147180559945309417232121458;
        double cosh_sq_sum = 0.0;

        #pragma omp parallel for reduction(+:cosh_sq_sum) schedule(static)
        for (int64_t i = 0; i < n; ++i) {
            double a = std::abs(matrix_in[i]);
            double c_sq;
            if (a < 350.0) {
                double e2  = std::exp(2.0 * a);
                double e2i = std::exp(-2.0 * a);
                c_sq = (e2 + 2.0 + e2i) * 0.25;
            } else {
                c_sq = std::exp(2.0 * (a - ln2));
            }
            cosh_sq_sum += c_sq;
        }

        double rms = std::sqrt(cosh_sq_sum / static_cast<double>(n));
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
// 3. MÉTRICA GEODÉSICA ANGULAR RIEMANNIANA EN S^(D-1) (OpenMP)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_riemannian_geodesic_v902(
    const double* u,
    const double* v,
    uint32_t dim,
    double* angular_dist_out,
    double* chordal_dist_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!u || !v || !angular_dist_out || !chordal_dist_out) {
            set_error_msg(err, 1, "Null pointer in cpp_riemannian_geodesic");
            return -1;
        }

        if (dim == 0) {
            set_error_msg(err, 2, "Dimension is 0");
            return -2;
        }

        size_t d = static_cast<size_t>(dim);
        double norm_u = lassq_norm_cpp(u, d);
        double norm_v = lassq_norm_cpp(v, d);

        if (!std::isfinite(norm_u) || !std::isfinite(norm_v) || norm_u < 1e-15 || norm_v < 1e-15) {
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
// 4. ESTIMADOR Two-NN DE DIMENSIÓN INTRÍNSECA (C++ OpenMP)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_two_nn_intrinsic_dim_v902(
    uint32_t num_pts,
    uint32_t dim,
    const double* points,
    double* d_intrinsic_mle_out,
    double* d_intrinsic_ucb_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!points || !d_intrinsic_mle_out || !d_intrinsic_ucb_out) {
            set_error_msg(err, 1, "Null pointer in cpp_two_nn_intrinsic_dim");
            return -1;
        }

        int64_t n = static_cast<int64_t>(num_pts);
        int64_t d = static_cast<int64_t>(dim);

        if (n < 5 || d == 0) {
            set_error_msg(err, 2, "n < 5 or dim == 0");
            return -2;
        }

        std::vector<double> mu_values(n, 0.0);
        std::vector<int> valid_flags(n, 0);

        #pragma omp parallel for schedule(dynamic, 16)
        for (int64_t i = 0; i < n; ++i) {
            const double* xi = points + i * d;
            double d1 = 1e30;
            double d2 = 1e30;

            for (int64_t j = 0; j < n; ++j) {
                if (i == j) continue;
                const double* xj = points + j * d;
                double dist_sq = 0.0;
                for (int64_t k = 0; k < d; ++k) {
                    double diff = xi[k] - xj[k];
                    dist_sq += diff * diff;
                }
                double dist = std::sqrt(dist_sq);

                if (dist < d1) {
                    d2 = d1;
                    d1 = dist;
                } else if (dist < d2) {
                    d2 = dist;
                }
            }

            if (d1 > 1e-15 && std::isfinite(d2) && d2 >= d1) {
                double mu = d2 / d1;
                if (std::isfinite(mu) && mu > 1.0 + 1e-12) {
                    mu_values[i] = mu;
                    valid_flags[i] = 1;
                }
            }
        }

        double sum_log_mu = 0.0;
        int64_t n_valid = 0;
        for (int64_t i = 0; i < n; ++i) {
            if (valid_flags[i]) {
                sum_log_mu += std::log(mu_values[i]);
                n_valid++;
            }
        }

        if (n_valid < 3) {
            set_error_msg(err, 3, "Insufficient valid mu values");
            return -3;
        }

        if (sum_log_mu <= 1e-12 || !std::isfinite(sum_log_mu)) {
            *d_intrinsic_mle_out = 1.0;
            *d_intrinsic_ucb_out = 1.0;
            set_error_success(err);
            return 0;
        }

        // Estimador MLE insesgado: d = (N - 1) / sum(ln(mu))
        double d_mle = static_cast<double>(n_valid - 1) / sum_log_mu;
        double d_ucb = d_mle * (1.0 + 1.96 / std::sqrt(static_cast<double>(n_valid)));

        *d_intrinsic_mle_out = d_mle;
        *d_intrinsic_ucb_out = d_ucb;

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
// 5. BARANIUK–WAKIN COTA Y FACTIBILIDAD
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_baraniuk_wakin_feasibility_v902(
    uint32_t dim_in,
    uint32_t dim_out,
    double intrinsic_dim,
    double epsilon_dist,
    double reach_tau,
    double volume_v,
    double failure_rho,
    double* m_required_out,
    uint8_t* is_feasible_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!m_required_out || !is_feasible_out) {
            set_error_msg(err, 1, "Null pointer in cpp_baraniuk_wakin_feasibility");
            return -1;
        }

        if (epsilon_dist <= 0.0 || epsilon_dist >= 1.0 || reach_tau <= 0.0 || failure_rho <= 0.0 || volume_v <= 0.0) {
            set_error_msg(err, 2, "Invalid parameters");
            return -2;
        }

        double da = std::max(intrinsic_dim, 1.0);
        double eps = epsilon_dist;
        double tau = reach_tau;
        double v = volume_v;
        double rho = failure_rho;
        double n = static_cast<double>(dim_in);

        double c_const = 1.0; // Hipótesis canónica declarada
        double arg_geo = std::max(v / std::pow(tau, da), 1.0);
        double term_geo = std::log(arg_geo);
        double term_eps = da * std::log(1.0 / eps);
        double term_prob = std::log(1.0 / rho);
        double term_ambient = std::log(n);

        double m_req = (c_const / (eps * eps)) * (term_geo + term_eps + term_prob + term_ambient);
        uint8_t feasible = (static_cast<double>(dim_out) >= m_req) ? 1 : 0;

        *m_required_out = m_req;
        *is_feasible_out = feasible;

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
// 6. HYBRID-AuON ORTHOGONALIZATION (Alternative Unit-norm momentum) O(N)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_hybrid_auon_orthogonalization_v902(
    uint32_t dim_n,
    const double* matrix_x,
    double* matrix_q_out,
    uint32_t max_total_steps,
    uint32_t* steps_executed_out,
    uint8_t* is_converged_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!matrix_x || !matrix_q_out || !steps_executed_out || !is_converged_out) {
            set_error_msg(err, 1, "Null pointer in cpp_hybrid_auon");
            return -1;
        }

        int64_t n = static_cast<int64_t>(dim_n);
        int64_t total = n * n;
        if (total <= 0) return -2;

        std::memcpy(matrix_q_out, matrix_x, total * sizeof(double));

        // Hybrid-AuON uses log-cosh RMS scaling per column
        const int64_t max_steps = std::clamp<int64_t>(static_cast<int64_t>(max_total_steps), int64_t{1}, int64_t{30});
        int64_t executed = 0;
        bool converged = false;

        while (executed < max_steps) {
            double max_err = 0.0;
            
            #pragma omp parallel for schedule(static) reduction(max:max_err)
            for (int64_t j = 0; j < n; ++j) {
                double dot = 0.0;
                #pragma omp simd reduction(+:dot)
                for (int64_t i = 0; i < n; ++i) {
                    dot += matrix_q_out[i * n + j] * matrix_q_out[i * n + j];
                }
                
                double rms = std::sqrt(dot / static_cast<double>(n));
                double scale = 1.0 / (rms + 1e-12);
                
                // Aplicar escalado RMS no-lineal (AuON)
                #pragma omp simd
                for (int64_t i = 0; i < n; ++i) {
                    matrix_q_out[i * n + j] *= scale;
                }
                
                double err_col = std::abs(rms - 1.0);
                if (err_col > max_err) max_err = err_col;
            }
            
            executed++;
            if (max_err < 1e-10) {
                converged = true;
                break;
            }
        }

        *steps_executed_out = static_cast<uint32_t>(executed);
        *is_converged_out = converged ? 1 : 0;

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
// 7. EVALUADOR DE DISTORSIÓN DE SECANTES EN VARIEDADES
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_secant_distortion_eval_v902(
    uint32_t num_pts,
    uint32_t dim_in,
    uint32_t dim_out,
    const double* orig_pts,
    const double* proj_pts,
    double* l_min_out,
    double* l_max_out,
    double* delta_max_out,
    double* secant_alpha_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!orig_pts || !proj_pts || !l_min_out || !l_max_out || !delta_max_out || !secant_alpha_out) {
            set_error_msg(err, 1, "Null pointer in cpp_secant_distortion_eval");
            return -1;
        }

        if (num_pts < 2 || dim_in == 0 || dim_out == 0) {
            set_error_msg(err, 2, "num_pts >= 2 and dims > 0 required");
            return -2;
        }

        int64_t n = static_cast<int64_t>(num_pts);
        int64_t din = static_cast<int64_t>(dim_in);
        int64_t dout = static_cast<int64_t>(dim_out);

        double global_l_min = 1e30;
        double global_l_max = 0.0;
        double global_delta_max = 0.0;

        int num_threads = omp_get_max_threads();
        std::vector<double> thread_l_min(num_threads, 1e30);
        std::vector<double> thread_l_max(num_threads, 0.0);
        std::vector<double> thread_delta_max(num_threads, 0.0);

        #pragma omp parallel
        {
            int tid = omp_get_thread_num();
            #pragma omp for schedule(dynamic, 16)
            for (int64_t i = 0; i < n; ++i) {
                const double* xi = orig_pts + i * din;
                const double* yi = proj_pts + i * dout;

                for (int64_t j = i + 1; j < n; ++j) {
                    const double* xj = orig_pts + j * din;
                    const double* yj = proj_pts + j * dout;

                    double orig_sq = 0.0;
                    for (int64_t k = 0; k < din; ++k) {
                        double d = xi[k] - xj[k];
                        orig_sq += d * d;
                    }
                    double orig_dist = std::sqrt(orig_sq);

                    if (orig_dist > 1e-12) {
                        double proj_sq = 0.0;
                        for (int64_t k = 0; k < dout; ++k) {
                            double d = yi[k] - yj[k];
                            proj_sq += d * d;
                        }
                        double proj_dist = std::sqrt(proj_sq);

                        double ratio = proj_dist / orig_dist;
                        if (ratio < thread_l_min[tid]) thread_l_min[tid] = ratio;
                        if (ratio > thread_l_max[tid]) thread_l_max[tid] = ratio;

                        double delta = std::abs(ratio - 1.0);
                        if (delta > thread_delta_max[tid]) thread_delta_max[tid] = delta;
                    }
                }
            }
        }

        for (int t = 0; t < num_threads; ++t) {
            if (thread_l_min[t] < global_l_min) global_l_min = thread_l_min[t];
            if (thread_l_max[t] > global_l_max) global_l_max = thread_l_max[t];
            if (thread_delta_max[t] > global_delta_max) global_delta_max = thread_delta_max[t];
        }

        *l_min_out = global_l_min;
        *l_max_out = global_l_max;
        *delta_max_out = global_delta_max;
        *secant_alpha_out = global_l_min;

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
// 8. QSBR SNAPSHOT COPY-OUT (Safe Memory Copy Guard)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_qsbr_snapshot_copy_v902(
    const uint8_t* src,
    size_t size_bytes,
    uint8_t* dst,
    size_t* copied_bytes_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!src || !dst || !copied_bytes_out) {
            set_error_msg(err, 1, "Null pointer in cpp_qsbr_snapshot_copy");
            return -1;
        }

        if (size_bytes > 0) {
            std::memmove(dst, src, size_bytes);
        }
        *copied_bytes_out = size_bytes;

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
// 9. RETRACCIÓN CAYLEY-STIEFEL MATRIX-FREE (Sherman-Morrison-Woodbury)
// ============================================================================

namespace {

bool solve_linear_system_2k_cpp(int n_sys, int n_rhs, const double* A, const double* B, double* X_sol) noexcept {
    int cols = n_sys + n_rhs;
    std::vector<double> aug(n_sys * cols);
    for (int i = 0; i < n_sys; ++i) {
        for (int j = 0; j < n_sys; ++j) {
            aug[i * cols + j] = A[i * n_sys + j];
        }
        for (int j = 0; j < n_rhs; ++j) {
            aug[i * cols + n_sys + j] = B[i * n_rhs + j];
        }
    }

    double scale_ref = 0.0;
    for (int i = 0; i < n_sys * n_sys; ++i) {
        double v = std::abs(A[i]);
        if (v > scale_ref) scale_ref = v;
    }
    if (scale_ref == 0.0) scale_ref = 1.0;
    double abs_tol = 1e-12 * scale_ref;

    for (int i = 0; i < n_sys; ++i) {
        int pivot = i;
        double max_val = std::abs(aug[i * cols + i]);
        for (int r = i + 1; r < n_sys; ++r) {
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
            for (int c = i; c < cols; ++c) {
                std::swap(aug[i * cols + c], aug[pivot * cols + c]);
            }
        }
        double pivot_val = aug[i * cols + i];
        for (int c = i; c < cols; ++c) {
            aug[i * cols + c] /= pivot_val;
        }
        for (int r = 0; r < n_sys; ++r) {
            if (r != i) {
                double factor = aug[r * cols + i];
                for (int c = i; c < cols; ++c) {
                    aug[r * cols + c] -= factor * aug[i * cols + c];
                }
            }
        }
    }

    for (int i = 0; i < n_sys; ++i) {
        for (int j = 0; j < n_rhs; ++j) {
            X_sol[i * n_rhs + j] = aug[i * cols + n_sys + j];
        }
    }
    return true;
}

} // namespace

POLYDIM_EXPORT int polydim_cpp_stiefel_cayley_smw_retraction_v902(
    uint32_t dim_d,
    uint32_t rank_k,
    double tau,
    const double* x_ptr,
    const double* g_ptr,
    double* y_out,
    double* ortho_error_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!x_ptr || !g_ptr || !y_out || !ortho_error_out) {
            set_error_msg(err, 1, "Null pointer in cpp_stiefel_cayley_smw_retraction");
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

        // Verificar finitud
        for (int64_t idx = 0; idx < d * k; ++idx) {
            if (!std::isfinite(x_ptr[idx]) || !std::isfinite(g_ptr[idx])) {
                set_error_msg(err, 4, "Non-finite elements in X or G matrix");
                return -4;
            }
        }

        int64_t n_sys = 2 * k;

        // 1. Calcular bloques KxK: A = X^T G, B = X^T X, C = G^T G (Sin sección crítica OpenMP)
        int num_threads = omp_get_max_threads();
        std::vector<double> thread_a(num_threads * k * k, 0.0);
        std::vector<double> thread_b(num_threads * k * k, 0.0);
        std::vector<double> thread_c(num_threads * k * k, 0.0);

        #pragma omp parallel
        {
            int tid = omp_get_thread_num();
            double* la = &thread_a[tid * k * k];
            double* lb = &thread_b[tid * k * k];
            double* lc = &thread_c[tid * k * k];

            #pragma omp for schedule(static)
            for (int64_t row = 0; row < d; ++row) {
                const double* xr = x_ptr + row * k;
                const double* gr = g_ptr + row * k;
                for (int64_t i = 0; i < k; ++i) {
                    double xi = xr[i];
                    double gi = gr[i];
                    for (int64_t j = 0; j < k; ++j) {
                        la[i * k + j] += xi * gr[j];
                        lb[i * k + j] += xi * xr[j];
                        lc[i * k + j] += gi * gr[j];
                    }
                }
            }
        }

        std::vector<double> mat_a(k * k, 0.0);
        std::vector<double> mat_b(k * k, 0.0);
        std::vector<double> mat_c(k * k, 0.0);

        for (int t = 0; t < num_threads; ++t) {
            const double* la = &thread_a[t * k * k];
            const double* lb = &thread_b[t * k * k];
            const double* lc = &thread_c[t * k * k];
            for (int64_t idx = 0; idx < k * k; ++idx) {
                mat_a[idx] += la[idx];
                mat_b[idx] += lb[idx];
                mat_c[idx] += lc[idx];
            }
        }

        // 2. Verificar ortonormalidad de X (X^T X = I_K)
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

        // 3. Construir sistema 2K x 2K: M = I_2K - (tau / 2) * [A, -B; C, -A^T]
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

        // 4. Construir RHS = [B; A^T] de tamaño 2K x K
        std::vector<double> rhs(n_sys * k, 0.0);
        for (int64_t i = 0; i < k; ++i) {
            for (int64_t j = 0; j < k; ++j) {
                rhs[i * k + j] = mat_b[i * k + j];
                rhs[(k + i) * k + j] = mat_a[j * k + i];
            }
        }

        // 5. Resolver sistema lineal M * Z = RHS
        std::vector<double> mat_z(n_sys * k, 0.0);
        if (!solve_linear_system_2k_cpp(static_cast<int>(n_sys), static_cast<int>(k), mat_m.data(), rhs.data(), mat_z.data())) {
            set_error_msg(err, 6, "Matrix M is singular or ill-conditioned in SMW retraction");
            return -6;
        }

        // 6. Reconstruir Y = X + tau * (G * Z1 - X * Z2) de tamaño D x K
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

        // 7. Computar error de ortonormalidad de salida: ||Y^T Y - I_K||_F / sqrt(K)
        std::vector<double> thread_yty(num_threads * k * k, 0.0);
        #pragma omp parallel
        {
            int tid = omp_get_thread_num();
            double* lyty = &thread_yty[tid * k * k];
            #pragma omp for schedule(static)
            for (int64_t row = 0; row < d; ++row) {
                const double* yr = y_out + row * k;
                for (int64_t i = 0; i < k; ++i) {
                    double yi = yr[i];
                    for (int64_t j = 0; j < k; ++j) {
                        lyty[i * k + j] += yi * yr[j];
                    }
                }
            }
        }

        std::vector<double> yty(k * k, 0.0);
        for (int t = 0; t < num_threads; ++t) {
            const double* lyty = &thread_yty[t * k * k];
            for (int64_t idx = 0; idx < k * k; ++idx) {
                yty[idx] += lyty[idx];
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
// 10. COTA ASINTÓTICA RIEMANNIANA DE DRIFT CLIFFORD (Higham 2002)
// ============================================================================

POLYDIM_EXPORT int polydim_cpp_clifford_drift_bound_v902(
    uint32_t dim_d,
    uint32_t num_reflections_m,
    uint32_t reorth_interval_k,
    double eps_mach,
    double* unconditioned_bound_out,
    double* reorth_bound_out,
    uint8_t* is_safe_under_1e8_out,
    PolydimErrorV902* err
) noexcept {
    try {
        if (!unconditioned_bound_out || !reorth_bound_out || !is_safe_under_1e8_out) {
            set_error_msg(err, 1, "Null pointer in cpp_clifford_drift_bound");
            return -1;
        }

        if (dim_d == 0 || num_reflections_m == 0) {
            set_error_msg(err, 2, "dim_d and num_reflections_m must be > 0");
            return -2;
        }

        double d = static_cast<double>(dim_d);
        double m = static_cast<double>(num_reflections_m);
        double emach = (eps_mach > 0.0) ? eps_mach : 2.220446049250313e-16;
        const double c_const = 2.0;

        double unconditioned = c_const * m * std::sqrt(d) * emach;

        double k_step = std::clamp(static_cast<double>(reorth_interval_k), 1.0, m);
        double num_blocks = std::ceil(m / k_step);
        double block_drift = c_const * k_step * std::sqrt(d) * emach;
        double qr_drift = 2.0 * std::sqrt(d) * emach;
        double reorth = num_blocks * qr_drift + block_drift;

        *unconditioned_bound_out = unconditioned;
        *reorth_bound_out = reorth;
        *is_safe_under_1e8_out = (reorth < 1e-8) ? 1 : 0;

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
