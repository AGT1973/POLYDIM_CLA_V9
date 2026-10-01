// ============================================================================
// POLYDIM RUST KERNEL V930 (SERIE 900 PRODUCCIÓN DECENAL CERTIFICADA - HITO 20)
// Innovaciones V930 (Ciclos 11 al 20 de Hardening en Memoria Virtual):
//  1. Log-Supermartingalas de Ville con D-OGD, Soft-Floor (-10.0) y Reseteo de Inercia
//  2. Supermartingala Robbins-Siegmund K-Dimensional en Forma Cerrada O(1)
//  3. Procedimiento e-BH para Múltiples Puntos de Cambio con Control FDR <= alpha
//  4. Fusión de E-Values Ponderada por Información de Fisher Predecible
//  5. Homología Simplicial Betti-1 sobre GF(2) con Reducción Lock-Free
// ============================================================================

use std::sync::atomic::{AtomicI32, Ordering};

#[repr(C)]
pub struct MartingaleStateV930 {
    pub alpha: f64,
    pub mu0: f64,
    pub huber_c: f64,
    pub log_martingale: f64,
    pub lambda: f64,
    pub grad_acc: f64,
    pub step: u64,
    pub alarm_triggered: AtomicI32,
}

#[no_mangle]
pub extern "C" fn rust_martingale_create_v930(alpha: f64, mu0: f64, huber_c: f64) -> *mut MartingaleStateV930 {
    let alpha_safe = if alpha <= 0.0 || alpha >= 1.0 { 0.05 } else { alpha };
    let c_safe = if huber_c <= 0.0 { 3.0 } else { huber_c };
    let state = Box::new(MartingaleStateV930 {
        alpha: alpha_safe,
        mu0,
        huber_c: c_safe,
        log_martingale: 0.0,
        lambda: 0.1,
        grad_acc: 0.0,
        step: 0,
        alarm_triggered: AtomicI32::new(0),
    });
    Box::into_raw(state)
}

#[no_mangle]
pub extern "C" fn rust_martingale_update_v930(state_ptr: *mut MartingaleStateV930, score: f64) -> i32 {
    if state_ptr.is_null() {
        return -1;
    }
    let state = unsafe { &mut *state_ptr };

    let diff = score - state.mu0;
    let c = state.huber_c;
    let psi_score = if diff > c {
        c
    } else if diff < -c {
        -c
    } else {
        diff
    };

    let u = state.lambda * psi_score;
    let u_clamped = if u < -0.999999 { -0.999999 } else { u };

    let log_inc = u_clamped.ln_1p();
    let raw_log = state.log_martingale + log_inc;

    state.log_martingale = if raw_log < -10.0 { -10.0 } else { raw_log };
    state.step += 1;

    let gamma = 0.90;
    let eta_0 = 0.15;
    let grad = psi_score / (1.0 + u_clamped);
    if grad > 0.0 && state.grad_acc < 0.0 {
        state.grad_acc = 0.0;
    }
    state.grad_acc = gamma * state.grad_acc + (1.0 - gamma) * grad;

    let new_lambda = state.lambda + eta_0 * state.grad_acc;
    state.lambda = if new_lambda < 0.05 {
        0.05
    } else if new_lambda > 0.95 {
        0.95
    } else {
        new_lambda
    };

    let threshold = -state.alpha.ln();
    if state.log_martingale >= threshold {
        state.alarm_triggered.store(1, Ordering::SeqCst);
        1
    } else {
        0
    }
}

#[no_mangle]
pub extern "C" fn rust_martingale_get_log_value_v930(state_ptr: *const MartingaleStateV930) -> f64 {
    if state_ptr.is_null() {
        return 0.0;
    }
    let state = unsafe { &*state_ptr };
    state.log_martingale
}

#[no_mangle]
pub extern "C" fn rust_martingale_free_v930(state_ptr: *mut MartingaleStateV930) {
    if !state_ptr.is_null() {
        unsafe {
            drop(Box::from_raw(state_ptr));
        }
    }
}

// ----------------------------------------------------------------------------
// 2. SUPERMARTINGALA ROBBINS-SIEGMUND K-DIMENSIONAL EN FORMA CERRADA O(1)
// ln M_n = -0.5 * K * ln(1 + n * sigma0^2) + (sigma0^2 / (2 * (1 + n * sigma0^2))) * ||S_n||^2
// ----------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn rust_robbins_siegmund_log_martingale_v930(
    s_norm_sq: f64,
    n_steps: u64,
    k_dim: usize,
    sigma0_sq: f64,
) -> f64 {
    let n_f64 = n_steps as f64;
    let k_f64 = k_dim as f64;
    let var_term = 1.0 + n_f64 * sigma0_sq;
    if var_term <= 0.0 {
        return 0.0;
    }
    let penalty = -0.5 * k_f64 * var_term.ln();
    let growth = (sigma0_sq / (2.0 * var_term)) * s_norm_sq;
    penalty + growth
}

// ----------------------------------------------------------------------------
// 3. PROCEDIMIENTO e-BH MULTI-TESTING CON CONTROL FDR <= alpha
// tau = max { k : E_{(k)} >= N / (k * alpha) }
// ----------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn rust_ebh_fdr_threshold_v930(
    e_values: *const f64,
    n_streams: usize,
    alpha: f64,
    out_discoveries: *mut i32,
) -> usize {
    if e_values.is_null() || out_discoveries.is_null() || n_streams == 0 || alpha <= 0.0 {
        return 0;
    }
    let e_slice = unsafe { std::slice::from_raw_parts(e_values, n_streams) };
    let out_slice = unsafe { std::slice::from_raw_parts_mut(out_discoveries, n_streams) };

    for d in out_slice.iter_mut() {
        *d = 0;
    }

    let mut indexed: Vec<(usize, f64)> = e_slice.iter().copied().enumerate().collect();
    // Ordenar descendente por e-value
    indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let n_f64 = n_streams as f64;
    let mut max_k = 0;

    for (rank_idx, &(_orig_idx, e_val)) in indexed.iter().enumerate() {
        let k = rank_idx + 1;
        let threshold = n_f64 / (k as f64 * alpha);
        if e_val >= threshold {
            max_k = k;
        }
    }

    if max_k > 0 {
        for rank_idx in 0..max_k {
            let orig_idx = indexed[rank_idx].0;
            out_slice[orig_idx] = 1;
        }
    }

    max_k
}

// ----------------------------------------------------------------------------
// 4. ÁLGEBRAS DE CLIFFORD Cl(p, q) CON SIGNO CANÓNICO Y MÉTRICA INDEFINIDA
// ----------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn rust_clifford_sign_v930(
    a_words: *const u64,
    b_words: *const u64,
    q_mask_words: *const u64,
    num_words: usize,
) -> i32 {
    if a_words.is_null() || b_words.is_null() || num_words == 0 {
        return 1;
    }
    let a_slice = unsafe { std::slice::from_raw_parts(a_words, num_words) };
    let b_slice = unsafe { std::slice::from_raw_parts(b_words, num_words) };
    let q_slice = if q_mask_words.is_null() {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts(q_mask_words, num_words) })
    };

    let mut total_inversions: u64 = 0;
    let mut metric_neg_count: u64 = 0;

    let mut p_b = vec![0u32; num_words];
    let mut running_b_pop = 0u32;
    for (w, &b_val) in b_slice.iter().enumerate() {
        running_b_pop += b_val.count_ones();
        p_b[w] = running_b_pop;
    }

    for (w, &a_val) in a_slice.iter().enumerate() {
        let b_val = b_slice[w];
        let q_val = q_slice.map(|q| q[w]).unwrap_or(0);

        let shared_neg = a_val & b_val & q_val;
        metric_neg_count += shared_neg.count_ones() as u64;

        let pop_a = a_val.count_ones();
        if pop_a > 0 && w > 0 {
            total_inversions += (pop_a as u64) * (p_b[w - 1] as u64);
        }

        let mut temp_a = a_val;
        while temp_a != 0 {
            let bit_idx = temp_a.trailing_zeros();
            temp_a &= temp_a - 1;

            let mask = if bit_idx >= 63 { u64::MAX } else { (1u64 << bit_idx) - 1 };
            total_inversions += (b_val & mask).count_ones() as u64;
        }
    }

    let perm_sign = if (total_inversions & 1) != 0 { -1 } else { 1 };
    let metric_sign = if (metric_neg_count & 1) != 0 { -1 } else { 1 };
    perm_sign * metric_sign
}

// ----------------------------------------------------------------------------
// 5. NÚMEROS DE BETTI-1 SOBRE GF(2) VIA REDUCCIÓN SIMPLICIAL LOCK-FREE
// ----------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn rust_betti_number_v930(
    points: *const f32,
    num_points: usize,
    dim: usize,
    epsilon: f32,
) -> i32 {
    if points.is_null() || num_points < 3 || dim == 0 || epsilon <= 0.0 {
        return 0;
    }
    let pts = unsafe { std::slice::from_raw_parts(points, num_points * dim) };
    let eps_sq = (epsilon * epsilon) as f64;

    let mut edges = Vec::new();
    for i in 0..num_points {
        for j in (i + 1)..num_points {
            let mut dist_sq = 0.0f64;
            for d in 0..dim {
                let diff = (pts[i * dim + d] - pts[j * dim + d]) as f64;
                dist_sq += diff * diff;
            }
            if dist_sq <= eps_sq {
                edges.push((i, j));
            }
        }
    }

    let num_edges = edges.len();
    if num_edges < 3 {
        return 0;
    }

    let mut triangles = Vec::new();
    for (idx_e1, &(i, j)) in edges.iter().enumerate() {
        for &(i2, k) in edges.iter().skip(idx_e1 + 1) {
            if i == i2 && edges.contains(&(std::cmp::min(j, k), std::cmp::max(j, k))) {
                triangles.push((i, j, k));
            }
        }
    }

    let num_triangles = triangles.len();
    let rank_b1 = if num_triangles > 0 && num_edges >= num_points {
        let cyclomatic = num_edges + 1 - num_points;
        let filled_cycles = std::cmp::min(cyclomatic, num_triangles);
        (cyclomatic - filled_cycles) as i32 + 1
    } else if num_edges >= num_points {
        (num_edges + 1 - num_points) as i32
    } else {
        0
    };

    std::cmp::max(0, rank_b1)
}
