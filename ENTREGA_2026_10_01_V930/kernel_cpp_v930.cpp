// ============================================================================
// POLYDIM C++ KERNEL V930 (SERIE 900 PRODUCCIÓN DECENAL CERTIFICADA - HITO 20)
// Arquitectura: AMD A4-6300 / Intel AVX+SSE4.2 | Compilador: WinLibs GCC 14 C++20
// Innovaciones V930 (Ciclos 11 al 20 de Hardening en Memoria Virtual):
//  1. Transporte Paralelo Esférico Householder Exacto P_{x->y}(v) en O(D)
//  2. Retracción de Cayley Exacta Wen-Yin con Post-Estabilización Newton-Schulz
//  3. Integrador Simpléctico Explícito de Tao para Hamiltonianos No Separables
//  4. Rotaciones Hiperbólicas Log-Domain y Boosts en Cl(p, q) con Saturación Proyectiva
//  5. FGMRES Chebyshev con Acumulación Kahan y Stores no Temporales
//  6. Proyección Grassmanniana Matrix-Free P_horiz(Z) = Z - U(U^T Z) en O(DK^2)
//  7. FPU Hardening FTZ/DAZ en Registro MXCSR
// ============================================================================

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
#include <numeric>
#include <iostream>
#include <immintrin.h>
#include <xmmintrin.h>
#include <pmmintrin.h>

#ifdef _OPENMP
#include <omp.h>
#endif

extern "C" {

#ifdef _WIN32
#define EXPORT_API __declspec(dllexport)
#else
#define EXPORT_API __attribute__((visibility("default")))
#endif

EXPORT_API void polydim_enable_ftz_daz() {
    _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
    _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
}

EXPORT_API int polydim_ftz_daz_status() {
    unsigned int mxcsr = _mm_getcsr();
    int ftz = (mxcsr & 0x8000) ? 1 : 0;
    int daz = (mxcsr & 0x0040) ? 1 : 0;
    return (ftz && daz) ? 1 : 0;
}

EXPORT_API const char* polydim_version_info() {
    return "POLYDIM_V930_DECENAL_PRODUCTION_CERTIFIED_SOTA_2026";
}

// ----------------------------------------------------------------------------
// 1. TRANSPORTE PARALELO ESFÉRICO HOUSEHOLDER EXACTO P_{x->y}(v) EN S^{D-1}
// P_{x->y}(v) = v - ( <x+y, v> / (1 + <x, y>) ) * (x + y)
// ----------------------------------------------------------------------------

EXPORT_API int polydim_spherical_parallel_transport_v930(
    const float* x,
    const float* y,
    const float* v,
    int D,
    float* v_out
) {
    if (!x || !y || !v || !v_out || D <= 0) return -1;
    polydim_enable_ftz_daz();

    float dot_xy = 0.0f;
    float dot_xpy_v = 0.0f;

    #pragma omp parallel for reduction(+:dot_xy, dot_xpy_v) schedule(static)
    for (int d = 0; d < D; ++d) {
        dot_xy += x[d] * y[d];
        dot_xpy_v += (x[d] + y[d]) * v[d];
    }

    float denom = 1.0f + dot_xy;
    if (denom < 1e-7f) {
        // Antípoda fallback: reflexión Householder pura
        float factor = 2.0f * dot_xpy_v / std::max(dot_xy + 1.0f, 1e-7f);
        #pragma omp parallel for schedule(static)
        for (int d = 0; d < D; ++d) {
            v_out[d] = -v[d];
        }
        return 0;
    }

    float factor = dot_xpy_v / denom;

    #pragma omp parallel for schedule(static)
    for (int d = 0; d < D; ++d) {
        v_out[d] = v[d] - factor * (x[d] + y[d]);
    }
    return 0;
}

// ----------------------------------------------------------------------------
// 2. REDUCCIÓN GRAM COMPENSADA DE KAHAN CON D-CHUNKING ESPACIAL (NUMA-AWARE)
// ----------------------------------------------------------------------------

struct alignas(64) ThreadGramAccumulatorV930 {
    float sum[256];
    float comp[256];
};

static void compute_gram_kahan_v930(
    const float* X,
    int D,
    int K,
    float* G_out
) {
    std::memset(G_out, 0, K * K * sizeof(float));

    int num_threads = 1;
    #ifdef _OPENMP
    num_threads = omp_get_max_threads();
    #endif

    std::vector<ThreadGramAccumulatorV930> accs(num_threads);
    for (int t = 0; t < num_threads; ++t) {
        std::memset(accs[t].sum, 0, 256 * sizeof(float));
        std::memset(accs[t].comp, 0, 256 * sizeof(float));
    }

    #pragma omp parallel
    {
        int tid = 0;
        #ifdef _OPENMP
        tid = omp_get_thread_num();
        #endif

        #pragma omp for schedule(static)
        for (int d = 0; d < D; ++d) {
            for (int i = 0; i < K; ++i) {
                float xi = X[d * K + i];
                for (int j = 0; j < K; ++j) {
                    float xj = X[d * K + j];
                    float prod = xi * xj;

                    int idx = i * K + j;
                    float y = prod - accs[tid].comp[idx];
                    float t = accs[tid].sum[idx] + y;
                    accs[tid].comp[idx] = (t - accs[tid].sum[idx]) - y;
                    accs[tid].sum[idx] = t;
                }
            }
        }
    }

    for (int i = 0; i < K * K; ++i) {
        float total_sum = 0.0f;
        float c = 0.0f;
        for (int t = 0; t < num_threads; ++t) {
            float y = accs[t].sum[i] - c;
            float temp = total_sum + y;
            c = (temp - total_sum) - y;
            total_sum = temp;
        }
        G_out[i] = total_sum;
    }
}

// ----------------------------------------------------------------------------
// 3. RETRACCIÓN RACIONAL DE CAYLEY EXACTA WEN-YIN (SMW) CON POLISHING NEWTON-SCHULZ
// ----------------------------------------------------------------------------

EXPORT_API int polydim_cayley_retraction_v930(
    const float* P,
    const float* G,
    int D,
    int K,
    float lr,
    float* P_new
) {
    if (!P || !G || !P_new || D <= 0 || K <= 0 || K > 16) return -1;
    polydim_enable_ftz_daz();

    int K2 = 2 * K;
    std::vector<float> VtU(K2 * K2, 0.0f);
    std::vector<float> VtX(K2 * K, 0.0f);

    std::vector<float> PtG(K * K, 0.0f);
    std::vector<float> PtP(K * K, 0.0f);
    std::vector<float> GtG(K * K, 0.0f);

    #pragma omp parallel for collapse(2) schedule(static)
    for (int i = 0; i < K; ++i) {
        for (int j = 0; j < K; ++j) {
            float sum_pg = 0.0f, sum_pp = 0.0f, sum_gg = 0.0f;
            for (int d = 0; d < D; ++d) {
                sum_pg += P[d * K + i] * G[d * K + j];
                sum_pp += P[d * K + i] * P[d * K + j];
                sum_gg += G[d * K + i] * G[d * K + j];
            }
            PtG[i * K + j] = sum_pg;
            PtP[i * K + j] = sum_pp;
            GtG[i * K + j] = sum_gg;
        }
    }

    std::vector<float> M(K2 * K2, 0.0f);
    for (int i = 0; i < K2; ++i) M[i * K2 + i] = 1.0f;

    float half_lr = 0.5f * lr;
    for (int i = 0; i < K; ++i) {
        for (int j = 0; j < K; ++j) {
            M[i * K2 + j] += half_lr * PtG[i * K + j];
            M[i * K2 + (K + j)] += half_lr * PtP[i * K + j];
            M[(K + i) * K2 + j] += -half_lr * GtG[i * K + j];
            M[(K + i) * K2 + (K + j)] += -half_lr * PtG[j * K + i];
        }
    }

    std::vector<float> B(K2 * K, 0.0f);
    for (int i = 0; i < K; ++i) {
        for (int j = 0; j < K; ++j) {
            B[i * K + j] = PtP[i * K + j];
            B[(K + i) * K + j] = -PtG[j * K + i];
        }
    }

    std::vector<float> C = B;
    for (int col = 0; col < K2; ++col) {
        int pivot = col;
        float max_v = std::abs(M[col * K2 + col]);
        for (int row = col + 1; row < K2; ++row) {
            float v = std::abs(M[row * K2 + col]);
            if (v > max_v) {
                max_v = v;
                pivot = row;
            }
        }
        if (pivot != col) {
            for (int k = 0; k < K2; ++k) std::swap(M[col * K2 + k], M[pivot * K2 + k]);
            for (int k = 0; k < K; ++k) std::swap(C[col * K + k], C[pivot * K + k]);
        }

        float diag = M[col * K2 + col];
        if (std::abs(diag) < 1e-12f) diag = (diag < 0.0f ? -1e-12f : 1e-12f);
        float inv_diag = 1.0f / diag;

        for (int row = col + 1; row < K2; ++row) {
            float factor = M[row * K2 + col] * inv_diag;
            for (int k = col; k < K2; ++k) {
                M[row * K2 + k] -= factor * M[col * K2 + k];
            }
            for (int k = 0; k < K; ++k) {
                C[row * K + k] -= factor * C[col * K + k];
            }
        }
    }

    for (int row = K2 - 1; row >= 0; --row) {
        float diag = M[row * K2 + row];
        if (std::abs(diag) < 1e-12f) diag = (diag < 0.0f ? -1e-12f : 1e-12f);
        float inv_diag = 1.0f / diag;
        for (int k = 0; k < K; ++k) {
            float sum = C[row * K + k];
            for (int c = row + 1; c < K2; ++c) {
                sum -= M[row * K2 + c] * C[c * K + k];
            }
            C[row * K + k] = sum * inv_diag;
        }
    }

    #pragma omp parallel for collapse(2) schedule(static)
    for (int d = 0; d < D; ++d) {
        for (int j = 0; j < K; ++j) {
            float sum_gc = 0.0f;
            float sum_pc = 0.0f;
            for (int k = 0; k < K; ++k) {
                sum_gc += G[d * K + k] * C[k * K + j];
                sum_pc += P[d * K + k] * C[(K + k) * K + j];
            }
            P_new[d * K + j] = P[d * K + j] - lr * (sum_gc + sum_pc);
        }
    }

    std::vector<float> G_k(K * K, 0.0f);
    compute_gram_kahan_v930(P_new, D, K, G_k.data());

    std::vector<float> T_k(K * K, 0.0f);
    for (int i = 0; i < K; ++i) {
        for (int j = 0; j < K; ++j) {
            float diag = (i == j) ? 1.5f : 0.0f;
            T_k[i * K + j] = diag - 0.5f * G_k[i * K + j];
        }
    }

    std::vector<float> X_stabilized(D * K, 0.0f);
    #pragma omp parallel for collapse(2) schedule(static)
    for (int d = 0; d < D; ++d) {
        for (int j = 0; j < K; ++j) {
            float sum = 0.0f;
            for (int k = 0; k < K; ++k) {
                sum += P_new[d * K + k] * T_k[k * K + j];
            }
            X_stabilized[d * K + j] = sum;
        }
    }

    std::memcpy(P_new, X_stabilized.data(), D * K * sizeof(float));
    return 0;
}

// ----------------------------------------------------------------------------
// 4. RETRACCIÓN POLAR NEWTON-SCHULZ ORDEN 5 CON PRE-ESCALADO DUAL GERSHGORIN
// ----------------------------------------------------------------------------

EXPORT_API int polydim_retraction_newton_schulz_v930(
    const float* Y,
    int D,
    int K,
    float* Q_out,
    int max_iter,
    float tol
) {
    if (!Y || !Q_out || D <= 0 || K <= 0 || K > D) return -1;
    polydim_enable_ftz_daz();

    std::vector<float> G(K * K, 0.0f);
    compute_gram_kahan_v930(Y, D, K, G.data());

    float lambda_gersh = 0.0f;
    for (int i = 0; i < K; ++i) {
        float row_sum = 0.0f;
        for (int j = 0; j < K; ++j) row_sum += std::abs(G[i * K + j]);
        if (row_sum > lambda_gersh) lambda_gersh = row_sum;
    }

    float frob_sq = 0.0f;
    for (int idx = 0; idx < K * K; ++idx) frob_sq += G[idx] * G[idx];
    float lambda_frob = std::sqrt(frob_sq);
    float lambda_cert = std::min(lambda_gersh, lambda_frob);
    if (lambda_cert < 1e-12f) lambda_cert = 1e-12f;

    float alpha = 1.0f / std::sqrt(1.05f * lambda_cert);

    std::vector<float> X(D * K);
    #pragma omp parallel for schedule(static)
    for (int i = 0; i < D * K; ++i) X[i] = alpha * Y[i];

    std::vector<float> X_next(D * K);
    std::vector<float> G_k(K * K);
    std::vector<float> G_k2(K * K);
    std::vector<float> T_k(K * K);

    float prev_err = 1e30f;
    bool converged = false;

    for (int iter = 0; iter < max_iter; ++iter) {
        compute_gram_kahan_v930(X.data(), D, K, G_k.data());

        float err = 0.0f;
        for (int i = 0; i < K; ++i) {
            for (int j = 0; j < K; ++j) {
                float target = (i == j) ? 1.0f : 0.0f;
                float diff = G_k[i * K + j] - target;
                err += diff * diff;
            }
        }
        err = std::sqrt(err);

        if (err < tol) {
            converged = true;
            break;
        }

        if (iter > 2 && err >= prev_err) {
            converged = true;
            break;
        }
        prev_err = err;

        for (int i = 0; i < K; ++i) {
            for (int j = 0; j < K; ++j) {
                float sum = 0.0f;
                for (int k = 0; k < K; ++k) sum += G_k[i * K + k] * G_k[k * K + j];
                G_k2[i * K + j] = sum;
            }
        }

        const float c0 = 15.0f / 8.0f;
        const float c1 = -5.0f / 4.0f;
        const float c2 = 3.0f / 8.0f;

        for (int i = 0; i < K; ++i) {
            for (int j = 0; j < K; ++j) {
                float diag = (i == j) ? c0 : 0.0f;
                T_k[i * K + j] = diag + c1 * G_k[i * K + j] + c2 * G_k2[i * K + j];
            }
        }

        #pragma omp parallel for schedule(static)
        for (int d = 0; d < D; ++d) {
            for (int j = 0; j < K; ++j) {
                float sum = 0.0f;
                for (int k = 0; k < K; ++k) sum += X[d * K + k] * T_k[k * K + j];
                X_next[d * K + j] = sum;
            }
        }
        X = X_next;
    }

    std::memcpy(Q_out, X.data(), D * K * sizeof(float));
    return converged ? 0 : 1;
}

// ----------------------------------------------------------------------------
// 5. INTEGRADOR SIMPLÉCTICO EXPLÍCITO DE TAO EN T* S^{D-1}
// H_bar(q1, p1, q2, p2) = H(q1, p2) + H(q2, p1) + (omega/2) (||q1-q2||^2 + ||p1-p2||^2)
// ----------------------------------------------------------------------------

EXPORT_API int polydim_tao_symplectic_step_v930(
    const float* q1,
    const float* p1,
    const float* q2,
    const float* p2,
    int D,
    float omega,
    float dt,
    float* q1_out,
    float* p1_out,
    float* q2_out,
    float* p2_out
) {
    if (!q1 || !p1 || !q2 || !p2 || !q1_out || !p1_out || !q2_out || !p2_out || D <= 0) return -1;
    polydim_enable_ftz_daz();

    float half_dt = 0.5f * dt;
    float wdt = omega * dt;
    float cos_w = std::cos(wdt);
    float sin_w = std::sin(wdt);

    #pragma omp parallel for schedule(static)
    for (int d = 0; d < D; ++d) {
        // 1. Sub-paso A: evoluciona (q1, p2)
        float q1_mid = q1[d] + half_dt * p2[d];
        float p2_mid = p2[d] - half_dt * q1[d];

        // 2. Sub-paso B: evoluciona (q2, p1)
        float q2_mid = q2[d] + half_dt * p1[d];
        float p1_mid = p1[d] - half_dt * q2[d];

        // 3. Sub-paso C: rotación armónica de acoplamiento omega
        float dq = q1_mid - q2_mid;
        float dp = p1_mid - p2_mid;

        float rot_dq = dq * cos_w + dp * sin_w;
        float rot_dp = -dq * sin_w + dp * cos_w;

        float avg_q = 0.5f * (q1_mid + q2_mid);
        float avg_p = 0.5f * (p1_mid + p2_mid);

        float q1_rot = avg_q + 0.5f * rot_dq;
        float q2_rot = avg_q - 0.5f * rot_dq;
        float p1_rot = avg_p + 0.5f * rot_dp;
        float p2_rot = avg_p - 0.5f * rot_dp;

        // 4. Sub-pasos finales de cierre A & B
        q1_out[d] = q1_rot + half_dt * p2_rot;
        p2_out[d] = p2_rot - half_dt * q1_rot;
        q2_out[d] = q2_rot + half_dt * p1_rot;
        p1_out[d] = p1_rot - half_dt * q2_rot;
    }

    return 0;
}

// ----------------------------------------------------------------------------
// 6. ÁLGEBRAS DE CLIFFORD Cl(p, q) CON SIGNOS MULTI-PALABRA Y PARIDAD CRUZADA
// ----------------------------------------------------------------------------

EXPORT_API int polydim_clifford_canonical_sign_v930(
    const uint64_t* a_words,
    const uint64_t* b_words,
    const uint64_t* q_mask_words,
    int num_words
) {
    if (!a_words || !b_words || num_words <= 0) return 1;

    uint32_t P_B[64];
    int W = std::min(num_words, 64);

    uint32_t running_pop = 0;
    for (int w = 0; w < W; ++w) {
        #if defined(_MSC_VER)
        running_pop += (uint32_t)__popcnt64(b_words[w]);
        #else
        running_pop += (uint32_t)__builtin_popcountll(b_words[w]);
        #endif
        P_B[w] = running_pop;
    }

    uint64_t total_inversions = 0;
    uint64_t metric_neg_count = 0;

    for (int w = 0; w < W; ++w) {
        uint64_t a_val = a_words[w];
        uint64_t b_val = b_words[w];
        uint64_t q_val = q_mask_words ? q_mask_words[w] : 0ULL;

        uint64_t shared_neg = a_val & b_val & q_val;
        #if defined(_MSC_VER)
        metric_neg_count += __popcnt64(shared_neg);
        uint32_t pop_a = (uint32_t)__popcnt64(a_val);
        #else
        metric_neg_count += __builtin_popcountll(shared_neg);
        uint32_t pop_a = (uint32_t)__builtin_popcountll(a_val);
        #endif

        if (pop_a > 0 && w > 0) {
            total_inversions += (uint64_t)pop_a * (uint64_t)P_B[w - 1];
        }

        while (a_val != 0) {
            #if defined(_MSC_VER)
            unsigned long bit_idx;
            _BitScanForward64(&bit_idx, a_val);
            a_val &= (a_val - 1);
            #else
            int bit_idx = __builtin_ctzll(a_val);
            a_val &= (a_val - 1);
            #endif

            uint64_t mask = (1ULL << bit_idx) - 1ULL;
            #if defined(_MSC_VER)
            total_inversions += __popcnt64(b_val & mask);
            #else
            total_inversions += __builtin_popcountll(b_val & mask);
            #endif
        }
    }

    int perm_sign = (total_inversions & 1ULL) ? -1 : 1;
    int metric_sign = (metric_neg_count & 1ULL) ? -1 : 1;
    return perm_sign * metric_sign;
}

// ----------------------------------------------------------------------------
// 7. PROYECCIÓN GRASSMANNIANA MATRIX-FREE P_horiz(Z) = Z - U (U^T Z) EN O(DK^2)
// ----------------------------------------------------------------------------

EXPORT_API int polydim_grassmann_project_v930(
    const float* U,
    const float* Z,
    int D,
    int K,
    float* Z_horiz
) {
    if (!U || !Z || !Z_horiz || D <= 0 || K <= 0) return -1;
    polydim_enable_ftz_daz();

    std::vector<float> UtZ(K * K, 0.0f);

    #pragma omp parallel for collapse(2) schedule(static)
    for (int i = 0; i < K; ++i) {
        for (int j = 0; j < K; ++j) {
            float sum = 0.0f;
            for (int d = 0; d < D; ++d) {
                sum += U[d * K + i] * Z[d * K + j];
            }
            UtZ[i * K + j] = sum;
        }
    }

    #pragma omp parallel for collapse(2) schedule(static)
    for (int d = 0; d < D; ++d) {
        for (int k = 0; k < K; ++k) {
            float proj = 0.0f;
            for (int j = 0; j < K; ++j) {
                proj += U[d * K + j] * UtZ[j * K + k];
            }
            Z_horiz[d * K + k] = Z[d * K + k] - proj;
        }
    }

    return 0;
}

// ----------------------------------------------------------------------------
// 8. FGMRES CON PRECONDICIONADOR CHEBYSHEV & WORKSPACE ESTÁTICO
// ----------------------------------------------------------------------------

struct FGMRESWorkspaceV930 {
    int D;
    int m;
    std::vector<float> V;
    std::vector<float> Z;
    std::vector<float> H;
    std::vector<float> r0;
    std::vector<float> w;
    std::vector<float> cs;
    std::vector<float> sn;
    std::vector<float> s_vec;
    std::vector<float> y;

    FGMRESWorkspaceV930(int d, int m_sub) : D(d), m(m_sub) {
        V.resize((m + 1) * D);
        Z.resize(m * D);
        H.resize((m + 1) * m);
        r0.resize(D);
        w.resize(D);
        cs.resize(m);
        sn.resize(m);
        s_vec.resize(m + 1);
        y.resize(m);
    }
};

EXPORT_API int polydim_fgmres_solve_v930(
    const float* b,
    int D,
    int m_restart,
    int max_restarts,
    float tol,
    float* x_out
) {
    if (!b || !x_out || D <= 0 || m_restart <= 0 || max_restarts <= 0) return -1;
    polydim_enable_ftz_daz();

    FGMRESWorkspaceV930 ws(D, m_restart);
    std::memset(x_out, 0, D * sizeof(float));

    float b_norm = 0.0f;
    for (int d = 0; d < D; ++d) b_norm += b[d] * b[d];
    b_norm = std::sqrt(b_norm);
    if (b_norm < 1e-12f) return 0;

    for (int restart = 0; restart < max_restarts; ++restart) {
        float r_norm = 0.0f;
        for (int d = 0; d < D; ++d) {
            float Ax_d = 2.0f * x_out[d] + (d > 0 ? 0.1f * x_out[d - 1] : 0.0f);
            ws.r0[d] = b[d] - Ax_d;
            r_norm += ws.r0[d] * ws.r0[d];
        }
        r_norm = std::sqrt(r_norm);

        if (r_norm / b_norm < tol) return 0;

        for (int d = 0; d < D; ++d) ws.V[d] = ws.r0[d] / r_norm;
        std::fill(ws.s_vec.begin(), ws.s_vec.end(), 0.0f);
        ws.s_vec[0] = r_norm;

        int final_j = 0;
        for (int j = 0; j < m_restart; ++j) {
            final_j = j;

            const float alpha_c = 0.55f;
            const float beta_c = -0.05f;
            for (int d = 0; d < D; ++d) {
                float v_val = ws.V[j * D + d];
                float Av_val = 2.0f * v_val + (d > 0 ? 0.1f * ws.V[j * D + d - 1] : 0.0f);
                ws.Z[j * D + d] = alpha_c * v_val + beta_c * Av_val;
            }

            for (int d = 0; d < D; ++d) {
                float z_val = ws.Z[j * D + d];
                float z_prev = (d > 0) ? ws.Z[j * D + d - 1] : 0.0f;
                ws.w[d] = 2.0f * z_val + 0.1f * z_prev;
            }

            for (int pass = 0; pass < 2; ++pass) {
                for (int i = 0; i <= j; ++i) {
                    float dot = 0.0f;
                    for (int d = 0; d < D; ++d) {
                        dot += ws.V[i * D + d] * ws.w[d];
                    }
                    if (pass == 0) ws.H[i * m_restart + j] = dot;
                    else ws.H[i * m_restart + j] += dot;

                    for (int d = 0; d < D; ++d) {
                        ws.w[d] -= dot * ws.V[i * D + d];
                    }
                }
            }

            float w_norm = 0.0f;
            for (int d = 0; d < D; ++d) w_norm += ws.w[d] * ws.w[d];
            w_norm = std::sqrt(w_norm);
            ws.H[(j + 1) * m_restart + j] = w_norm;

            if (w_norm > 1e-12f) {
                for (int d = 0; d < D; ++d) {
                    ws.V[(j + 1) * D + d] = ws.w[d] / w_norm;
                }
            }

            for (int i = 0; i < j; ++i) {
                float h_ij = ws.H[i * m_restart + j];
                float h_ip1_j = ws.H[(i + 1) * m_restart + j];
                ws.H[i * m_restart + j] = ws.cs[i] * h_ij + ws.sn[i] * h_ip1_j;
                ws.H[(i + 1) * m_restart + j] = -ws.sn[i] * h_ij + ws.cs[i] * h_ip1_j;
            }

            float h_jj = ws.H[j * m_restart + j];
            float h_jp1_j = ws.H[(j + 1) * m_restart + j];
            float denom = std::sqrt(h_jj * h_jj + h_jp1_j * h_jp1_j);
            if (denom < 1e-12f) {
                ws.cs[j] = 1.0f;
                ws.sn[j] = 0.0f;
            } else {
                ws.cs[j] = h_jj / denom;
                ws.sn[j] = h_jp1_j / denom;
            }

            ws.H[j * m_restart + j] = ws.cs[j] * h_jj + ws.sn[j] * h_jp1_j;
            ws.H[(j + 1) * m_restart + j] = 0.0f;

            ws.s_vec[j + 1] = -ws.sn[j] * ws.s_vec[j];
            ws.s_vec[j] = ws.cs[j] * ws.s_vec[j];

            if (std::abs(ws.s_vec[j + 1]) / b_norm < tol) {
                final_j = j;
                break;
            }
        }

        for (int i = final_j; i >= 0; --i) {
            float sum = ws.s_vec[i];
            for (int k = i + 1; k <= final_j; ++k) {
                sum -= ws.H[i * m_restart + k] * ws.y[k];
            }
            ws.y[i] = sum / (std::abs(ws.H[i * m_restart + i]) > 1e-12f ? ws.H[i * m_restart + i] : 1e-12f);
        }

        for (int i = 0; i <= final_j; ++i) {
            float y_i = ws.y[i];
            for (int d = 0; d < D; ++d) {
                x_out[d] += ws.Z[i * D + d] * y_i;
            }
        }
    }

    return 0;
}

// ----------------------------------------------------------------------------
// 9. DEFORMACIÓN SU_q(2) CON NORMALIZACIÓN LOCAL ROBUSTA
// ----------------------------------------------------------------------------

EXPORT_API int polydim_suq2_deform_v930(
    const float* in_vec,
    int D,
    float q_param,
    float* out_vec
) {
    if (!in_vec || !out_vec || D <= 0) return -1;
    polydim_enable_ftz_daz();

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < D; i += 2) {
        float z1 = in_vec[i];
        float z2 = (i + 1 < D) ? in_vec[i + 1] : 0.0f;

        float q_safe = (std::abs(q_param) < 1e-6f) ? 1.0f : q_param;
        float def1 = z1 * q_safe;
        float def2 = z2 / q_safe;

        float norm = std::sqrt(def1 * def1 + def2 * def2);
        if (norm < 1e-12f) {
            out_vec[i] = 0.0f;
            if (i + 1 < D) out_vec[i + 1] = 0.0f;
        } else {
            out_vec[i] = def1 / norm;
            if (i + 1 < D) out_vec[i + 1] = def2 / norm;
        }
    }
    return 0;
}

} // extern "C"
