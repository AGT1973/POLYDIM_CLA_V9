//! kernel_rust_v903.rs
//! Kernel Topológico y Guardián Numérico Rust POLYDIM V903 (Master Industrial Release)
//! 
//! # Alcance y Fundamentación Matemática V903:
//! 
//! POLYDIM opera directamente en el espacio continuo de variedades latentes de alta dimensión ($S^{D-1}$).
//! 
//! Este módulo Rust proporciona los contratos de invariantes matemáticas más críticos:
//! 1. **Freno Numérico Espectral AuON:** Estabilización en el dominio logarítmico $\log\cosh(z) = \log(1 + 2\sinh^2(z/2))$ para $|z| \le 20$.
//! 2. **Métrica Geodésica Riemanniana en $\mathbb{S}^{D-1}$:** Cálculo numéricamente incondicionado sobre vectores normalizados LASSQ.
//! 3. **Homología Simplicial Exacta:** Verificación de clausura de complejos y cálculo de $\beta_1 = \dim\ker(B_1) - \operatorname{rank}(B_2)$.
//! 4. **Cota de Manifold Secant RIP (Baraniuk–Wakin) & Estimador Multi-K Two-NN:** Verificación en runtime de dimensión intrínseca $d_A$ con prior Gamma conjugado.
//! 5. **CliffordNet 2026 & Interacción Bivectorial:** Producto exterior compacto bivectorial $K(K-1)/2$ y Sparse Rolling Interaction (SRI, S=5).
//! 6. **Iteración Polar Gram Newton–Schulz con Schedule de Reinicio [2,3,2]:** Pre-escalado espectral exacto $\|X\|_F$ y convergencia cúbica.
//! 7. **Métrica FIRE (Frobenius-Isometry Reinitialization):** Monitoreo de drift espectral $\|Q^\top Q - I_K\|_F / \sqrt{K}$.
//! 8. **Protección de Concurrencia FFI V903:** Estructura POD align(64) de 320 bytes y thread_local error state.

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
        let ax = val.abs();
        if ax.is_nan() || ax.is_infinite() {
            return f64::NAN;
        }
        if ax != 0.0 {
            if scale < ax {
                let r = scale / ax;
                ssq = 1.0 + ssq * r * r;
                scale = ax;
            } else {
                let r = ax / scale;
                ssq += r * r;
            }
        }
    }
    scale * ssq.sqrt()
}

// ============================================================================
// 1. GESTIÓN DE ERRORES Y CORTAFUEGOS FFI POD V903 (Thread-Local Isolated)
// ============================================================================

thread_local! {
    static LAST_ERR_STR: RefCell<CString> = RefCell::new(CString::new("").unwrap());
}

#[repr(C, align(64))]
#[derive(Debug, Clone, Copy)]
pub struct V903Error {
    pub code: u32,
    pub msg: [u8; 256],
    pub arena_id: u64,
    pub gen: u64,
    pub _pad: [u8; 40],
}

impl V903Error {
    pub fn write_success(&mut self) {
        self.code = 0;
        self.msg[0] = 0;
        self.arena_id = 0;
        self.gen = 0;
    }

    pub fn write_error(&mut self, code: u32, message: &str) {
        self.code = code;
        self.arena_id = 0;
        self.gen = 0;
        self.msg.fill(0);
        let bytes = message.as_bytes();
        let len = bytes.len().min(255);
        self.msg[..len].copy_from_slice(&bytes[..len]);
    }
}

fn set_last_error(msg: &str) {
    LAST_ERR_STR.with(|cell| {
        let clean_msg = msg.replace('\0', " ");
        let c_str = CString::new(clean_msg).unwrap_or_else(|_| CString::new("Error parsing error string").unwrap());
        *cell.borrow_mut() = c_str;
    });
}

#[no_mangle]
pub extern "C" fn polydim_rust_get_last_error_v903() -> *const c_char {
    LAST_ERR_STR.with(|cell| cell.borrow().as_ptr())
}

#[no_mangle]
pub extern "C" fn polydim_rust_copy_last_error_v903(dst: *mut c_char, cap: usize) -> c_int {
    if dst.is_null() || cap == 0 {
        return -1;
    }
    LAST_ERR_STR.with(|cell| {
        let s = cell.borrow();
        let bytes = s.as_bytes();
        let n = bytes.len().min(cap - 1);
        unsafe {
            std::ptr::copy_nonoverlapping(bytes.as_ptr() as *const c_char, dst, n);
            *dst.add(n) = 0;
        }
        n as c_int
    })
}

#[no_mangle]
pub extern "C" fn polydim_rust_clear_last_error_v903() {
    LAST_ERR_STR.with(|cell| {
        *cell.borrow_mut() = CString::new("").unwrap();
    });
}

// ============================================================================
// 2. FRENO NUMÉRICO ESPECTRAL AuON (Estabilización log-cosh V903)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_auon_log_cosh_brake_v903(
    residual: c_double,
    scale_s: c_double,
    lambda: c_double,
    loss_out: *mut c_double,
    grad_out: *mut c_double,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if loss_out.is_null() || grad_out.is_null() {
            set_last_error("Null pointers passed to auon_log_cosh_brake");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer provided"); } }
            return -1;
        }

        if !residual.is_finite() || !scale_s.is_finite() || !lambda.is_finite() {
            set_last_error("NaN or Infinity in auon_log_cosh_brake inputs");
            if !err.is_null() { unsafe { (*err).write_error(2, "NaN/Inf in inputs"); } }
            return -2;
        }

        if scale_s <= 0.0 || lambda < 0.0 {
            set_last_error("Invalid scale_s <= 0 or lambda < 0");
            if !err.is_null() { unsafe { (*err).write_error(3, "Invalid parameters"); } }
            return -3;
        }

        if scale_s < 1e-12 {
            set_last_error("scale_s below minimum 1e-12");
            if !err.is_null() { unsafe { (*err).write_error(4, "scale_s too small"); } }
            return -4;
        }

        let z = residual / scale_s;
        let abs_z = z.abs();
        let ln2 = std::f64::consts::LN_2;

        let log_cosh_z = if abs_z <= 20.0 {
            let s = (0.5 * abs_z).sinh();
            (2.0 * s * s).ln_1p()
        } else {
            abs_z + (-2.0 * abs_z).exp().ln_1p() - ln2
        };

        let loss = lambda * scale_s * scale_s * log_cosh_z;
        let grad = lambda * scale_s * z.tanh();

        unsafe {
            *loss_out = loss;
            *grad_out = grad;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in auon_log_cosh_brake");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

#[no_mangle]
pub extern "C" fn polydim_rust_auon_matrix_rms_normalize_v903(
    rows: c_uint,
    cols: c_uint,
    matrix_in_ptr: *const c_double,
    matrix_out_ptr: *mut c_double,
    rms_out: *mut c_double,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if matrix_in_ptr.is_null() || matrix_out_ptr.is_null() || rms_out.is_null() {
            set_last_error("Null pointers in auon_matrix_rms_normalize");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let n_elements = match (rows as usize).checked_mul(cols as usize) {
            Some(n) if n > 0 => n,
            _ => {
                set_last_error("Matrix size is 0 or overflows usize");
                if !err.is_null() { unsafe { (*err).write_error(2, "Invalid size"); } }
                return -2;
            }
        };

        let in_slice = unsafe { std::slice::from_raw_parts(matrix_in_ptr, n_elements) };
        let out_slice = unsafe { std::slice::from_raw_parts_mut(matrix_out_ptr, n_elements) };

        for &v in in_slice {
            if !v.is_finite() {
                set_last_error("Non-finite values in matrix input");
                if !err.is_null() { unsafe { (*err).write_error(3, "Non-finite input"); } }
                return -3;
            }
        }

        let ln2 = std::f64::consts::LN_2;
        let mut cosh_sq_sum = 0.0f64;
        for &v in in_slice {
            let a = v.abs();
            let c_sq = if a < 350.0 {
                let e2 = (2.0 * a).exp();
                let e2i = (-2.0 * a).exp();
                (e2 + 2.0 + e2i) * 0.25
            } else {
                (2.0 * (a - ln2)).exp()
            };
            cosh_sq_sum += c_sq;
        }

        let rms = (cosh_sq_sum / (n_elements as f64)).sqrt();
        let scale = 1.0 / (rms + 1e-8);
        for i in 0..n_elements {
            out_slice[i] = in_slice[i] * scale;
        }

        unsafe {
            *rms_out = rms;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in auon_matrix_rms_normalize");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 3. MÉTRICA GEODÉSICA ANGULAR RIEMANNIANA EN S^(D-1) V903
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_riemannian_geodesic_v903(
    u_ptr: *const c_double,
    v_ptr: *const c_double,
    dim: c_uint,
    angular_dist_out: *mut c_double,
    chordal_dist_out: *mut c_double,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if u_ptr.is_null() || v_ptr.is_null() || angular_dist_out.is_null() || chordal_dist_out.is_null() {
            set_last_error("Null pointers in riemannian_geodesic");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let d = dim as usize;
        if d == 0 {
            set_last_error("Dimension cannot be 0");
            if !err.is_null() { unsafe { (*err).write_error(2, "Dimension is 0"); } }
            return -2;
        }

        let u_slice = unsafe { std::slice::from_raw_parts(u_ptr, d) };
        let v_slice = unsafe { std::slice::from_raw_parts(v_ptr, d) };

        let norm_u = lassq_norm(u_slice);
        let norm_v = lassq_norm(v_slice);

        if !norm_u.is_finite() || !norm_v.is_finite() || norm_u < 1e-15 || norm_v < 1e-15 {
            set_last_error("Degenerate or non-finite vector norm in geodesic");
            if !err.is_null() { unsafe { (*err).write_error(3, "Invalid vector norm"); } }
            return -3;
        }

        let inv_u = 1.0 / norm_u;
        let inv_v = 1.0 / norm_v;

        let mut dot = 0.0f64;
        let mut chordal_sq = 0.0f64;

        for i in 0..d {
            let u_normed = u_slice[i] * inv_u;
            let v_normed = v_slice[i] * inv_v;
            dot += u_normed * v_normed;
            let diff = u_normed - v_normed;
            chordal_sq += diff * diff;
        }

        dot = dot.clamp(-1.0, 1.0);
        let chordal_dist = chordal_sq.sqrt();
        let angular_dist = if dot > 0.9999 {
            2.0 * (chordal_dist * 0.5).asin()
        } else {
            dot.acos()
        };

        unsafe {
            *angular_dist_out = angular_dist;
            *chordal_dist_out = chordal_dist;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in riemannian_geodesic");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 4. HOMOLOGÍA SIMPLICIAL EXACTA Y VALIDACIÓN DE COMPLEJOS
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_simplicial_homology_hodge_v903(
    num_vertices: c_uint,
    num_edges: c_uint,
    edges_pairs_ptr: *const c_uint,
    num_triangles: c_uint,
    triangles_ptr: *const c_uint,
    betti0_out: *mut c_uint,
    betti1_simplicial_out: *mut c_longlong,
    graph_cycle_rank_out: *mut c_longlong,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if betti0_out.is_null() || betti1_simplicial_out.is_null() || graph_cycle_rank_out.is_null() {
            set_last_error("Null output pointers in simplicial_homology");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let nv = num_vertices as usize;
        let ne = num_edges as usize;
        let nt = num_triangles as usize;

        if ne > 0 && edges_pairs_ptr.is_null() {
            set_last_error("Null edges pointer with num_edges > 0");
            if !err.is_null() { unsafe { (*err).write_error(2, "Null edges pointer"); } }
            return -2;
        }

        if nt > 0 && triangles_ptr.is_null() {
            set_last_error("Null triangles pointer with num_triangles > 0");
            if !err.is_null() { unsafe { (*err).write_error(3, "Null triangles pointer"); } }
            return -3;
        }

        let edges = if ne > 0 {
            unsafe { std::slice::from_raw_parts(edges_pairs_ptr, ne * 2) }
        } else {
            &[]
        };

        let mut edge_map: std::collections::HashMap<(usize, usize), usize> = std::collections::HashMap::new();
        for e in 0..ne {
            let u = edges[e * 2] as usize;
            let v = edges[e * 2 + 1] as usize;
            if u >= nv || v >= nv || u == v {
                set_last_error("Invalid edge: self-loop or vertex index out of bounds");
                if !err.is_null() { unsafe { (*err).write_error(4, "Invalid edge"); } }
                return -4;
            }
            let key = if u < v { (u, v) } else { (v, u) };
            edge_map.insert(key, e);
        }

        let mut parent: Vec<usize> = (0..nv).collect();
        fn find(parent: &mut [usize], mut i: usize) -> usize {
            while i != parent[i] {
                parent[i] = parent[parent[i]];
                i = parent[i];
            }
            i
        }

        let mut num_components = nv;
        for e in 0..ne {
            let u = edges[e * 2] as usize;
            let v = edges[e * 2 + 1] as usize;
            let root_u = find(&mut parent, u);
            let root_v = find(&mut parent, v);
            if root_u != root_v {
                parent[root_u] = root_v;
                num_components -= 1;
            }
        }

        let b0 = num_components as c_uint;
        let cycle_rank = (ne as i64) - (nv as i64) + (b0 as i64);

        let mut b2_rank = 0usize;
        if nt > 0 {
            let triangles = unsafe { std::slice::from_raw_parts(triangles_ptr, nt * 3) };
            let mut boundary_cols: Vec<Vec<usize>> = Vec::new();

            for t in 0..nt {
                let v0 = triangles[t * 3] as usize;
                let v1 = triangles[t * 3 + 1] as usize;
                let v2 = triangles[t * 3 + 2] as usize;

                if v0 >= nv || v1 >= nv || v2 >= nv || v0 == v1 || v1 == v2 || v0 == v2 {
                    set_last_error("Invalid triangle: duplicate vertex or index out of bounds");
                    if !err.is_null() { unsafe { (*err).write_error(5, "Invalid triangle"); } }
                    return -5;
                }

                let mut v = [v0, v1, v2];
                v.sort_unstable();

                let e01 = edge_map.get(&(v[0], v[1]));
                let e12 = edge_map.get(&(v[1], v[2]));
                let e02 = edge_map.get(&(v[0], v[2]));

                if e01.is_none() || e12.is_none() || e02.is_none() {
                    set_last_error("Simplicial closure violation: triangle references missing boundary edge");
                    if !err.is_null() { unsafe { (*err).write_error(6, "Missing boundary edge"); } }
                    return -6;
                }

                let mut col = vec![*e01.unwrap(), *e12.unwrap(), *e02.unwrap()];
                col.sort_unstable();
                boundary_cols.push(col);
            }

            let mut basis: std::collections::HashMap<usize, Vec<usize>> = std::collections::HashMap::new();
            for mut col in boundary_cols {
                while !col.is_empty() {
                    let pivot = col[col.len() - 1];
                    if let Some(existing) = basis.get(&pivot) {
                        let mut new_col = Vec::new();
                        let mut i = 0;
                        let mut j = 0;
                        while i < col.len() && j < existing.len() {
                            if col[i] == existing[j] {
                                i += 1; j += 1;
                            } else if col[i] < existing[j] {
                                new_col.push(col[i]);
                                i += 1;
                            } else {
                                new_col.push(existing[j]);
                                j += 1;
                            }
                        }
                        while i < col.len() { new_col.push(col[i]); i += 1; }
                        while j < existing.len() { new_col.push(existing[j]); j += 1; }
                        col = new_col;
                    } else {
                        basis.insert(pivot, col);
                        b2_rank += 1;
                        break;
                    }
                }
            }
        }

        let simplicial_b1 = (cycle_rank - (b2_rank as i64)).max(0);

        unsafe {
            *betti0_out = b0;
            *graph_cycle_rank_out = cycle_rank;
            *betti1_simplicial_out = simplicial_b1;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in simplicial_homology");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 5. ESTIMADOR Multi-K / Two-NN DE DIMENSIÓN INTRÍNSECA (Prior Gamma V903)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_two_nn_intrinsic_dim_v903(
    num_pts: c_uint,
    dim: c_uint,
    points_ptr: *const c_double,
    d_intrinsic_mle_out: *mut c_double,
    d_intrinsic_ucb_out: *mut c_double,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if points_ptr.is_null() || d_intrinsic_mle_out.is_null() || d_intrinsic_ucb_out.is_null() {
            set_last_error("Null pointers in two_nn_intrinsic_dim");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let n = num_pts as usize;
        let d = dim as usize;

        if n < 5 || d == 0 {
            set_last_error("Two-NN requires at least 5 points and dim > 0");
            if !err.is_null() { unsafe { (*err).write_error(2, "n < 5 or dim == 0"); } }
            return -2;
        }

        let pts = unsafe { std::slice::from_raw_parts(points_ptr, n * d) };
        let mut mu_values: Vec<f64> = Vec::with_capacity(n);

        for i in 0..n {
            let xi = &pts[i * d..(i + 1) * d];
            let mut dists = Vec::with_capacity(n - 1);

            for j in 0..n {
                if i == j { continue; }
                let xj = &pts[j * d..(j + 1) * d];
                let mut dist_sq = 0.0f64;
                for k in 0..d {
                    let diff = xi[k] - xj[k];
                    dist_sq += diff * diff;
                }
                if dist_sq.is_finite() {
                    dists.push(dist_sq.sqrt());
                }
            }

            dists.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

            let mut k_used = 0;
            while k_used < dists.len() && dists[k_used] <= 1e-12 {
                k_used += 1;
            }

            if k_used + 1 < dists.len() {
                let d1 = dists[k_used];
                let d2 = dists[k_used + 1];
                let mu = d2 / d1;
                
                if mu.is_finite() && mu >= 1.0 {
                    mu_values.push(mu);
                }
            }
        }

        if mu_values.len() < 3 {
            set_last_error("Insufficient valid mu ratios in Two-NN");
            if !err.is_null() { unsafe { (*err).write_error(3, "Degenerate points"); } }
            return -3;
        }

        let n_valid = mu_values.len() as f64;
        let sum_log_mu: f64 = mu_values.iter().map(|&mu| mu.ln()).sum();

        let alpha = 2.0;
        let beta = 1e-3;
        let d_map = (n_valid + alpha - 1.0) / (sum_log_mu + beta);
        let d_ucb = d_map * (1.0 + 1.96 / n_valid.sqrt());

        unsafe {
            *d_intrinsic_mle_out = d_map;
            *d_intrinsic_ucb_out = d_ucb;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in two_nn_intrinsic_dim");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 6. COTA BARANIUK–WAKIN Y FACTIBILIDAD DE PROYECCIÓN V903
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_baraniuk_wakin_feasibility_v903(
    dim_in: c_uint,
    dim_out: c_uint,
    intrinsic_dim: c_double,
    epsilon_dist: c_double,
    reach_tau: c_double,
    volume_v: c_double,
    failure_rho: c_double,
    m_required_out: *mut c_double,
    is_feasible_out: *mut u8,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if m_required_out.is_null() || is_feasible_out.is_null() {
            set_last_error("Null pointers in baraniuk_wakin_feasibility");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        if epsilon_dist <= 0.0 || epsilon_dist >= 1.0 || reach_tau <= 0.0 || failure_rho <= 0.0 || volume_v <= 0.0 {
            set_last_error("Invalid parameters in baraniuk_wakin_feasibility");
            if !err.is_null() { unsafe { (*err).write_error(2, "Invalid params"); } }
            return -2;
        }

        let da = intrinsic_dim.max(1.0);
        let eps = epsilon_dist;
        let tau = reach_tau;
        let v = volume_v;
        let rho = failure_rho;
        let n = dim_in as f64;

        let c_const = 1.0;
        let arg_geo = (v / tau.powf(da)).max(1.0);
        let term_geo = arg_geo.ln();
        let term_eps = da * (1.0 / eps).ln();
        let term_prob = (1.0 / rho).ln();
        let term_ambient = n.ln();

        let m_req = (c_const / (eps * eps)) * (term_geo + term_eps + term_prob + term_ambient);
        let feasible = if (dim_out as f64) >= m_req { 1u8 } else { 0u8 };

        unsafe {
            *m_required_out = m_req;
            *is_feasible_out = feasible;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in baraniuk_wakin_feasibility");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 7. CLIFFORDNET 2026: INTERACCIÓN BIVECTORIAL Y SRI V903
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_cliffordnet_bivector_interact_v903(
    num_vectors: c_uint,
    dim_k: c_uint,
    vectors_in_ptr: *const c_double,
    bivectors_out_ptr: *mut c_double,
    energy_out: *mut c_double,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if vectors_in_ptr.is_null() || bivectors_out_ptr.is_null() || energy_out.is_null() {
            set_last_error("Null pointers in cliffordnet_bivector_interact");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let n = num_vectors as usize;
        let k = dim_k as usize;

        if n == 0 || k < 2 {
            set_last_error("num_vectors > 0 and dim_k >= 2 required");
            if !err.is_null() { unsafe { (*err).write_error(2, "Invalid dimensions"); } }
            return -2;
        }

        let bivec_dim = (k * (k - 1)) / 2;
        let shift_s = 5usize;

        let vecs = unsafe { std::slice::from_raw_parts(vectors_in_ptr, n * k) };
        let bivecs = unsafe { std::slice::from_raw_parts_mut(bivectors_out_ptr, n * bivec_dim) };

        let mut total_energy = 0.0f64;

        for v in 0..n {
            let vec = &vecs[v * k..(v + 1) * k];
            let bivec = &mut bivecs[v * bivec_dim..(v + 1) * bivec_dim];

            let mut idx = 0usize;
            for i in 0..k {
                for j in (i + 1)..k {
                    let b_val = vec[i] * vec[j] - vec[j] * vec[i];
                    let damping = if (j - i) % shift_s == 0 { 1.0 } else { 0.8 };
                    let res = b_val * damping;
                    bivec[idx] = res;
                    idx += 1;
                    total_energy += res * res;
                }
            }
        }

        unsafe {
            *energy_out = (total_energy / ((n * bivec_dim) as f64)).sqrt();
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in cliffordnet_bivector_interact");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 8. ITERACIÓN POLAR GRAM NEWTON–SCHULZ (Schedule [2, 3, 2] V903)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_hybrid_auon_orthogonalization_v903(
    dim_n: c_uint,
    matrix_x_ptr: *const c_double,
    matrix_q_out_ptr: *mut c_double,
    max_total_steps: c_uint,
    steps_executed_out: *mut c_uint,
    is_converged_out: *mut u8,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if matrix_x_ptr.is_null() || matrix_q_out_ptr.is_null() || steps_executed_out.is_null() || is_converged_out.is_null() {
            set_last_error("Null pointers in hybrid_auon_orthogonalization");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let n = dim_n as usize;
        let total_elems = match n.checked_mul(n) {
            Some(t) if t > 0 => t,
            _ => {
                set_last_error("Dimension is 0 or overflows usize");
                if !err.is_null() { unsafe { (*err).write_error(2, "Invalid dim"); } }
                return -2;
            }
        };

        let x_slice = unsafe { std::slice::from_raw_parts(matrix_x_ptr, total_elems) };
        let q_slice = unsafe { std::slice::from_raw_parts_mut(matrix_q_out_ptr, total_elems) };

        q_slice.copy_from_slice(x_slice);

        let s_bound = lassq_norm(q_slice).max(1e-12);
        for v in q_slice.iter_mut() {
            *v /= s_bound;
        }

        let max_steps = (max_total_steps as usize).clamp(1, 30);
        let schedule = [2usize, 3usize, 2usize];
        let mut executed = 0usize;
        let mut converged = false;
        let mut phase = 0usize;

        let mut temp_r = vec![0.0f64; total_elems];
        let mut temp_r2 = vec![0.0f64; total_elems];
        let mut temp_next = vec![0.0f64; total_elems];

        let a = 15.0f64 / 8.0f64;
        let b = -10.0f64 / 8.0f64;
        let c = 3.0f64 / 8.0f64;

        while executed < max_steps {
            let take = schedule[phase].min(max_steps - executed);

            for _ in 0..take {
                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            dot += q_slice[i * n + k] * q_slice[j * n + k];
                        }
                        temp_r[i * n + j] = dot;
                    }
                }

                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            dot += temp_r[i * n + k] * temp_r[k * n + j];
                        }
                        temp_r2[i * n + j] = dot;
                    }
                }

                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            let m_ik = (if i == k { a } else { 0.0 }) + b * temp_r[i * n + k] + c * temp_r2[i * n + k];
                            dot += m_ik * q_slice[k * n + j];
                        }
                        temp_next[i * n + j] = dot;
                    }
                }

                q_slice.copy_from_slice(&temp_next);
                executed += 1;

                let mut frob_err_sq = 0.0f64;
                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            dot += q_slice[k * n + i] * q_slice[k * n + j];
                        }
                        let eye = if i == j { 1.0f64 } else { 0.0f64 };
                        let diff = dot - eye;
                        frob_err_sq += diff * diff;
                    }
                }
                let iso_err = (frob_err_sq / (n as f64)).sqrt();
                if iso_err < 1e-10 {
                    converged = true;
                    break;
                }
            }

            if converged { break; }
            phase = (phase + 1) % schedule.len();
        }

        unsafe {
            *steps_executed_out = executed as c_uint;
            *is_converged_out = if converged { 1 } else { 0 };
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in hybrid_auon_orthogonalization");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 9. MÉTRICA FIRE (Frobenius-Isometry Reinitialization) V903
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_fire_metric_v903(
    dim_d: c_uint,
    rank_k: c_uint,
    q_matrix_ptr: *const c_double,
    drift_threshold: c_double,
    spectral_drift_out: *mut c_double,
    reinit_needed_out: *mut u8,
    err: *mut V903Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if q_matrix_ptr.is_null() || spectral_drift_out.is_null() || reinit_needed_out.is_null() {
            set_last_error("Null pointers in fire_metric");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let d = dim_d as usize;
        let k = rank_k as usize;

        if d == 0 || k == 0 || k > d {
            set_error_msg("Invalid dimensions for FIRE metric");
            if !err.is_null() { unsafe { (*err).write_error(2, "Invalid dimensions"); } }
            return -2;
        }

        let q_slice = unsafe { std::slice::from_raw_parts(q_matrix_ptr, d * k) };

        let mut frob_sq = 0.0f64;
        for i in 0..k {
            for j in 0..k {
                let mut dot = 0.0f64;
                for row in 0..d {
                    dot += q_slice[row * k + i] * q_slice[row * k + j];
                }
                let eye = if i == j { 1.0f64 } else { 0.0f64 };
                let diff = dot - eye;
                frob_sq += diff * diff;
            }
        }

        let drift = (frob_sq / (k as f64)).sqrt();
        let thresh = if drift_threshold > 0.0 { drift_threshold } else { 1e-6 };

        unsafe {
            *spectral_drift_out = drift;
            *reinit_needed_out = if drift > thresh { 1 } else { 0 };
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in fire_metric");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}
