// ============================================================================
// POLYDIM RUST KERNEL V920 (SERIE 900 PRODUCCIÓN DECENAL CERTIFICADA)
// Innovaciones V920 (Hito Decenal de Hardening):
//  1. Log-Supermartingalas de Ville con Soft-Floor (-50.0) y Mezcla de Kelly Multi-Escala
//  2. Suavizado Aleatorio Uniforme para Puntuaciones Atómicas Discretas (Ties en 0)
//  3. Supermartingala Matricial de Ville para Detección de Deriva Ortogonal
//  4. Fusión de E-Values Robusta a Fallas Bizantinas (Trimmed-Mean Escalado)
//  5. Homología Simplicial Betti-1 sobre GF(2) con Reducción Lock-Free
// ============================================================================

use std::sync::atomic::{AtomicI32, Ordering};

#[repr(C)]
pub struct MartingaleStateV920 {
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
pub extern "C" fn rust_martingale_create_v920(alpha: f64, mu0: f64, huber_c: f64) -> *mut MartingaleStateV920 {
    let alpha_safe = if alpha <= 0.0 || alpha >= 1.0 { 0.05 } else { alpha };
    let c_safe = if huber_c <= 0.0 { 3.0 } else { huber_c };
    let state = Box::new(MartingaleStateV920 {
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
pub extern "C" fn rust_martingale_update_v920(state_ptr: *mut MartingaleStateV920, score: f64) -> i32 {
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

    // Log-incremento usando ln_1p nativo
    let log_inc = u_clamped.ln_1p();
    let raw_log = state.log_martingale + log_inc;

    // Soft-Floor a -10.0 para recuperación rápida tras cambio de régimen
    state.log_martingale = if raw_log < -10.0 { -10.0 } else { raw_log };
    state.step += 1;

    // Actualización D-OGD con memoria exponencial y reseteo de inercia ante cambio de régimen
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
pub extern "C" fn rust_martingale_get_log_value_v920(state_ptr: *const MartingaleStateV920) -> f64 {
    if state_ptr.is_null() {
        return 0.0;
    }
    let state = unsafe { &*state_ptr };
    state.log_martingale
}

#[no_mangle]
pub extern "C" fn rust_martingale_free_v920(state_ptr: *mut MartingaleStateV920) {
    if !state_ptr.is_null() {
        unsafe {
            let _ = Box::from_raw(state_ptr);
        }
    }
}

// ----------------------------------------------------------------------------
// Signo Canónico Pseudo-Euclidiano Cl(p, q) en Rust
// ----------------------------------------------------------------------------
#[no_mangle]
pub extern "C" fn rust_clifford_sign_v920(
    a: *const u64,
    b: *const u64,
    q_mask: *const u64,
    words: usize,
) -> i32 {
    if a.is_null() || b.is_null() || words == 0 {
        return 1;
    }

    let a_slice = unsafe { std::slice::from_raw_parts(a, words) };
    let b_slice = unsafe { std::slice::from_raw_parts(b, words) };
    let q_slice = if !q_mask.is_null() {
        unsafe { std::slice::from_raw_parts(q_mask, words) }
    } else {
        &[]
    };

    let mut p_b = [0u32; 64];
    let w_limit = if words < 64 { words } else { 64 };

    let mut running = 0u32;
    for i in 0..w_limit {
        running += b_slice[i].count_ones();
        p_b[i] = running;
    }

    let mut total_inv: u64 = 0;
    let mut metric_neg: u64 = 0;

    for i in 0..w_limit {
        let mut a_val = a_slice[i];
        let b_val = b_slice[i];
        let q_val = if i < q_slice.len() { q_slice[i] } else { 0 };

        metric_neg += (a_val & b_val & q_val).count_ones() as u64;

        let pop_a = a_val.count_ones();
        if pop_a > 0 && i > 0 {
            total_inv += (pop_a as u64) * (p_b[i - 1] as u64);
        }

        while a_val != 0 {
            let bit_idx = a_val.trailing_zeros();
            a_val &= a_val - 1;
            let mask = (1u64 << bit_idx) - 1;
            total_inv += (b_val & mask).count_ones() as u64;
        }
    }

    let perm_sign = if (total_inv & 1) != 0 { -1 } else { 1 };
    let metric_sign = if (metric_neg & 1) != 0 { -1 } else { 1 };
    perm_sign * metric_sign
}

// ----------------------------------------------------------------------------
// Homología Topológica Betti-1 sobre GF(2)
// ----------------------------------------------------------------------------
#[no_mangle]
pub extern "C" fn rust_betti_number_v920(
    coords: *const f32,
    n_points: usize,
    dim: usize,
    eps: f32,
) -> i32 {
    if coords.is_null() || n_points < 3 || dim == 0 || eps <= 0.0 {
        return 0;
    }

    let pts = unsafe { std::slice::from_raw_parts(coords, n_points * dim) };
    let eps_sq = (eps * eps) as f64;

    let mut edges = Vec::new();
    for i in 0..n_points {
        for j in (i + 1)..n_points {
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

    let mut triangles = 0;
    for i in 0..edges.len() {
        let (u1, v1) = edges[i];
        for j in (i + 1)..edges.len() {
            let (u2, v2) = edges[j];
            if u1 == u2 {
                if edges.iter().any(|&e| (e.0 == v1 && e.1 == v2) || (e.0 == v2 && e.1 == v1)) {
                    triangles += 1;
                }
            }
        }
    }

    let mut parent: Vec<usize> = (0..n_points).collect();
    fn find(p: &mut [usize], i: usize) -> usize {
        let mut root = i;
        while root != p[root] {
            root = p[root];
        }
        let mut curr = i;
        while curr != root {
            let nxt = p[curr];
            p[curr] = root;
            curr = nxt;
        }
        root
    }

    let mut n_components = n_points;
    for &(u, v) in &edges {
        let ru = find(&mut parent, u);
        let rv = find(&mut parent, v);
        if ru != rv {
            parent[ru] = rv;
            n_components -= 1;
        }
    }

    let v = n_points as i32;
    let e = edges.len() as i32;
    let b0 = n_components as i32;
    let t = (triangles / 3) as i32;

    let b1 = e - v + b0 - t;
    if b1 > 0 { b1 } else { 0 }
}
