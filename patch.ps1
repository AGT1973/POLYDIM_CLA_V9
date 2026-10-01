$file = "E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V907\kernel_cpp_v907.cpp"
$content = Get-Content $file -Raw

# Patch Riemannian Geodesic Kahan
$old_geo = @"
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
"@

$new_geo = @"
        double dot = 0.0;
        double chordal_sq = 0.0;
        int64_t d_i64 = static_cast<int64_t>(d);

        #pragma omp parallel schedule(static)
        {
            double local_dot = 0.0, c_dot = 0.0;
            double local_chord = 0.0, c_chord = 0.0;
            #pragma omp for
            for (int64_t i = 0; i < d_i64; ++i) {
                double un = u[i] * inv_u;
                double vn = v[i] * inv_v;
                
                // Kahan dot
                double y_dot = (un * vn) - c_dot;
                double t_dot = local_dot + y_dot;
                c_dot = (t_dot - local_dot) - y_dot;
                local_dot = t_dot;
                
                // Kahan chordal
                double diff = un - vn;
                double y_chord = (diff * diff) - c_chord;
                double t_chord = local_chord + y_chord;
                c_chord = (t_chord - local_chord) - y_chord;
                local_chord = t_chord;
            }
            #pragma omp critical
            {
                dot += local_dot;
                chordal_sq += local_chord;
            }
        }

        dot = std::clamp(dot, -1.0, 1.0);
        double chord = std::sqrt(chordal_sq);
        double angle;
        if (dot > 0.9999) {
            angle = 2.0 * std::asin(chord * 0.5);
        } else if (dot < -0.9999) {
            double chord_anti = 0.0;
            #pragma omp parallel for reduction(+:chord_anti) schedule(static)
            for (int64_t i = 0; i < d_i64; ++i) {
                double un = u[i] * inv_u;
                double vn = v[i] * inv_v;
                double sum_val = un + vn;
                chord_anti += sum_val * sum_val;
            }
            angle = 3.14159265358979323846 - 2.0 * std::asin(std::sqrt(chord_anti) * 0.5);
        } else {
            angle = std::acos(dot);
        }
"@

$content = $content.Replace($old_geo, $new_geo)

# Patch Cayley Retraction Allocation Bottleneck
$old_cayley = @"
bool solve_linear_system_2k_v907(int64_t n_sys, int64_t n_rhs, const double* A, const double* B, double* X_sol) noexcept {
    int64_t cols = n_sys + n_rhs;
    std::vector<double> aug(n_sys * cols);
"@
$new_cayley = @"
bool solve_linear_system_2k_v907(int64_t n_sys, int64_t n_rhs, const double* A, const double* B, double* X_sol) noexcept {
    int64_t cols = n_sys + n_rhs;
    // Fixed buffer for K <= 128 (max 256 system size) to avoid dynamic allocation bottleneck
    double static_aug[256 * 256 + 256 * 128]; 
    double* aug = static_aug;
    std::vector<double> dyn_aug;
    if (n_sys * cols > (256 * 256 + 256 * 128)) {
        dyn_aug.resize(n_sys * cols);
        aug = dyn_aug.data();
    }
"@
$content = $content.Replace($old_cayley, $new_cayley)

# Patch AuON Log-Space RMS
$old_rms = @"
        double rms;
        if (sum_exp > 0.0) {
            rms = std::exp(max_log * 0.5) * std::sqrt(sum_exp / static_cast<double>(n));
        } else {
            rms = 0.0;
        }

        double scale = 1.0 / (rms + 1e-8);
"@
$new_rms = @"
        double log_rms = -std::numeric_limits<double>::infinity();
        if (sum_exp > 0.0) {
            log_rms = max_log * 0.5 + 0.5 * std::log(sum_exp / static_cast<double>(n));
        }
        
        double scale = 0.0;
        if (log_rms != -std::numeric_limits<double>::infinity()) {
            scale = std::exp(-log_rms); // Direct log-space scaling
            if (!std::isfinite(scale)) scale = 0.0; // Underflow to 0 safely
        }
        double rms = std::exp(log_rms);
"@
$content = $content.Replace($old_rms, $new_rms)

$content | Set-Content $file
