// ============================================================================
// POLYDIM RUST KERNEL V1101 (SERIE 900 PRODUCCION CERTIFICADA - GF(2) BETTI-1)
// Compilador: rustc 1.80+ cdylib -C opt-level=3
// ============================================================================

use std::slice;
use std::cell::RefCell;
use std::ffi::CString;
use std::os::raw::c_char;
use std::panic::{catch_unwind, AssertUnwindSafe};

thread_local! {
    static LAST_ERROR: RefCell<Option<CString>> = RefCell::new(None);
}

fn set_last_error(err: &str) {
    LAST_ERROR.with(|e| {
        *e.borrow_mut() = CString::new(err).ok();
    });
}

#[no_mangle]
pub extern "C" fn polydim_last_error_v1100() -> *const c_char {
    LAST_ERROR.with(|e| {
        match e.borrow().as_ref() {
            Some(cstr) => cstr.as_ptr(),
            None => std::ptr::null(),
        }
    })
}

// 1. MARTINGALA ROBBINS-SIEGMUND CONFORME CON ACUMULACIÓN F64 Y SCHEDULE ANTI-ESTANCAMIENTO
#[no_mangle]
pub unsafe extern "C" fn polydim_robbins_siegmund_conformal_v1100(
    losses: *const f32,
    alpha: f32,
    out_v: *mut f32,
    t_len: i32,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if losses.is_null() || out_v.is_null() || t_len <= 0 || !alpha.is_finite() {
            set_last_error("Null pointer or invalid parameters in robbins_siegmund");
            return -1;
        }
        let loss_slice = slice::from_raw_parts(losses, t_len as usize);
        let out_slice = slice::from_raw_parts_mut(out_v, t_len as usize);

        const V_MIN: f64 = 1.0e-6;
        const V_MAX: f64 = 10.0;
        const GAMMA_MIN: f64 = 1.0e-4;
        const BETA_MIN: f64 = 0.5 * GAMMA_MIN;

        let alpha_d = alpha as f64;
        let mut v = 1.0_f64;

        for t in 0..(t_len as usize) {
            let l_raw = loss_slice[t];
            let l = if l_raw.is_finite() { l_raw as f64 } else { alpha_d };

            let denom = (t as f64) + 2.0;
            let gamma_t = (1.0_f64 / denom).max(GAMMA_MIN);
            let beta_t = (0.5_f64 / denom).max(BETA_MIN);

            let drift = (l - alpha_d).tanh();
            v = (1.0_f64 - gamma_t) * v + beta_t * drift;
            v = v.clamp(V_MIN, V_MAX);

            out_slice[t] = v as f32;
        }
        0
    }));

    match result {
        Ok(code) => code,
        Err(_) => {
            set_last_error("Panic caught in polydim_robbins_siegmund_conformal_v1100");
            -3
        }
    }
}

// 2. CONCENTRACIÓN MATRICIAL DE FREEDMAN-TROPP (VARIACIÓN CUADRÁTICA MATRICIAL E ITERACIÓN DE POTENCIAS)
#[no_mangle]
pub unsafe extern "C" fn polydim_matrix_freedman_tropp_v1100(
    matrices: *const f32,
    t_len: i32,
    d: i32,
    u_thresh: f32,
    out_drift: *mut f32,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if matrices.is_null() || out_drift.is_null() || t_len <= 0 || d <= 0 || d > 64 {
            set_last_error("Null pointer or invalid dimensions (d must be in 1..64) in matrix_freedman_tropp");
            return -1;
        }
        let t_u = t_len as usize;
        let d_u = d as usize;
        let n_sq = d_u * d_u;
        let total_elems = t_u * n_sq;
        let mat_slice = slice::from_raw_parts(matrices, total_elems);

        // Buffers f64 fijos en stack sin asignación en heap
        let mut sum_mat = [0.0_f64; 64 * 64];
        let mut var_mat = [0.0_f64; 64 * 64];

        for t in 0..t_u {
            let offset = t * n_sq;
            let x = &mat_slice[offset..(offset + n_sq)];

            // 1. S += X_t
            for q in 0..n_sq {
                let val = x[q] as f64;
                if val.is_finite() {
                    sum_mat[q] += val;
                }
            }

            // 2. V += X_t * X_t (producto matricial simetrizado en f64)
            for i in 0..d_u {
                for j in 0..d_u {
                    let mut acc = 0.0_f64;
                    for p in 0..d_u {
                        let x_ip = 0.5_f64 * ((x[i * d_u + p] as f64) + (x[p * d_u + i] as f64));
                        let x_pj = 0.5_f64 * ((x[p * d_u + j] as f64) + (x[j * d_u + p] as f64));
                        acc += x_ip * x_pj;
                    }
                    var_mat[i * d_u + j] += acc;
                }
            }
        }

        // 3. Estimación de autovalor dominante de V via power iteration
        let mut q_vec = [1.0_f64 / (d_u as f64).sqrt(); 64];
        let mut y_vec = [0.0_f64; 64];

        for _ in 0..60 {
            for i in 0..d_u {
                let mut s = 0.0_f64;
                for j in 0..d_u {
                    s += var_mat[i * d_u + j] * q_vec[j];
                }
                y_vec[i] = s;
            }
            let mut norm_sq = 0.0_f64;
            for i in 0..d_u {
                norm_sq += y_vec[i] * y_vec[i];
            }
            let norm = norm_sq.sqrt();
            if norm < 1e-12_f64 || !norm.is_finite() {
                break;
            }
            for i in 0..d_u {
                q_vec[i] = y_vec[i] / norm;
            }
        }

        let mut lambda_v = 0.0_f64;
        for i in 0..d_u {
            let mut row_dot = 0.0_f64;
            for j in 0..d_u {
                row_dot += var_mat[i * d_u + j] * q_vec[j];
            }
            lambda_v += q_vec[i] * row_dot;
        }
        lambda_v = lambda_v.max(0.0_f64);

        // 4. Cota exponencial de Freedman-Tropp: P(lambda_max(S) >= u) <= d * exp( -u^2 / (2*(lambda_v + R*u/3)) )
        let u = (u_thresh as f64).abs();
        let r_bound = 1.0_f64; // Cota de norma de operador ||X_k|| <= R
        let denom = 2.0_f64 * (lambda_v + r_bound * u / 3.0_f64);

        let p_tail = if u == 0.0_f64 {
            1.0_f64
        } else if denom <= 1e-12_f64 {
            0.0_f64
        } else {
            ((d_u as f64) * (-(u * u) / denom).exp()).min(1.0_f64)
        };

        // Salida: probabilidad de cola de Freedman-Tropp (o indicador de deriva si p_tail < 0.05)
        *out_drift = if p_tail.is_finite() { p_tail as f32 } else { 1.0f32 };
        0
    }));

    match result {
        Ok(code) => code,
        Err(_) => {
            set_last_error("Panic caught in polydim_matrix_freedman_tropp_v1100");
            -3
        }
    }
}

// 3. QEMD SIFT (DESCOMPOSICIÓN CUATERNISÓNICA CON REGULARIZACIÓN SMOOTHSTEP Y CLAMPING DE GANANCIA)
#[no_mangle]
pub unsafe extern "C" fn polydim_qemd_sift_v1100(
    q_signal: *const f32,
    out_imf: *mut f32,
    d: i32,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if q_signal.is_null() || out_imf.is_null() || d <= 0 || (d % 4 != 0) {
            set_last_error("Invalid parameters or non-multiple of 4 in qemd_sift");
            return -1;
        }
        let in_slice = slice::from_raw_parts(q_signal, d as usize);
        let out_slice = slice::from_raw_parts_mut(out_imf, d as usize);

        let num_quats = (d / 4) as usize;
        let mut total_mag = 0.0_f64;

        for q in 0..num_quats {
            let w = in_slice[q * 4 + 0] as f64;
            let x = in_slice[q * 4 + 1] as f64;
            let y = in_slice[q * 4 + 2] as f64;
            let z = in_slice[q * 4 + 3] as f64;
            let mag_sq = w * w + x * x + y * y + z * z;
            if mag_sq.is_finite() {
                total_mag += mag_sq.sqrt();
            }
        }
        let mean_mag = total_mag / (num_quats as f64).max(1.0_f64);

        const EPS: f64 = 1e-6;
        const MAX_GAIN: f64 = 10.0;

        for q in 0..num_quats {
            let w = in_slice[q * 4 + 0] as f64;
            let x = in_slice[q * 4 + 1] as f64;
            let y = in_slice[q * 4 + 2] as f64;
            let z = in_slice[q * 4 + 3] as f64;

            let mag_sq = w * w + x * x + y * y + z * z;
            let mag = if mag_sq.is_finite() { mag_sq.sqrt() } else { 0.0_f64 };

            // Smoothstep taper: t * t * (3 - 2t) sobre [0, EPS]
            let taper = if mag <= 0.0_f64 {
                0.0_f64
            } else if mag >= EPS {
                1.0_f64
            } else {
                let t = mag / EPS;
                t * t * (3.0_f64 - 2.0_f64 * t)
            };

            let env = 0.5_f64 * (mag + mean_mag);
            let denom = mag.max(EPS);
            let raw_scale = (mag - env) / denom;
            let scale = taper * raw_scale.clamp(-MAX_GAIN, MAX_GAIN);

            out_slice[q * 4 + 0] = (w * scale) as f32;
            out_slice[q * 4 + 1] = (x * scale) as f32;
            out_slice[q * 4 + 2] = (y * scale) as f32;
            out_slice[q * 4 + 3] = (z * scale) as f32;
        }
        0
    }));

    match result {
        Ok(code) => code,
        Err(_) => {
            set_last_error("Panic caught in polydim_qemd_sift_v1100");
            -3
        }
    }
}

// 4. ESTRUCTURA UNION-FIND PARA TOPOLOGÍA
struct DisjointSet {
    parent: Vec<usize>,
    rank: Vec<usize>,
    count: usize,
}

impl DisjointSet {
    fn new(n: usize) -> Self {
        DisjointSet {
            parent: (0..n).collect(),
            rank: vec![0; n],
            count: n,
        }
    }

    fn find(&mut self, i: usize) -> usize {
        let mut root = i;
        while root != self.parent[root] {
            root = self.parent[root];
        }
        let mut curr = i;
        while curr != root {
            let next = self.parent[curr];
            self.parent[curr] = root;
            curr = next;
        }
        root
    }

    fn union(&mut self, i: usize, j: usize) -> bool {
        let root_i = self.find(i);
        let root_j = self.find(j);
        if root_i != root_j {
            if self.rank[root_i] < self.rank[root_j] {
                self.parent[root_i] = root_j;
            } else if self.rank[root_i] > self.rank[root_j] {
                self.parent[root_j] = root_i;
            } else {
                self.parent[root_j] = root_i;
                self.rank[root_i] += 1;
            }
            self.count -= 1;
            true
        } else {
            false
        }
    }
}

// 5. PRIMER NÚMERO DE BETTI EXACTO EN VIETORIS-RIPS CON ELIMINACIÓN GF(2)
#[no_mangle]
pub unsafe extern "C" fn polydim_betti1_rips_v1100(
    points: *const f32,
    n: i32,
    d: i32,
    eps: f32,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if points.is_null() || n <= 0 || d <= 0 {
            set_last_error("Null pointer or invalid dimensions in betti1_rips");
            return -1;
        }
        let pt_slice = slice::from_raw_parts(points, (n * d) as usize);
        let n_u = n as usize;
        let d_u = d as usize;

        let mut uf = DisjointSet::new(n_u);
        let mut edges = Vec::new();
        let mut edge_map = std::collections::HashMap::new();

        for i in 0..n_u {
            for j in (i + 1)..n_u {
                let mut dist_sq = 0.0f32;
                for k in 0..d_u {
                    let diff = pt_slice[i * d_u + k] - pt_slice[j * d_u + k];
                    dist_sq += diff * diff;
                }
                if dist_sq <= eps * eps {
                    let e_idx = edges.len();
                    edges.push((i, j));
                    edge_map.insert((i, j), e_idx);
                    uf.union(i, j);
                }
            }
        }

        let num_v = n as i32;
        let num_e = edges.len();
        let num_c = uf.count as i32;
        let cycle_dim = (num_e as i32) - num_v + num_c;
        if cycle_dim <= 0 {
            return 0;
        }

        // Enumerar 2-símplices (triángulos) y construir vectores columna de borde sobre GF(2)
        let num_words = (num_e + 63) / 64;
        let mut boundary_cols: Vec<Vec<u64>> = Vec::new();

        for i in 0..n_u {
            for j in (i + 1)..n_u {
                if !edge_map.contains_key(&(i, j)) { continue; }
                for k in (j + 1)..n_u {
                    if let (Some(&e1), Some(&e2), Some(&e3)) = (
                        edge_map.get(&(i, j)),
                        edge_map.get(&(i, k)),
                        edge_map.get(&(j, k))
                    ) {
                        let mut col = vec![0u64; num_words];
                        col[e1 / 64] ^= 1u64 << (e1 % 64);
                        col[e2 / 64] ^= 1u64 << (e2 % 64);
                        col[e3 / 64] ^= 1u64 << (e3 % 64);
                        boundary_cols.push(col);
                    }
                }
            }
        }

        // Eliminación Gaussiana sobre GF(2) para calcular rank(partial_2) exacto
        let mut pivots: std::collections::HashMap<usize, Vec<u64>> = std::collections::HashMap::new();
        let mut rank_partial2 = 0;

        for mut col in boundary_cols {
            loop {
                // Encontrar el bit más significativo (leading 1)
                let mut lead_bit = None;
                for w in (0..num_words).rev() {
                    if col[w] != 0 {
                        let bit_pos = 63 - col[w].leading_zeros() as usize;
                        lead_bit = Some(w * 64 + bit_pos);
                        break;
                    }
                }

                match lead_bit {
                    None => break, // Columna reducida a 0 (dependiente)
                    Some(bit) => {
                        if let Some(pivot_vec) = pivots.get(&bit) {
                            // XOR con el vector pivote existente y continuar reduciendo
                            for w in 0..num_words {
                                col[w] ^= pivot_vec[w];
                            }
                            continue;
                        } else {
                            // Nuevo pivote independiente encontrado
                            pivots.insert(bit, col);
                            rank_partial2 += 1;
                            break;
                        }
                    }
                }
            }
        }

        let b1 = (cycle_dim - rank_partial2 as i32).max(0);
        b1
    }));

    match result {
        Ok(code) => code,
        Err(_) => {
            set_last_error("Panic caught in polydim_betti1_rips_v1100");
            -3
        }
    }
}

// 6. ROTOR DE CLIFFORD SPIN(D) CON REORTOGONALIZACIÓN "TWICE-IS-ENOUGH" Y ACTUALIZACIÓN PLANAR DE RANGO 2
#[no_mangle]
pub unsafe extern "C" fn polydim_clifford_rotor_spin_v1100(
    x: *const f32,
    bivector_u: *const f32,
    bivector_v: *const f32,
    theta: f32,
    out_x: *mut f32,
    d: i32,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if x.is_null() || bivector_u.is_null() || bivector_v.is_null() || out_x.is_null() || d <= 0 {
            set_last_error("Null pointer or invalid dimensions in clifford_rotor");
            return -1;
        }
        let d_u = d as usize;
        let x_s = slice::from_raw_parts(x, d_u);
        let u_s = slice::from_raw_parts(bivector_u, d_u);
        let v_s = slice::from_raw_parts(bivector_v, d_u);
        let out_s = slice::from_raw_parts_mut(out_x, d_u);

        // 1. Norma en f64 de u
        let mut u_norm_sq = 0.0_f64;
        let mut v_norm_sq = 0.0_f64;
        for i in 0..d_u {
            let u_val = u_s[i] as f64;
            let v_val = v_s[i] as f64;
            u_norm_sq += u_val * u_val;
            v_norm_sq += v_val * v_val;
        }
        let nu = u_norm_sq.sqrt();
        let nv = v_norm_sq.sqrt();
        if nu < 1e-12_f64 || nv < 1e-12_f64 || !nu.is_finite() || !nv.is_finite() {
            // u o v degenerados: copia identidad x a out_x
            for i in 0..d_u { out_s[i] = x_s[i]; }
            return 0;
        }

        let inv_nu = 1.0_f64 / nu;

        // 2. Primera pasada de proyección MGS: w = v - <e1, v> e1
        let mut e1_dot_v = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            let vi = v_s[i] as f64;
            e1_dot_v += e1_i * vi;
        }

        // Vector temporal w en heap/stack para reortogonalización precisa
        let mut w = vec![0.0_f64; d_u];
        let mut w_norm_sq1 = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            let wi = (v_s[i] as f64) - e1_dot_v * e1_i;
            w[i] = wi;
            w_norm_sq1 += wi * wi;
        }

        // 3. Segunda pasada de reortogonalización (Twice-Is-Enough para cota de pérdida de ortogonalidad <= O(eps))
        let mut e1_dot_w = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            e1_dot_w += e1_i * w[i];
        }

        let mut w_norm_sq2 = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            w[i] -= e1_dot_w * e1_i;
            w_norm_sq2 += w[i] * w[i];
        }

        let nw = w_norm_sq2.sqrt();
        // Guarda de colinealidad relativa estricta: si ||w|| / ||v|| < 1e-8, el plano es singular
        if nw < 1e-8_f64 * nv || !nw.is_finite() {
            for i in 0..d_u { out_s[i] = x_s[i]; }
            return 0;
        }

        let inv_nw = 1.0_f64 / nw;

        // 4. Coordenadas planares a = <e1, x>, b = <e2, x>
        let mut a = 0.0_f64;
        let mut b = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            let e2_i = w[i] * inv_nw;
            let xi = x_s[i] as f64;
            a += e1_i * xi;
            b += e2_i * xi;
        }

        // 5. Rotación 2D exacta de las componentes del plano generador
        let theta_d = theta as f64;
        let cos_t = theta_d.cos();
        let sin_t = theta_d.sin();

        // Variaciones delta en el plano:
        // delta_a = (cos(theta)-1)*a - sin(theta)*b
        // delta_b =  sin(theta)*a + (cos(theta)-1)*b
        let c_minus_1 = cos_t - 1.0_f64;
        let delta_a = c_minus_1 * a - sin_t * b;
        let delta_b = sin_t * a + c_minus_1 * b;

        // 6. Actualización de rango 2 sobre el vector de estado: x' = x + delta_a * e1 + delta_b * e2
        let mut out_norm_sq = 0.0_f64;
        for i in 0..d_u {
            let e1_i = (u_s[i] as f64) * inv_nu;
            let e2_i = w[i] * inv_nw;
            let xi = x_s[i] as f64;
            let val = xi + delta_a * e1_i + delta_b * e2_i;
            out_s[i] = val as f32;
            out_norm_sq += val * val;
        }

        // 7. Normalización cordal de preservación de esfera unitaria S^{D-1}
        if out_norm_sq > 0.0_f64 && out_norm_sq.is_finite() {
            let inv_n = (1.0_f64 / out_norm_sq.sqrt()) as f32;
            for i in 0..d_u {
                out_s[i] *= inv_n;
            }
        }
        0
    }));

    match result {
        Ok(code) => code,
        Err(_) => {
            set_last_error("Panic caught in polydim_clifford_rotor_spin_v1100");
            -3
        }
    }
}
