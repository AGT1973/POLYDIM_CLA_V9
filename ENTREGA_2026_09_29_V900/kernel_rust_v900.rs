//! kernel_rust_v900.rs
//! Kernel Topológico y Guardián Numérico Rust POLYDIM V900 (Master Industrial Release)
//! 
//! # Alcance y Fundamentación Matemática para Científicos de Datos e Ingenieros de Sistemas:
//! 
//! POLYDIM opera directamente en el espacio continuo de variedades latentes de alta dimensión ($S^{D-1}$).
//! 
//! Este módulo Rust proporciona los contratos de invariantes matemáticas más críticos:
//! 1. **Freno Numérico Espectral AuON:** Estabilización en el dominio logarítmico $\log\cosh(z) = |z| + \operatorname{log1p}(e^{-2|z|}) - \ln 2$,
//!    con escala RMS Frobenius $\mathrm{rms} = \|\cosh(\text{update})\|_F / \sqrt{N}$ y gradientes analíticos $|\partial \mathcal{L}/\partial r| \le \lambda s$.
//! 2. **Métrica Geodésica Riemanniana en $\mathbb{S}^{D-1}$:** Cálculo numéricamente incondicionado sobre vectores normalizados
//!    $d_{\mathbb{S}}(u,v) = \arccos(\operatorname{clamp}(\hat{u}^\top \hat{v}, -1, 1))$.
//! 3. **Homología Simplicial Exacta:** Verificación estricta de clausura de complejos y cálculo de $\beta_1 = \dim\ker(B_1) - \operatorname{rank}(B_2)$.
//! 4. **Cota de Manifold Secant RIP (Baraniuk–Wakin) & Estimador Two-NN:** Verificación en runtime de la dimensión intrínseca $d_A$
//!    con estimador MLE insesgado $(N-1)/\sum \ln(\mu_i)$.
//! 5. **Iteración Polar Gram Newton–Schulz con Schedule de Reinicio [2,3,2]:** Pre-escalado espectral exacto $\|X\|_F$ y convergencia cúbica local.
//! 6. **Protección de Concurrencia FFI:** Aislamiento de errores por hilo (`thread_local!`), copia segura `copy_last_error` y validación de rangos sin solapamiento.

use std::cell::RefCell;
use std::ffi::CString;
use std::os::raw::{c_char, c_double, c_int, c_longlong, c_uint};
use std::panic::{catch_unwind, AssertUnwindSafe};

// ============================================================================
// HELPERS NUMÉRICOS INCONDICIONADOS (Blue's Algorithm / LASSQ)
// ============================================================================

/// Calcula la norma euclidiana L2 de forma numéricamente incondicionada
/// evitando overflow/underflow prematuro en exponentes hasta 1e308 (LAPACK dlapy2 / lassq).
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
// 1. GESTIÓN DE ERRORES Y CORTAFUEGOS FFI POD (Thread-Local Isolated)
// ============================================================================

thread_local! {
    static LAST_ERR_STR: RefCell<CString> = RefCell::new(CString::new("").unwrap());
}

#[repr(C, align(8))]
#[derive(Debug, Clone, Copy)]
pub struct V900Error {
    pub code: u32,
    pub msg: [u8; 256],
    pub arena_id: u64,
    pub gen: u64,
}

impl V900Error {
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

/// Devuelve un puntero prestado al último error registrado en el hilo llamador.
#[no_mangle]
pub extern "C" fn polydim_rust_get_last_error_v900() -> *const c_char {
    LAST_ERR_STR.with(|cell| cell.borrow().as_ptr())
}

/// Copia segura sin Use-After-Free a un buffer provisto por el llamador.
#[no_mangle]
pub extern "C" fn polydim_rust_copy_last_error_v900(dst: *mut c_char, cap: usize) -> c_int {
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
pub extern "C" fn polydim_rust_clear_last_error_v900() {
    LAST_ERR_STR.with(|cell| {
        *cell.borrow_mut() = CString::new("").unwrap();
    });
}

// ============================================================================
// 2. FRENO NUMÉRICO ESPECTRAL AuON (Estabilización log-cosh Exacta)
// ============================================================================

/// Calcula la pérdida de frenado espectral $\mathcal{L}(x; s, \lambda) = \lambda s^2 \log\cosh(x / s)$
/// en forma numéricamente incondicionada usando la identidad $|z| + \operatorname{log1p}(e^{-2|z|}) - \ln 2$.
/// Su derivada $\partial \mathcal{L}/\partial x = \lambda s \tanh(x / s)$ está analíticamente acotada por $\lambda s$.
#[no_mangle]
pub extern "C" fn polydim_rust_auon_log_cosh_brake_v900(
    residual: c_double,
    scale_s: c_double,
    lambda: c_double,
    loss_out: *mut c_double,
    grad_out: *mut c_double,
    err: *mut V900Error,
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

/// Normalización de matriz AuON: rms = ||cosh(U)||_F / sqrt(N).
#[no_mangle]
pub extern "C" fn polydim_rust_auon_matrix_rms_normalize_v900(
    rows: c_uint,
    cols: c_uint,
    matrix_in_ptr: *const c_double,
    matrix_out_ptr: *mut c_double,
    rms_out: *mut c_double,
    err: *mut V900Error,
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

        // Verificar finitud
        for &v in in_slice {
            if !v.is_finite() {
                set_last_error("Non-finite values in matrix input");
                if !err.is_null() { unsafe { (*err).write_error(3, "Non-finite input"); } }
                return -3;
            }
        }

        // cosh sobre valores originales con rama asintótica anti-overflow
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
// 3. MÉTRICA GEODÉSICA ANGULAR RIEMANNIANA EN S^(D-1)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_riemannian_geodesic_v900(
    u_ptr: *const c_double,
    v_ptr: *const c_double,
    dim: c_uint,
    angular_dist_out: *mut c_double,
    chordal_dist_out: *mut c_double,
    err: *mut V900Error,
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

        // Normalización exacta a la esfera unitaria S^(D-1)
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
        let angular_dist = dot.acos();
        let chordal_dist = chordal_sq.sqrt();

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
pub extern "C" fn polydim_rust_simplicial_homology_hodge_v900(
    num_vertices: c_uint,
    num_edges: c_uint,
    edges_pairs_ptr: *const c_uint,
    num_triangles: c_uint,
    triangles_ptr: *const c_uint,
    betti0_out: *mut c_uint,
    betti1_simplicial_out: *mut c_longlong,
    graph_cycle_rank_out: *mut c_longlong,
    err: *mut V900Error,
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

        // 1. Validar aristas
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

        // 2. DSU para Betti-0
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

        // 3. Validar triángulos y verificar clausura simplicial
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

            // Reducción Gaussiana de columnas frontera sobre GF(2)
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
// 5. ESTIMADOR Two-NN DE DIMENSIÓN INTRÍNSECA (MLE Insesgado)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_two_nn_intrinsic_dim_v900(
    num_pts: c_uint,
    dim: c_uint,
    points_ptr: *const c_double,
    d_intrinsic_mle_out: *mut c_double,
    d_intrinsic_ucb_out: *mut c_double,
    err: *mut V900Error,
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
            let mut d1 = f64::INFINITY;
            let mut d2 = f64::INFINITY;

            for j in 0..n {
                if i == j { continue; }
                let xj = &pts[j * d..(j + 1) * d];
                let mut dist_sq = 0.0f64;
                for k in 0..d {
                    let diff = xi[k] - xj[k];
                    dist_sq += diff * diff;
                }
                let dist = dist_sq.sqrt();

                if dist < d1 {
                    d2 = d1;
                    d1 = dist;
                } else if dist < d2 {
                    d2 = dist;
                }
            }

            if d1 > 1e-15 && d2.is_finite() && d2 >= d1 {
                let mu = d2 / d1;
                if mu.is_finite() && mu > 1.0 + 1e-12 {
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

        if sum_log_mu <= 1e-12 || !sum_log_mu.is_finite() {
            unsafe {
                *d_intrinsic_mle_out = 1.0;
                *d_intrinsic_ucb_out = 1.0;
                if !err.is_null() { (*err).write_success(); }
            }
            return 0;
        }

        // Estimador MLE insesgado: d = (N - 1) / sum(ln(mu))
        let d_mle = (n_valid - 1.0) / sum_log_mu;
        let d_ucb = d_mle * (1.0 + 1.96 / n_valid.sqrt());

        unsafe {
            *d_intrinsic_mle_out = d_mle;
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
// 6. COTA BARANIUK–WAKIN Y FACTIBILIDAD DE PROYECCIÓN
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_baraniuk_wakin_feasibility_v900(
    dim_in: c_uint,
    dim_out: c_uint,
    intrinsic_dim: c_double,
    epsilon_dist: c_double,
    reach_tau: c_double,
    volume_v: c_double,
    failure_rho: c_double,
    m_required_out: *mut c_double,
    is_feasible_out: *mut u8,
    err: *mut V900Error,
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

        let c_const = 1.0; // Hipótesis canónica declarada
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
// 7. ITERACIÓN POLAR GRAM NEWTON–SCHULZ (Schedule [2, 3, 2])
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_gram_ns_polar_restart_v900(
    dim_n: c_uint,
    matrix_x_ptr: *const c_double,
    matrix_q_out_ptr: *mut c_double,
    max_total_steps: c_uint,
    steps_executed_out: *mut c_uint,
    is_converged_out: *mut u8,
    err: *mut V900Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if matrix_x_ptr.is_null() || matrix_q_out_ptr.is_null() || steps_executed_out.is_null() || is_converged_out.is_null() {
            set_last_error("Null pointers in gram_ns_polar_restart");
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

        // Pre-escalado riguroso: cota superior Frobenius exacta ||X||_F
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

        // Coeficientes canónicos de grado 5 con convergencia local cúbica:
        // p(x) = (15x - 10x^3 + 3x^5)/8
        let a = 15.0f64 / 8.0f64;
        let b = -10.0f64 / 8.0f64;
        let c = 3.0f64 / 8.0f64;

        while executed < max_steps {
            let take = schedule[phase].min(max_steps - executed);

            for _ in 0..take {
                // 1. R = Q * Q^T
                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            dot += q_slice[i * n + k] * q_slice[j * n + k];
                        }
                        temp_r[i * n + j] = dot;
                    }
                }

                // 2. R2 = R * R
                for i in 0..n {
                    for j in 0..n {
                        let mut dot = 0.0f64;
                        for k in 0..n {
                            dot += temp_r[i * n + k] * temp_r[k * n + j];
                        }
                        temp_r2[i * n + j] = dot;
                    }
                }

                // 3. M = a*I + b*R + c*R2, Q_next = M * Q
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

                // Test de convergencia ||Q^T Q - I||_F / sqrt(n)
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

            if converged {
                break;
            }
            phase = (phase + 1) % schedule.len();
        }

        unsafe {
            *steps_executed_out = executed as c_uint;
            *is_converged_out = if converged { 1u8 } else { 0u8 };
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in gram_ns_polar_restart");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 8. EVALUADOR DE DISTORSIÓN SECANTE EN VARIEDADES
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_secant_distortion_eval_v900(
    num_pts: c_uint,
    dim_in: c_uint,
    dim_out: c_uint,
    orig_pts_ptr: *const c_double,
    proj_pts_ptr: *const c_double,
    l_min_out: *mut c_double,
    l_max_out: *mut c_double,
    delta_max_out: *mut c_double,
    secant_alpha_out: *mut c_double,
    err: *mut V900Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if orig_pts_ptr.is_null() || proj_pts_ptr.is_null() || l_min_out.is_null() || l_max_out.is_null() || delta_max_out.is_null() || secant_alpha_out.is_null() {
            set_last_error("Null pointers in secant_distortion_eval");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let n = num_pts as usize;
        let din = dim_in as usize;
        let dout = dim_out as usize;

        if n < 2 || din == 0 || dout == 0 {
            set_last_error("At least 2 points required and dims > 0");
            if !err.is_null() { unsafe { (*err).write_error(2, "Invalid dimensions"); } }
            return -2;
        }

        let orig = unsafe { std::slice::from_raw_parts(orig_pts_ptr, n * din) };
        let proj = unsafe { std::slice::from_raw_parts(proj_pts_ptr, n * dout) };

        let mut l_min = f64::INFINITY;
        let mut l_max = 0.0f64;
        let mut delta_max = 0.0f64;

        for i in 0..n {
            let xi = &orig[i * din..(i + 1) * din];
            let yi = &proj[i * dout..(i + 1) * dout];

            for j in (i + 1)..n {
                let xj = &orig[j * din..(j + 1) * din];
                let yj = &proj[j * dout..(j + 1) * dout];

                let mut orig_diff = vec![0.0f64; din];
                for k in 0..din { orig_diff[k] = xi[k] - xj[k]; }
                let orig_dist = lassq_norm(&orig_diff);

                if orig_dist > 1e-12 {
                    let mut proj_diff = vec![0.0f64; dout];
                    for k in 0..dout { proj_diff[k] = yi[k] - yj[k]; }
                    let proj_dist = lassq_norm(&proj_diff);

                    let ratio = proj_dist / orig_dist;
                    if ratio < l_min { l_min = ratio; }
                    if ratio > l_max { l_max = ratio; }

                    let delta = (ratio - 1.0).abs();
                    if delta > delta_max { delta_max = delta; }
                }
            }
        }

        unsafe {
            *l_min_out = l_min;
            *l_max_out = l_max;
            *delta_max_out = delta_max;
            *secant_alpha_out = l_min;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in secant_distortion_eval");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 9. QSBR / MEMORY SNAPSHOT COPY-OUT (Safe Overlap Guard)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_qsbr_snapshot_copy_v900(
    src_ptr: *const u8,
    size_bytes: usize,
    dst_ptr: *mut u8,
    copied_bytes_out: *mut usize,
    err: *mut V900Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if src_ptr.is_null() || dst_ptr.is_null() || copied_bytes_out.is_null() {
            set_last_error("Null pointers in qsbr_snapshot_copy");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        if size_bytes == 0 {
            unsafe {
                *copied_bytes_out = 0;
                if !err.is_null() { (*err).write_success(); }
            }
            return 0;
        }

        let src_addr = src_ptr as usize;
        let dst_addr = dst_ptr as usize;

        // Comprobar solapamiento de memoria
        unsafe {
            if src_addr < dst_addr + size_bytes && dst_addr < src_addr + size_bytes {
                std::ptr::copy(src_ptr, dst_ptr, size_bytes);
            } else {
                std::ptr::copy_nonoverlapping(src_ptr, dst_ptr, size_bytes);
            }
            *copied_bytes_out = size_bytes;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in qsbr_snapshot_copy");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 10. RETRACCIÓN CAYLEY-STIEFEL MATRIX-FREE (Sherman-Morrison-Woodbury)
// ============================================================================

fn solve_linear_system_2k_rust(n_sys: usize, n_rhs: usize, a: &[f64], b: &[f64], x_sol: &mut [f64]) -> bool {
    let cols = n_sys + n_rhs;
    let mut aug = vec![0.0f64; n_sys * cols];
    for i in 0..n_sys {
        for j in 0..n_sys {
            aug[i * cols + j] = a[i * n_sys + j];
        }
        for j in 0..n_rhs {
            aug[i * cols + n_sys + j] = b[i * n_rhs + j];
        }
    }

    let mut scale_ref = 0.0f64;
    for &v in a {
        let x = v.abs();
        if x > scale_ref { scale_ref = x; }
    }
    if scale_ref == 0.0 { scale_ref = 1.0; }
    let abs_tol = 1e-12 * scale_ref;

    for i in 0..n_sys {
        let mut pivot = i;
        let mut max_val = aug[i * cols + i].abs();
        for r in (i + 1)..n_sys {
            let val = aug[r * cols + i].abs();
            if val > max_val {
                max_val = val;
                pivot = r;
            }
        }
        if max_val < abs_tol {
            return false;
        }
        if pivot != i {
            for c in i..cols {
                aug.swap(i * cols + c, pivot * cols + c);
            }
        }
        let pivot_val = aug[i * cols + i];
        for c in i..cols {
            aug[i * cols + c] /= pivot_val;
        }
        for r in 0..n_sys {
            if r != i {
                let factor = aug[r * cols + i];
                for c in i..cols {
                    let sub = factor * aug[i * cols + c];
                    aug[r * cols + c] -= sub;
                }
            }
        }
    }

    for i in 0..n_sys {
        for j in 0..n_rhs {
            x_sol[i * n_rhs + j] = aug[i * cols + n_sys + j];
        }
    }
    true
}

#[no_mangle]
pub extern "C" fn polydim_rust_stiefel_cayley_smw_retraction_v900(
    dim_d: c_uint,
    rank_k: c_uint,
    tau: c_double,
    x_ptr: *const c_double,
    g_ptr: *const c_double,
    y_out: *mut c_double,
    ortho_error_out: *mut c_double,
    err: *mut V900Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if x_ptr.is_null() || g_ptr.is_null() || y_out.is_null() || ortho_error_out.is_null() {
            set_last_error("Null pointer in stiefel_cayley_smw_retraction");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        let d = dim_d as usize;
        let k = rank_k as usize;

        if d == 0 || k == 0 || k > d {
            set_last_error("Invalid dimensions: require 0 < k <= d");
            if !err.is_null() { unsafe { (*err).write_error(2, "Invalid dimensions (k > d)"); } }
            return -2;
        }

        if !tau.is_finite() {
            set_last_error("Non-finite tau in stiefel retraction");
            if !err.is_null() { unsafe { (*err).write_error(3, "tau non-finite"); } }
            return -3;
        }

        let n_sys = 2 * k;
        let x_slice = unsafe { std::slice::from_raw_parts(x_ptr, d * k) };
        let g_slice = unsafe { std::slice::from_raw_parts(g_ptr, d * k) };
        let y_slice = unsafe { std::slice::from_raw_parts_mut(y_out, d * k) };

        // Verificar finitud de entradas
        for idx in 0..(d * k) {
            if !x_slice[idx].is_finite() || !g_slice[idx].is_finite() {
                set_last_error("Non-finite elements in X or G matrix");
                if !err.is_null() { unsafe { (*err).write_error(4, "X or G non-finite"); } }
                return -4;
            }
        }

        // 1. Calcular bloques KxK: A = X^T G, B = X^T X, C = G^T G
        let mut mat_a = vec![0.0f64; k * k];
        let mut mat_b = vec![0.0f64; k * k];
        let mut mat_c = vec![0.0f64; k * k];

        for row in 0..d {
            let xr = &x_slice[row * k..(row + 1) * k];
            let gr = &g_slice[row * k..(row + 1) * k];
            for i in 0..k {
                let xi = xr[i];
                let gi = gr[i];
                for j in 0..k {
                    mat_a[i * k + j] += xi * gr[j];
                    mat_b[i * k + j] += xi * xr[j];
                    mat_c[i * k + j] += gi * gr[j];
                }
            }
        }

        // 2. Verificar ortonormalidad de X (X^T X = I_K)
        let mut x_defect_sq = 0.0f64;
        for i in 0..k {
            for j in 0..k {
                let eye = if i == j { 1.0f64 } else { 0.0f64 };
                let diff = mat_b[i * k + j] - eye;
                x_defect_sq += diff * diff;
            }
        }
        let x_defect = (x_defect_sq / (k as f64)).sqrt();
        if x_defect > 1e-3 {
            set_last_error("Input matrix X is not on Stiefel manifold St(D, K)");
            if !err.is_null() { unsafe { (*err).write_error(5, "Input X not Stiefel"); } }
            return -5;
        }

        // 3. Construir sistema 2K x 2K: M = I_2K - (tau / 2) * [A, -B; C, -A^T]
        let mut mat_m = vec![0.0f64; n_sys * n_sys];
        let half_tau = 0.5 * tau;

        for i in 0..k {
            for j in 0..k {
                let eye = if i == j { 1.0f64 } else { 0.0f64 };
                mat_m[i * n_sys + j] = eye - half_tau * mat_a[i * k + j];
                mat_m[i * n_sys + (k + j)] = half_tau * mat_b[i * k + j];
                mat_m[(k + i) * n_sys + j] = -half_tau * mat_c[i * k + j];
                mat_m[(k + i) * n_sys + (k + j)] = eye + half_tau * mat_a[j * k + i];
            }
        }

        // 4. Construir RHS = [B; A^T] de tamaño 2K x K
        let mut rhs = vec![0.0f64; n_sys * k];
        for i in 0..k {
            for j in 0..k {
                rhs[i * k + j] = mat_b[i * k + j];
                rhs[(k + i) * k + j] = mat_a[j * k + i];
            }
        }

        // 5. Resolver sistema lineal M * Z = RHS
        let mut mat_z = vec![0.0f64; n_sys * k];
        if !solve_linear_system_2k_rust(n_sys, k, &mat_m, &rhs, &mut mat_z) {
            set_last_error("Matrix M is singular or ill-conditioned in SMW retraction");
            if !err.is_null() { unsafe { (*err).write_error(6, "Matrix M singular"); } }
            return -6;
        }

        // 6. Reconstruir Y = X + tau * (G * Z1 - X * Z2)
        for row in 0..d {
            let xr = &x_slice[row * k..(row + 1) * k];
            let gr = &g_slice[row * k..(row + 1) * k];
            let yr = &mut y_slice[row * k..(row + 1) * k];

            for col in 0..k {
                let mut sum_g = 0.0f64;
                let mut sum_x = 0.0f64;
                for j in 0..k {
                    sum_g += gr[j] * mat_z[j * k + col];
                    sum_x += xr[j] * mat_z[(k + j) * k + col];
                }
                yr[col] = xr[col] + tau * (sum_g - sum_x);
            }
        }

        // 7. Computar error de ortonormalidad de salida: ||Y^T Y - I_K||_F / sqrt(K)
        let mut yty = vec![0.0f64; k * k];
        for row in 0..d {
            let yr = &y_slice[row * k..(row + 1) * k];
            for i in 0..k {
                let yi = yr[i];
                for j in 0..k {
                    yty[i * k + j] += yi * yr[j];
                }
            }
        }

        let mut frob_sq = 0.0f64;
        for i in 0..k {
            for j in 0..k {
                let eye = if i == j { 1.0f64 } else { 0.0f64 };
                let diff = yty[i * k + j] - eye;
                frob_sq += diff * diff;
            }
        }
        let ortho_err = (frob_sq / (k as f64)).sqrt();

        unsafe {
            *ortho_error_out = ortho_err;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in stiefel_cayley_smw_retraction");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}

// ============================================================================
// 11. COTA ASINTÓTICA RIEMANNIANA DE DRIFT CLIFFORD (Higham 2002)
// ============================================================================

#[no_mangle]
pub extern "C" fn polydim_rust_clifford_drift_bound_v900(
    dim_d: c_uint,
    num_reflections_m: c_uint,
    reorth_interval_k: c_uint,
    eps_mach: c_double,
    unconditioned_bound_out: *mut c_double,
    reorth_bound_out: *mut c_double,
    is_safe_under_1e8_out: *mut u8,
    err: *mut V900Error,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if unconditioned_bound_out.is_null() || reorth_bound_out.is_null() || is_safe_under_1e8_out.is_null() {
            set_last_error("Null pointer in clifford_drift_bound");
            if !err.is_null() { unsafe { (*err).write_error(1, "Null pointer"); } }
            return -1;
        }

        if dim_d == 0 || num_reflections_m == 0 {
            set_last_error("dim_d and num_reflections_m must be > 0");
            if !err.is_null() { unsafe { (*err).write_error(2, "dim_d and m must be > 0"); } }
            return -2;
        }

        let d = dim_d as f64;
        let m = num_reflections_m as f64;
        let emach = if eps_mach > 0.0 { eps_mach } else { 2.220446049250313e-16 };
        let c_const = 2.0;

        let unconditioned = c_const * m * d.sqrt() * emach;

        let k_step = (reorth_interval_k as f64).clamp(1.0, m);
        let num_blocks = (m / k_step).ceil();
        let block_drift = c_const * k_step * d.sqrt() * emach;
        let qr_drift = 2.0 * d.sqrt() * emach;
        let reorth = num_blocks * qr_drift + block_drift;

        let is_safe = if reorth < 1e-8 { 1u8 } else { 0u8 };

        unsafe {
            *unconditioned_bound_out = unconditioned;
            *reorth_bound_out = reorth;
            *is_safe_under_1e8_out = is_safe;
            if !err.is_null() { (*err).write_success(); }
        }

        0
    }));

    result.unwrap_or_else(|_| {
        set_last_error("Panic caught in clifford_drift_bound");
        if !err.is_null() { unsafe { (*err).write_error(99, "Panic unwind caught"); } }
        -99
    })
}
