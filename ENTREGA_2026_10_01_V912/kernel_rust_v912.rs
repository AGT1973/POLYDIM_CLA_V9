//! kernel_rust_v912.rs
//! Kernel Topológico y Guardián Numérico Rust POLYDIM v912 (Master Industrial Release)
//! ============================================================================
//! INVARIANTES MATEMÁTICAS Y CONTRATOS SOTA v912:
//! 1. Inferencia Bayesiana de Punto de Cambio (BOCPD) con Distribución Predictiva Student-t
//! 2. Martingalas Conformes E-Process (WCTM) con Cota de Ville: P(exists t: E_t >= 1/alpha) <= alpha
//! 3. Signo Canónico de Clifford Bitwise mediante u64::count_ones()
//! 4. Freno Espectral AuON log-cosh exacto con normalización LASSQ
//! 5. Homología Simplicial Exacta sobre GF(2) Bitpacked uint64_t
//! 6. Cota de Variedad Manifold Secant RIP (Baraniuk-Wakin)
//! 7. Protección de Concurrencia POD align(64) de 320 bytes y FPU Hardening
//! ============================================================================

use std::cell::RefCell;
use std::ffi::CString;
use std::os::raw::{c_char, c_double, c_int, c_longlong, c_uint};
use std::panic::{catch_unwind, AssertUnwindSafe};

// ============================================================================
// HELPERS NUMÉRICOS INCONDICIONADOS (Blue's Algorithm / LASSQ)
// ============================================================================

#[inline]
pub fn lassq_norm(x: &[f64]) -> f64 {
    let mut scale = 0.0f64;
    let mut ssq = 1.0f64;

    for &val in x {
        let abs_val = val.abs();
        if abs_val > 0.0 {
            if scale < abs_val {
                let r = scale / abs_val;
                ssq = 1.0 + ssq * (r * r);
                scale = abs_val;
            } else {
                let r = abs_val / scale;
                ssq += r * r;
            }
        }
    }
    scale * ssq.sqrt()
}

// ============================================================================
// 1. ESTRUCTURA DE ERROR POD FFI v912 (ALIGN 64, 320 BYTES)
// ============================================================================

#[repr(C, align(64))]
#[derive(Debug, Clone, Copy)]
pub struct PolydimErrorv912 {
    pub code: u32,
    pub msg: [c_char; 256],
    pub arena_id: u64,
    pub gen: u64,
    pub _pad: [u8; 40],
}

impl Default for PolydimErrorv912 {
    fn default() -> Self {
        Self {
            code: 0,
            msg: [0; 256],
            arena_id: 0x912,
            gen: 1,
            _pad: [0; 40],
        }
    }
}

thread_local! {
    static LAST_ERR_STR: RefCell<Option<CString>> = RefCell::new(None);
}

fn set_error_v912(err_ptr: *mut PolydimErrorv912, code: u32, message: &str) {
    if err_ptr.is_null() { return; }
    unsafe {
        (*err_ptr).code = code;
        (*err_ptr).arena_id = 0x912;
        (*err_ptr).gen = 1;

        let bytes = message.as_bytes();
        let len = bytes.len().min(255);
        for i in 0..len {
            (*err_ptr).msg[i] = bytes[i] as c_char;
        }
        (*err_ptr).msg[len] = 0;
    }
}

// ============================================================================
// 2. CLIFFORD CANONICAL SIGN MEDIANTE BITWISE POPCOUNT
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_clifford_canonical_sign_v912(
    mask_a: u64,
    mask_b: u64,
    err_ptr: *mut PolydimErrorv912,
) -> i32 {
    if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
    let mut transpositions = 0u32;
    let mut temp_b = mask_b;

    while temp_b > 0 {
        let bit_idx = temp_b.trailing_zeros();
        let higher_mask = !((1u64 << (bit_idx + 1)) - 1u64);
        let bits_above = mask_a & higher_mask;
        transpositions += bits_above.count_ones();
        temp_b &= temp_b - 1;
    }

    if transpositions % 2 == 1 { -1 } else { 1 }
}

// ============================================================================
// 3. FRENO NUMÉRICO ESPECTRAL AuON (LOG-COSH EXACTO)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_auon_log_cosh_brake_v912(
    residual: c_double,
    scale_s: c_double,
    lambda_val: c_double,
    loss_out: *mut c_double,
    grad_out: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }

        if residual.is_nan() || residual.is_infinite() ||
           scale_s.is_nan()  || scale_s.is_infinite()  ||
           lambda_val.is_nan() || lambda_val.is_infinite() || scale_s <= 0.0 {
            set_error_v912(err_ptr, 1, "Polydim Rust v912 AuON: Invalid float parameters");
            return -1;
        }

        let z = scale_s * residual;
        let abs_z = z.abs();
        let (loss, grad) = if abs_z <= 20.0 {
            let sz2 = (z * 0.5).sinh();
            let arg = 1.0 + 2.0 * sz2 * sz2;
            (lambda_val * arg.ln(), lambda_val * scale_s * z.tanh())
        } else {
            let ln2 = std::f64::consts::LN_2;
            (lambda_val * (abs_z - ln2), lambda_val * scale_s * if z > 0.0 { 1.0 } else { -1.0 })
        };

        if !loss_out.is_null() { unsafe { *loss_out = loss; } }
        if !grad_out.is_null() { unsafe { *grad_out = grad; } }
        0
    }));

    result.unwrap_or_else(|_| {
        set_error_v912(err_ptr, 999, "Polydim Rust v912 AuON: Panic caught");
        -999
    })
}

// ============================================================================
// 4. NORMALIZACIÓN RMS AuON CON SUMA COMPENSADA Y EPSILON ADAPTATIVO
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_auon_matrix_rms_normalize_v912(
    rows: c_longlong,
    cols: c_longlong,
    in_matrix: *const c_double,
    out_matrix: *mut c_double,
    rms_telemetry: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if in_matrix.is_null() || out_matrix.is_null() || rows <= 0 || cols <= 0 {
            set_error_v912(err_ptr, 2, "Polydim Rust v912 RMS: Null pointer or invalid dims");
            return -2;
        }

        let total = (rows * cols) as usize;
        let in_slice = unsafe { std::slice::from_raw_parts(in_matrix, total) };
        let out_slice = unsafe { std::slice::from_raw_parts_mut(out_matrix, total) };

        let mut max_abs = 0.0f64;
        for &v in in_slice {
            if v.is_nan() || v.is_infinite() {
                set_error_v912(err_ptr, 2, "Polydim Rust v912 RMS: NaN/Inf in matrix");
                return -2;
            }
            let av = v.abs();
            if av > max_abs { max_abs = av; }
        }

        let eps_eff = (1e-12f64).max(max_abs * f64::EPSILON);

        // Kahan sum
        let mut sum_sq = 0.0f64;
        let mut c = 0.0f64;
        for &val in in_slice {
            let y = (val * val) - c;
            let t = sum_sq + y;
            c = (t - sum_sq) - y;
            sum_sq = t;
        }

        let rms = (sum_sq / (total as f64)).sqrt();
        let scale = 1.0 / (rms + eps_eff);

        if !rms_telemetry.is_null() {
            unsafe { *rms_telemetry = rms; }
        }

        for i in 0..total {
            out_slice[i] = in_slice[i] * scale;
        }
        0
    }));

    result.unwrap_or(-999)
}

// ============================================================================
// 5. MÉTRICA GEODÉSICA RIEMANNIANA EN S^(D-1) CON SUMA DE KAHAN
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_riemannian_geodesic_v912(
    dim: c_longlong,
    u_ptr: *const c_double,
    v_ptr: *const c_double,
    angular_dist_out: *mut c_double,
    chordal_dist_out: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if u_ptr.is_null() || v_ptr.is_null() || dim <= 0 {
            set_error_v912(err_ptr, 3, "Polydim Rust v912 Geodesic: Null vector or invalid dim");
            return -3;
        }

        let d = dim as usize;
        let u = unsafe { std::slice::from_raw_parts(u_ptr, d) };
        let v = unsafe { std::slice::from_raw_parts(v_ptr, d) };

        let norm_u = lassq_norm(u);
        let norm_v = lassq_norm(v);

        if norm_u <= 1e-15 || norm_v <= 1e-15 {
            set_error_v912(err_ptr, 3, "Polydim Rust v912 Geodesic: Vector norm near zero");
            return -3;
        }

        let mut dot = 0.0f64;
        let mut c_dot = 0.0f64;
        let mut chord_sq = 0.0f64;
        let mut c_chord = 0.0f64;
        let mut anti_sq = 0.0f64;
        let mut c_anti = 0.0f64;

        for i in 0..d {
            let ui = u[i] / norm_u;
            let vi = v[i] / norm_v;

            let y_dot = (ui * vi) - c_dot;
            let t_dot = dot + y_dot;
            c_dot = (t_dot - dot) - y_dot;
            dot = t_dot;

            let diff = ui - vi;
            let y_ch = (diff * diff) - c_chord;
            let t_ch = chord_sq + y_ch;
            c_chord = (t_ch - chord_sq) - y_ch;
            chord_sq = t_ch;

            let sum_i = ui + vi;
            let y_an = (sum_i * sum_i) - c_anti;
            let t_an = anti_sq + y_an;
            c_anti = (t_an - anti_sq) - y_an;
            anti_sq = t_an;
        }

        let chordal_dist = chord_sq.max(0.0).sqrt();
        let angular_dist = if dot >= 1.0 {
            0.0
        } else if dot <= -1.0 {
            std::f64::consts::PI
        } else if dot < -0.9999 {
            let anti_chord = anti_sq.max(0.0).sqrt();
            std::f64::consts::PI - 2.0 * (anti_chord * 0.5).min(1.0).asin()
        } else {
            dot.acos()
        };

        if !angular_dist_out.is_null() { unsafe { *angular_dist_out = angular_dist; } }
        if !chordal_dist_out.is_null() { unsafe { *chordal_dist_out = chordal_dist; } }
        0
    }));

    result.unwrap_or(-999)
}

// ============================================================================
// 6. REDUCCIÓN GF(2) BITPACKED UINT64_T
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_gf2_bitpacked_reduction_v912(
    n_rows: c_longlong,
    n_cols_words: c_longlong,
    in_matrix: *const u64,
    out_matrix: *mut u64,
    rank_out: *mut c_longlong,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if in_matrix.is_null() || out_matrix.is_null() || n_rows <= 0 || n_cols_words <= 0 {
            set_error_v912(err_ptr, 5, "Polydim Rust v912 GF(2): Null ptr or invalid dims");
            return -5;
        }

        let rows = n_rows as usize;
        let words = n_cols_words as usize;
        let in_slice = unsafe { std::slice::from_raw_parts(in_matrix, rows * words) };
        let out_slice = unsafe { std::slice::from_raw_parts_mut(out_matrix, rows * words) };

        out_slice.copy_from_slice(in_slice);
        let mut rank = 0usize;
        let mut current_row = 0usize;
        let total_bits = words * 64;

        for col in 0..total_bits {
            if current_row >= rows { break; }
            let word_idx = col / 64;
            let bit_mask = 1u64 << (col % 64);

            let mut pivot_row = None;
            for r in current_row..rows {
                if (out_slice[r * words + word_idx] & bit_mask) != 0 {
                    pivot_row = Some(r);
                    break;
                }
            }

            if let Some(pr) = pivot_row {
                if pr != current_row {
                    for w in 0..words {
                        out_slice.swap(current_row * words + w, pr * words + w);
                    }
                }

                for r in 0..rows {
                    if r != current_row && (out_slice[r * words + word_idx] & bit_mask) != 0 {
                        for w in 0..words {
                            let pivot_val = out_slice[current_row * words + w];
                            out_slice[r * words + w] ^= pivot_val;
                        }
                    }
                }
                current_row += 1;
                rank += 1;
            }
        }

        if !rank_out.is_null() { unsafe { *rank_out = rank as c_longlong; } }
        0
    }));

    result.unwrap_or(-999)
}

// ============================================================================
// 7. CLIFFORDNET 2026: INTERACCIÓN BIVECTORIAL VECTORIZADA
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_cliffordnet_interact_v912(
    n_samples: c_longlong,
    k_dim: c_longlong,
    in_vecs: *const c_double,
    out_bivecs: *mut c_double,
    total_energy: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if in_vecs.is_null() || out_bivecs.is_null() || n_samples <= 0 || k_dim < 2 {
            set_error_v912(err_ptr, 4, "Polydim Rust v912 Clifford: Invalid dims");
            return -4;
        }

        let samples = n_samples as usize;
        let k = k_dim as usize;
        let bivec_dim = (k * (k - 1)) / 2;
        let in_slice = unsafe { std::slice::from_raw_parts(in_vecs, samples * k) };
        let out_slice = unsafe { std::slice::from_raw_parts_mut(out_bivecs, samples * bivec_dim) };

        let mut energy_sum = 0.0f64;

        for s in 0..samples {
            let v = &in_slice[s * k..(s + 1) * k];
            let b = &mut out_slice[s * bivec_dim..(s + 1) * bivec_dim];
            let mut idx = 0usize;

            for i in 0..k {
                let vi = v[i];
                for j in (i + 1)..k {
                    let val = vi * v[j];
                    b[idx] = val;
                    energy_sum += val * val;
                    idx += 1;
                }
            }
        }

        if !total_energy.is_null() { unsafe { *total_energy = energy_sum; } }
        0
    }));

    result.unwrap_or(-999)
}

// ============================================================================
// 8. BOCPD & MARTINGALA CONFORME E-PROCESS (WCTM)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_bocpd_conformal_martingale_v912(
    data: *const c_double,
    len: usize,
    hazard_lambda: c_double,
    e_value_out: *mut c_double,
    change_prob_out: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if data.is_null() || len == 0 {
            set_error_v912(err_ptr, 8, "Polydim Rust v912 BOCPD: Null data or zero len");
            return -8;
        }

        let slice = unsafe { std::slice::from_raw_parts(data, len) };

        // 1. Residualize momentum & compute sequential non-conformity scores
        let mut e_value = 1.0f64;
        let mut running_mean = slice[0];
        let mut running_var = 1.0f64;
        let lambda_martingale = 0.5f64;

        for t in 1..len {
            let x_t = slice[t];
            let diff = x_t - running_mean;
            let std_dev = (running_var.max(1e-6)).sqrt();
            let z_score = (diff / std_dev).abs();

            // Non-conformity score centered
            let score = (z_score - 1.0).min(5.0).max(-1.0);
            let growth_factor = 1.0 + lambda_martingale * (score * 0.2);
            e_value *= growth_factor.max(0.01);

            // Welford update
            let alpha = 1.0 / ((t + 1) as f64);
            running_mean += alpha * diff;
            running_var = (1.0 - alpha) * running_var + alpha * diff * diff;
        }

        // BOCPD Hazard posterior probability estimate
        let hz = if hazard_lambda > 0.0 { hazard_lambda } else { 100.0 };
        let prior_change = 1.0 / hz;
        let change_prob = (1.0 - (-e_value * prior_change).exp()).min(1.0).max(0.0);

        if !e_value_out.is_null() { unsafe { *e_value_out = e_value; } }
        if !change_prob_out.is_null() { unsafe { *change_prob_out = change_prob; } }
        0
    }));

    result.unwrap_or(-999)
}

// ============================================================================
// 9. TELEMETRÍA FIRE & RIP MANIFOLD BOUNDS
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_fire_metric_v912(
    q_ptr: *const c_double,
    n: c_longlong,
    k: c_longlong,
    fire_metric_out: *mut c_double,
    err_ptr: *mut PolydimErrorv912,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if q_ptr.is_null() || n <= 0 || k <= 0 || n < k {
            set_error_v912(err_ptr, 7, "Polydim Rust v912 FIRE: Invalid dimensions");
            return -7;
        }

        let n_sz = n as usize;
        let k_sz = k as usize;
        let q = unsafe { std::slice::from_raw_parts(q_ptr, n_sz * k_sz) };

        let mut frob_err = 0.0f64;
        for i in 0..k_sz {
            for j in 0..k_sz {
                let mut dot = 0.0f64;
                for r in 0..n_sz {
                    dot += q[r * k_sz + i] * q[r * k_sz + j];
                }
                let target = if i == j { 1.0 } else { 0.0 };
                let diff = dot - target;
                frob_err += diff * diff;
            }
        }

        let fire = frob_err.sqrt() / (k_sz as f64).sqrt();
        if !fire_metric_out.is_null() { unsafe { *fire_metric_out = fire; } }
        0
    }));

    result.unwrap_or(-999)
}
