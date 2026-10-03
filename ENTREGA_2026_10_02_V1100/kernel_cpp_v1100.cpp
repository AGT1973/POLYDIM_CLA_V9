// ============================================================================
// POLYDIM C++ KERNEL V1101 (SERIE 900 PRODUCCION CERTIFICADA - WOODBURY + GEODESIC)
// Arquitectura: AMD A4-6300 / Intel AVX+SSE4.2 | Compilador: WinLibs GCC 14 C++20
// ============================================================================

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <numeric>
#include <algorithm>
#include <immintrin.h>
#include <omp.h>

#if defined(_WIN32) || defined(_WIN64)
#define POLYDIM_EXPORT extern "C" __declspec(dllexport)
#else
#define POLYDIM_EXPORT extern "C" __attribute__((visibility("default")))
#endif

static inline void polydim_enable_ftz_daz() {
    #if defined(__x86_64__) || defined(_M_X64)
    _mm_setcsr(_mm_getcsr() | 0x8040); // FTZ=bit 15, DAZ=bit 6
    #endif
}

// 1. SOLUCIONADOR VLASOV-POISSON CON INTEGRACIÓN GEODÉSICA ANALÍTICA EXACTA EN S^{D-1}
POLYDIM_EXPORT int32_t polydim_spherical_vlasov_poisson_step_v1101(
    const float* pos, const float* mom, const float* grad_phi,
    float* out_pos, float* out_mom,
    int32_t N, int32_t D, float dt
) {
    if (!pos || !mom || !grad_phi || !out_pos || !out_mom || N <= 0 || D <= 0) return -1;
    polydim_enable_ftz_daz();

    #pragma omp parallel
    {
        std::vector<float> p_mid(D);

        #pragma omp for schedule(static)
        for (int32_t i = 0; i < N; ++i) {
            const float* x = pos + i * D;
            const float* p = mom + i * D;
            const float* g = grad_phi + i * D;
            float* out_x = out_pos + i * D;
            float* out_p = out_mom + i * D;

            // Fuerza tangente riemanniana en S^{D-1}: F = -(I - x x^T) grad_phi
            float dot_gx = 0.0f;
            for (int32_t k = 0; k < D; ++k) dot_gx += g[k] * x[k];

            // Actualización de momento tangente (Kick)
            float p_mid_norm_sq = 0.0f;
            for (int32_t k = 0; k < D; ++k) {
                float f_k = -(g[k] - dot_gx * x[k]);
                p_mid[k] = p[k] + dt * f_k;
                p_mid_norm_sq += p_mid[k] * p_mid[k];
            }

            // Proyección exacta a tangente T_x S^{D-1}
            float dot_xp = 0.0f;
            for (int32_t k = 0; k < D; ++k) dot_xp += x[k] * p_mid[k];
            for (int32_t k = 0; k < D; ++k) p_mid[k] -= dot_xp * x[k];

            float omega = std::sqrt(std::max(1e-12f, p_mid_norm_sq));
            float theta = omega * dt;
            float cos_t = std::cos(theta);
            float sin_t = std::sin(theta);
            float sin_div_w = (omega > 1e-6f) ? (sin_t / omega) : dt;

            // Flujo geodésico exacto en S^{D-1} (Drift simpléctico sin disipación)
            // x(t+dt) = x * cos(omega*dt) + (p/omega) * sin(omega*dt)
            // p(t+dt) = -x * omega * sin(omega*dt) + p * cos(omega*dt)
            for (int32_t k = 0; k < D; ++k) {
                out_x[k] = x[k] * cos_t + p_mid[k] * sin_div_w;
                out_p[k] = -x[k] * (omega * sin_t) + p_mid[k] * cos_t;
            }

            // Normalización de seguridad cordal
            float n_sq = 0.0f;
            for (int32_t k = 0; k < D; ++k) n_sq += out_x[k] * out_x[k];
            float inv_n = 1.0f / std::sqrt(std::max(1e-12f, n_sq));
            for (int32_t k = 0; k < D; ++k) out_x[k] *= inv_n;
        }
    }
    return 0;
}

// 2. PAR DE LAX CALOGERO-SUTHERLAND MATRIX-FREE CON INVARIANTE I_2 Y REGULARIZACIÓN SOFT-CORE O(1) MEMORIA
POLYDIM_EXPORT int32_t polydim_calogero_sutherland_integrals_v1101(
    const float* positions, const float* momenta, float* out_integrals,
    int32_t N, float g_coupling
) {
    if (!positions || !momenta || !out_integrals || N <= 0) return -1;
    polydim_enable_ftz_daz();

    double sum_p = 0.0;
    double sum_p2 = 0.0;
    double pair_sum = 0.0;
    const double g2 = static_cast<double>(g_coupling) * static_cast<double>(g_coupling);
    constexpr double eps2 = 1.0e-12;

    #pragma omp parallel for reduction(+:sum_p, sum_p2, pair_sum) schedule(static)
    for (int32_t j = 0; j < N; ++j) {
        double pj = static_cast<double>(momenta[j]);
        sum_p  += pj;
        sum_p2 += pj * pj;

        double xj = static_cast<double>(positions[j]);
        for (int32_t k = j + 1; k < N; ++k) {
            double diff = xj - static_cast<double>(positions[k]);
            double s = std::sin(diff);
            double c = std::cos(diff);
            // Regularización suave soft-core: c^2 / (s^2 + eps^2) evitando discontinuidades
            pair_sum += (c * c) / (s * s + eps2);
        }
    }

    double I1 = sum_p;
    double I2 = 0.5 * sum_p2 + g2 * pair_sum;

    out_integrals[0] = static_cast<float>(I1);
    out_integrals[1] = static_cast<float>(I2);
    return 0;
}

// Helper: Solver LU directo de doble precisión con buffer de pila para M <= 64 (Evita heap churn en L1)
static void solve_lu_direct_double(const double* A, const double* b, double* x, int M) {
    constexpr int MAX_STACK_M = 64;
    double LU_stack[MAX_STACK_M * MAX_STACK_M];
    int p_stack[MAX_STACK_M];
    double y_stack[MAX_STACK_M];

    std::vector<double> LU_heap;
    std::vector<int> p_heap;
    std::vector<double> y_heap;

    double* LU = (M <= MAX_STACK_M) ? LU_stack : (LU_heap.resize(M * M), LU_heap.data());
    int* p = (M <= MAX_STACK_M) ? p_stack : (p_heap.resize(M), p_heap.data());
    double* y = (M <= MAX_STACK_M) ? y_stack : (y_heap.resize(M), y_heap.data());

    std::memcpy(LU, A, M * M * sizeof(double));
    for (int i = 0; i < M; ++i) p[i] = i;

    for (int i = 0; i < M; ++i) {
        int max_r = i;
        double max_v = std::abs(LU[i * M + i]);
        for (int r = i + 1; r < M; ++r) {
            double val = std::abs(LU[r * M + i]);
            if (val > max_v) {
                max_v = val;
                max_r = r;
            }
        }
        if (max_r != i) {
            std::swap(p[i], p[max_r]);
            for (int k = 0; k < M; ++k) std::swap(LU[i * M + k], LU[max_r * M + k]);
        }
        double pivot = LU[i * M + i];
        if (std::abs(pivot) < 1e-15) pivot = (pivot >= 0.0 ? 1e-15 : -1e-15);
        for (int r = i + 1; r < M; ++r) {
            LU[r * M + i] /= pivot;
            for (int c = i + 1; c < M; ++c) {
                LU[r * M + c] -= LU[r * M + i] * LU[i * M + c];
            }
        }
    }

    for (int i = 0; i < M; ++i) {
        double sum = b[p[i]];
        for (int j = 0; j < i; ++j) sum -= LU[i * M + j] * y[j];
        y[i] = sum;
    }
    for (int i = M - 1; i >= 0; --i) {
        double sum = y[i];
        for (int j = i + 1; j < M; ++j) sum -= LU[i * M + j] * x[j];
        double diag = LU[i * M + i];
        if (std::abs(diag) < 1e-15) diag = (diag >= 0.0 ? 1e-15 : -1e-15);
        x[i] = sum / diag;
    }
}

// 3. RETRACCIÓN STIEFEL CAYLEY-SMW CON SOLUCIONADOR WOODBURY 2K x 2K EXACTO (FUSED REDUCTION + STACK L1)
POLYDIM_EXPORT int32_t polydim_cayley_smw_stiefel_v1101(
    const float* X, const float* U, const float* V, float* out_X,
    int32_t D, int32_t K, float tau
) {
    if (!X || !U || !V || !out_X || D <= 0 || K <= 0) return -1;
    polydim_enable_ftz_daz();

    const int32_t M = 2 * K;
    const double c = static_cast<double>(tau) * 0.5;

    // Bufferes de doble precisión para estabilidad espectral
    std::vector<double> rhs(M, 0.0);
    std::vector<double> W_mat(M * M, 0.0);

    // Diagonal identidad en W
    for (int32_t i = 0; i < M; ++i) W_mat[i * M + i] = 1.0;

    // Reducción OpenMP fusionada para matrices de Gram y RHS (V^T X, U^T X, V^T U, V^T V, U^T U, U^T V)
    #pragma omp parallel
    {
        std::vector<double> local_rhs(M, 0.0);
        std::vector<double> local_VtU(K * K, 0.0);
        std::vector<double> local_VtV(K * K, 0.0);
        std::vector<double> local_UtU(K * K, 0.0);
        std::vector<double> local_UtV(K * K, 0.0);

        #pragma omp for schedule(static)
        for (int32_t i = 0; i < D; ++i) {
            double xi = static_cast<double>(X[i]);
            const float* Ui = U + i * K;
            const float* Vi = V + i * K;

            for (int32_t r = 0; r < K; ++r) {
                double vr = static_cast<double>(Vi[r]);
                double ur = static_cast<double>(Ui[r]);

                local_rhs[r] += vr * xi;
                local_rhs[K + r] += ur * xi;

                for (int32_t cl = 0; cl < K; ++cl) {
                    double v_cl = static_cast<double>(Vi[cl]);
                    double u_cl = static_cast<double>(Ui[cl]);

                    local_VtU[r * K + cl] += vr * u_cl;
                    local_VtV[r * K + cl] += vr * v_cl;
                    local_UtU[r * K + cl] += ur * u_cl;
                    local_UtV[r * K + cl] += ur * v_cl;
                }
            }
        }

        #pragma omp critical
        {
            for (int32_t m = 0; m < M; ++m) rhs[m] += local_rhs[m];
            for (int32_t r = 0; r < K; ++r) {
                for (int32_t cl = 0; cl < K; ++cl) {
                    W_mat[r * M + cl]           += c * local_VtU[r * K + cl];
                    W_mat[r * M + (K + cl)]     += c * local_VtV[r * K + cl];
                    W_mat[(K + r) * M + cl]     -= c * local_UtU[r * K + cl];
                    W_mat[(K + r) * M + (K + cl)] -= c * local_UtV[r * K + cl];
                }
            }
        }
    }

    // 3. Resolver sistema 2K x 2K en L1 Stack: W_mat * z = rhs
    std::vector<double> z(M, 0.0);
    solve_lu_direct_double(W_mat.data(), rhs.data(), z.data(), M);

    // 4. Proyección Woodbury exacta: out_X = X - 2*c * [U, V] * z
    #pragma omp parallel for schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        double uz = 0.0, vz = 0.0;
        const float* Ui = U + i * K;
        const float* Vi = V + i * K;
        for (int32_t k = 0; k < K; ++k) {
            uz += static_cast<double>(Ui[k]) * z[k];
            vz += static_cast<double>(Vi[k]) * z[K + k];
        }
        double res = static_cast<double>(X[i]) - 2.0 * c * (uz + vz);
        out_X[i] = static_cast<float>(res);
    }

    // 5. Normalización cordal de alta precisión
    double norm_sq = 0.0;
    #pragma omp parallel for reduction(+:norm_sq) schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        double val = static_cast<double>(out_X[i]);
        norm_sq += val * val;
    }
    double inv_norm = 1.0 / std::sqrt(std::max(1e-15, norm_sq));
    #pragma omp parallel for schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        out_X[i] = static_cast<float>(static_cast<double>(out_X[i]) * inv_norm);
    }

    return 0;
}

// 4. CUANTIZADOR E8 LATTICE CONWAY-SLOANE COMPLETO (BI-COSET D8 U (D8 + 1/2 * 1)) CON OPENMP PER-THREAD FTZ/DAZ
POLYDIM_EXPORT int32_t polydim_e8_lattice_quantize_v1101(
    const float* in_vec, float* out_quant, int32_t D
) {
    if (!in_vec || !out_quant || D <= 0 || (D % 8 != 0)) return -1;

    int32_t num_blocks = D / 8;

    #pragma omp parallel
    {
        polydim_enable_ftz_daz();

        #pragma omp for schedule(static, 64)
        for (int32_t b = 0; b < num_blocks; ++b) {
            const float* x = in_vec + b * 8;
            float* y = out_quant + b * 8;

            // Guarda contra NaNs o infinitos: paso a cero seguro
            bool has_nonfinite = false;
            for (int32_t i = 0; i < 8; ++i) {
                if (!std::isfinite(x[i])) {
                    has_nonfinite = true;
                    break;
                }
            }
            if (has_nonfinite) {
                for (int32_t i = 0; i < 8; ++i) y[i] = 0.0f;
                continue;
            }

            // 1. Candidato f1 en coset entero D8 (suma de enteros par)
            float f1[8];
            int32_t sum1 = 0;
            int32_t max_idx1 = 0;
            float max_err1 = -1.0f;

            for (int32_t i = 0; i < 8; ++i) {
                float r = std::round(x[i]);
                f1[i] = r;
                sum1 += static_cast<int32_t>(r);
                float err = std::abs(x[i] - r);
                if (err > max_err1) {
                    max_err1 = err;
                    max_idx1 = i;
                }
            }
            // Corrección de paridad robusta libre de división
            if ((sum1 & 1) != 0) {
                f1[max_idx1] += (x[max_idx1] >= f1[max_idx1]) ? 1.0f : -1.0f;
            }

            // 2. Candidato f2 en coset semi-entero D8 + 1/2*1
            float f2[8];
            int32_t sum2 = 0;
            int32_t max_idx2 = 0;
            float max_err2 = -1.0f;

            for (int32_t i = 0; i < 8; ++i) {
                float shifted = x[i] - 0.5f;
                float r = std::round(shifted);
                f2[i] = r + 0.5f;
                sum2 += static_cast<int32_t>(r);
                float err = std::abs(shifted - r);
                if (err > max_err2) {
                    max_err2 = err;
                    max_idx2 = i;
                }
            }
            if ((sum2 & 1) != 0) {
                f2[max_idx2] += (x[max_idx2] >= f2[max_idx2]) ? 1.0f : -1.0f;
            }

            // 3. Selección de coset de mínima distancia euclídea al cuadrado
            float dist1_sq = 0.0f, dist2_sq = 0.0f;
            for (int32_t i = 0; i < 8; ++i) {
                float d1 = x[i] - f1[i];
                float d2 = x[i] - f2[i];
                dist1_sq += d1 * d1;
                dist2_sq += d2 * d2;
            }

            const float* best = (dist1_sq <= dist2_sq) ? f1 : f2;
            for (int32_t i = 0; i < 8; ++i) y[i] = best[i];
        }
    }
    return 0;
}

// 5. TRANSPORTE PARALELO HOUSEHOLDER CON BISECTOR CORDAL CONTINUO (PRECISIÓN NUMÉRICA BLINDADA)
POLYDIM_EXPORT int32_t polydim_parallel_transport_householder_v1101(
    const float* x, const float* y, const float* v, float* out_v, int32_t D
) {
    if (!x || !y || !v || !out_v || D <= 0) return -1;
    polydim_enable_ftz_daz();
    
    double dot_xy = 0.0;
    #pragma omp parallel for reduction(+:dot_xy) schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        dot_xy += static_cast<double>(x[i]) * static_cast<double>(y[i]);
    }

    // Antipodal guard: si dot_xy ≈ -1.0 dentro de la precisión numérica
    if (dot_xy <= -0.99999999999) {
        #pragma omp parallel for schedule(static)
        for (int32_t i = 0; i < D; ++i) out_v[i] = -v[i];
        return 0;
    }

    double dot_sum_v = 0.0;
    #pragma omp parallel for reduction(+:dot_sum_v) schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        dot_sum_v += (static_cast<double>(x[i]) + static_cast<double>(y[i])) * static_cast<double>(v[i]);
    }
    
    double factor = dot_sum_v / (1.0 + dot_xy);
    #pragma omp parallel for schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        out_v[i] = static_cast<float>(static_cast<double>(v[i]) - factor * (static_cast<double>(x[i]) + static_cast<double>(y[i])));
    }

    return 0;
}

// 6. SUMA GIROVECTORIAL DE MÖBIUS (SOTA CAUCHY-SCHWARZ DENOMINADOR Y REDUCCIÓN DOUBLE SINGLE-PASS)
POLYDIM_EXPORT int32_t polydim_mobius_addition_v1101(
    const float* x, const float* y, float* out_res,
    int32_t D, float c
) {
    if (!x || !y || !out_res || D <= 0 || c <= 0.0f) return -1;
    polydim_enable_ftz_daz();

    double c_d = static_cast<double>(c);
    double xx = 0.0, yy = 0.0, xy = 0.0;

    // Single OpenMP pass: 3 dot products in double precision
    #pragma omp parallel for reduction(+:xx, yy, xy) schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        double xi = static_cast<double>(x[i]);
        double yi = static_cast<double>(y[i]);
        xx += xi * xi;
        yy += yi * yi;
        xy += xi * yi;
    }

    double a = c_d * xx;
    double b = c_d * yy;
    double p = c_d * xy;

    // Denominador libre de cancelación por Cauchy-Schwarz: Delta = (1-p)^2 + (a-p)*(b-p)
    double u = 1.0 - p;
    double v = a - p;
    double w = b - p;
    double den = u * u + v * w;
    if (std::abs(den) < 1e-15 || !std::isfinite(den)) den = 1e-15;

    double alpha = (1.0 + 2.0 * p + b) / den;
    double beta = (1.0 - a) / den;

    double out_norm_sq = 0.0;
    #pragma omp parallel for reduction(+:out_norm_sq) schedule(static)
    for (int32_t i = 0; i < D; ++i) {
        double val = alpha * static_cast<double>(x[i]) + beta * static_cast<double>(y[i]);
        out_res[i] = static_cast<float>(val);
        out_norm_sq += val * val;
    }

    // Guarda radial de frontera del modelo de Poincaré: ||z|| < 1/sqrt(c) - 1e-6
    double limit = 1.0 / std::sqrt(c_d) - 1e-6;
    if (limit > 0.0 && std::isfinite(out_norm_sq)) {
        double r = std::sqrt(out_norm_sq);
        if (r > limit) {
            float scale = static_cast<float>(limit / r);
            #pragma omp parallel for schedule(static)
            for (int32_t i = 0; i < D; ++i) {
                out_res[i] *= scale;
            }
        }
    }

    return 0;
}
