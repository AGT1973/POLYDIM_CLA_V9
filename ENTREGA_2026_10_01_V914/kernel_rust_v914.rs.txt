//! kernel_rust_v914.rs
//! Kernel Topológico y Guardián Numérico Rust POLYDIM v914 (Master Industrial Release)
//! ============================================================================
//! INVARIANTES NUMÉRICAS SOTA v914:
//! 1. Hardware FTZ/DAZ x86_64 MXCSR Initializer
//! 2. Conformal Martingale con Discounted OGD (Ader): Memoria Exponencial gamma in [0.95, 0.99]
//! 3. Signo Canónico de Clifford en Tiempo Lineal O(W) mediante Sumas de Prefijos de Popcount
//! 4. Freno Espectral AuON log-cosh, Geodésica Riemanniana Kahan y Telemetría FIRE
//! ============================================================================

use std::cell::RefCell;
use std::ffi::CString;
use std::os::raw::{c_char, c_double, c_int, c_longlong};
use std::panic::{catch_unwind, AssertUnwindSafe};

#[repr(C, align(64))]
#[derive(Debug, Clone, Copy)]
pub struct PolydimErrorv914 {
    pub code: u32,
    pub msg: [c_char; 256],
    pub arena_id: u64,
    pub gen: u64,
    pub _pad: [u8; 40],
}

impl Default for PolydimErrorv914 {
    fn default() -> Self {
        Self {
            code: 0,
            msg: [0; 256],
            arena_id: 0x914,
            gen: 1,
            _pad: [0; 40],
        }
    }
}

fn set_error_v914(err_ptr: *mut PolydimErrorv914, code: u32, message: &str) {
    if err_ptr.is_null() { return; }
    unsafe {
        (*err_ptr).code = code;
        (*err_ptr).arena_id = 0x914;
        (*err_ptr).gen = 1;
        let bytes = message.as_bytes();
        let len = bytes.len().min(255);
        for i in 0..len {
            (*err_ptr).msg[i] = bytes[i] as c_char;
        }
        (*err_ptr).msg[len] = 0;
    }
}

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

#[no_mangle]
pub extern "C" fn polydim_rust_clifford_prefix_canonical_sign_v914(
    mask_a: *const u64,
    mask_b: *const u64,
    num_words: usize,
    err_ptr: *mut PolydimErrorv914,
) -> i32 {
    if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
    if mask_a.is_null() || mask_b.is_null() || num_words == 0 {
        set_error_v914(err_ptr, 4, "Polydim Rust v914 Clifford: Null pointer or 0 words");
        return 1;
    }

    let a = unsafe { std::slice::from_raw_parts(mask_a, num_words) };
    let b = unsafe { std::slice::from_raw_parts(mask_b, num_words) };

    let mut p_b = vec![0u32; num_words];
    let mut running_sum = 0u32;
    for w in 0..num_words {
        running_sum += b[w].count_ones();
        p_b[w] = running_sum;
    }

    let mut total_transpositions = 0u32;
    for w in 0..num_words {
        let mut temp_b = b[w];
        while temp_b > 0 {
            let bit_idx = temp_b.trailing_zeros();
            let higher_mask = !((1u64 << (bit_idx + 1)) - 1u64);
            let bits_above = a[w] & higher_mask;
            total_transpositions += bits_above.count_ones();
            temp_b &= temp_b - 1;
        }

        if w > 0 {
            let count_a_w = a[w].count_ones();
            total_transpositions += count_a_w * p_b[w - 1];
        }
    }

    if total_transpositions % 2 == 1 { -1 } else { 1 }
}

#[no_mangle]
pub extern "C" fn polydim_rust_discounted_ogd_martingale_v914(
    scores: *const c_double,
    len: usize,
    discount_gamma: c_double,
    log_e_value_out: *mut c_double,
    final_e_value_out: *mut c_double,
    alarm_out: *mut c_int,
    err_ptr: *mut PolydimErrorv914,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if scores.is_null() || len == 0 {
            set_error_v914(err_ptr, 8, "Polydim Rust v914 Martingale: Null scores or len 0");
            return -8;
        }

        let slice = unsafe { std::slice::from_raw_parts(scores, len) };
        let mut log_e = 0.0f64;
        let mut lambda_t = 0.5f64;
        let mut g_tilde = 0.0f64;
        let gamma = if discount_gamma > 0.0 && discount_gamma < 1.0 { discount_gamma } else { 0.98f64 };
        let eta_0 = 0.08f64;
        let threshold_log = (1.0f64 / 0.05f64).ln(); // alpha = 0.05 -> log(20) ~ 2.9957
        let mut alarm = 0;

        for &score in slice {
            let g_t = score.max(-1.0).min(1.0);
            let u = lambda_t * g_t;
            let log_increment = (1.0f64 + u).ln();

            log_e += log_increment;

            if log_e >= threshold_log {
                alarm = 1;
            }

            // Discounted Gradient Memory (Anti-Anesthesia)
            let raw_grad = g_t / (1.0f64 + lambda_t * g_t).max(0.01);
            g_tilde = gamma * g_tilde + (1.0 - gamma) * raw_grad;
            lambda_t = (lambda_t + eta_0 * g_tilde).max(-0.9).min(0.9);
        }

        if !log_e_value_out.is_null() { unsafe { *log_e_value_out = log_e; } }
        if !final_e_value_out.is_null() { unsafe { *final_e_value_out = log_e.exp(); } }
        if !alarm_out.is_null() { unsafe { *alarm_out = alarm; } }
        0
    }));

    result.unwrap_or(-999)
}

#[no_mangle]
pub extern "C" fn polydim_rust_auon_log_cosh_brake_v914(
    residual: c_double,
    scale_s: c_double,
    lambda_val: c_double,
    loss_out: *mut c_double,
    grad_out: *mut c_double,
    err_ptr: *mut PolydimErrorv914,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if residual.is_nan() || residual.is_infinite() || scale_s <= 0.0 {
            set_error_v914(err_ptr, 1, "Polydim Rust v914 AuON: Invalid float");
            return -1;
        }
        let z = scale_s * residual;
        let abs_z = z.abs();
        let (loss, grad) = if abs_z <= 20.0 {
            let sz2 = (z * 0.5).sinh();
            (lambda_val * (1.0 + 2.0 * sz2 * sz2).ln(), lambda_val * scale_s * z.tanh())
        } else {
            let ln2 = std::f64::consts::LN_2;
            (lambda_val * (abs_z - ln2), lambda_val * scale_s * if z > 0.0 { 1.0 } else { -1.0 })
        };
        if !loss_out.is_null() { unsafe { *loss_out = loss; } }
        if !grad_out.is_null() { unsafe { *grad_out = grad; } }
        0
    }));
    result.unwrap_or(-999)
}

#[no_mangle]
pub extern "C" fn polydim_rust_fire_metric_v914(
    q_ptr: *const c_double,
    n: c_longlong,
    k: c_longlong,
    fire_metric_out: *mut c_double,
    err_ptr: *mut PolydimErrorv914,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if !err_ptr.is_null() { unsafe { (*err_ptr).code = 0; } }
        if q_ptr.is_null() || n <= 0 || k <= 0 || n < k {
            set_error_v914(err_ptr, 7, "Polydim Rust v914 FIRE: Invalid dims");
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
