import os

file_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V908\kernel_cpp_v908.cpp'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. AuON RMS: Use logaddexp strictly
old_rms = """        double log_rms = -std::numeric_limits<double>::infinity();
        if (sum_exp > 0.0) {
            log_rms = max_log * 0.5 + 0.5 * std::log(sum_exp / static_cast<double>(n));
        }
        
        double scale = 0.0;
        if (log_rms != -std::numeric_limits<double>::infinity()) {
            scale = std::exp(-log_rms); // Direct log-space scaling
            if (!std::isfinite(scale)) scale = 0.0; // Underflow to 0 safely
        }"""

new_rms = """        double log_rms = -std::numeric_limits<double>::infinity();
        if (sum_exp > 0.0) {
            log_rms = max_log * 0.5 + 0.5 * std::log(sum_exp / static_cast<double>(n));
        }
        
        double scale = 0.0;
        if (log_rms != -std::numeric_limits<double>::infinity()) {
            // SOTA: logaddexp integration to preserve epsilon semantically
            double eps = 1e-8;
            double log_eps = std::log(eps);
            double diff = log_eps - log_rms;
            double log_rms_eps = log_rms + (diff > 0 ? diff + std::log1p(std::exp(-diff)) : std::log1p(std::exp(diff)));
            scale = std::exp(-log_rms_eps);
            if (!std::isfinite(scale)) scale = 0.0;
        }"""
content = content.replace(old_rms, new_rms)

# 2. Geodesic: Neumaier Summation
old_geo = """                // Kahan dot
                double y_dot = (un * vn) - c_dot;
                double t_dot = local_dot + y_dot;
                c_dot = (t_dot - local_dot) - y_dot;
                local_dot = t_dot;
                
                // Kahan chordal
                double diff = un - vn;
                double y_chord = (diff * diff) - c_chord;
                double t_chord = local_chord + y_chord;
                c_chord = (t_chord - local_chord) - y_chord;
                local_chord = t_chord;"""

new_geo = """                // Neumaier dot (SOTA Scientific)
                double term_dot = un * vn;
                double t_dot = local_dot + term_dot;
                if (std::abs(local_dot) >= std::abs(term_dot)) {
                    c_dot += (local_dot - t_dot) + term_dot;
                } else {
                    c_dot += (term_dot - t_dot) + local_dot;
                }
                local_dot = t_dot;
                
                // Neumaier chordal (SOTA Scientific)
                double diff = un - vn;
                double term_chord = diff * diff;
                double t_chord = local_chord + term_chord;
                if (std::abs(local_chord) >= std::abs(term_chord)) {
                    c_chord += (local_chord - t_chord) + term_chord;
                } else {
                    c_chord += (term_chord - t_chord) + local_chord;
                }
                local_chord = t_chord;"""
content = content.replace(old_geo, new_geo)

# 3. Cayley Retraction: Persistent thread_local Workspace
old_cayley = """    // Fixed buffer for K <= 128 (max 256 system size) to avoid dynamic allocation bottleneck
    double static_aug[256 * 256 + 256 * 128]; 
    double* aug = static_aug;
    std::vector<double> dyn_aug;
    if (n_sys * cols > (256 * 256 + 256 * 128)) {
        dyn_aug.resize(n_sys * cols);
        aug = dyn_aug.data();
    }"""

new_cayley = """    // SOTA: thread_local persistent workspace to prevent heap fragmentation unconditionally
    thread_local std::vector<double> tls_aug;
    if (tls_aug.size() < static_cast<size_t>(n_sys * cols)) {
        tls_aug.resize(n_sys * cols);
    }
    double* aug = tls_aug.data();"""
content = content.replace(old_cayley, new_cayley)

# 4. CliffordNet: Separate Metric and Raw Energy telemetry
old_cliff = """POLYDIM_EXPORT int polydim_cpp_cliffordnet_bivector_interact_v908(
    uint32_t num_vectors,
    uint32_t dim_k,
    const double* vectors_in,
    double* bivectors_out,
    double* energy_out,
    PolydimErrorV908* err
) noexcept {"""

new_cliff = """POLYDIM_EXPORT int polydim_cpp_cliffordnet_bivector_interact_v908(
    uint32_t num_vectors,
    uint32_t dim_k,
    const double* vectors_in,
    double* bivectors_out,
    double* raw_energy_out,
    double* metric_energy_out,
    PolydimErrorV908* err
) noexcept {"""
content = content.replace(old_cliff, new_cliff)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
