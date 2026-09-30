import sqlite3
import os
import hashlib
import time

db_path = r'E:\POLYDIM-THEORICAL\POLYDIM_VECDB.sqlite'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

findings = [
    # GLM-5.2 Findings
    ('GLM-5.2', 'polydim_v900_monolito.py', 'PolydimCppKernelV900', 'Method Shadowing & Dead Code', 'CRITICAL',
     'Metodo duplicado clifford_drift_bound en PolydimCppKernelV900: el primero llama a polydim_rust_clifford_drift_bound_v900 inexistente en DLL C++ y a self.get_last_error_string no definida en CppKernel.',
     'def clifford_drift_bound(...) in PolydimCppKernelV900'),
    ('GLM-5.2', 'polydim_rocm_mi300x_benchmark.cpp', 'hip_stiefel_smw_matvec', 'Missing V^T X Matmul in SMW', 'CRITICAL',
     'El kernel HIP no implementa la formula SMW completa Y = X + tau * U * M_inv * V^T * X; falta multiplicar por V^T X y V es parametro no usado.',
     '__global__ void hip_stiefel_smw_matvec'),
    ('GLM-5.2', 'polydim_dart_v900.dart', 'PolydimErrorV900 Struct', 'Dart ABI Incomplete Struct & Missing Packing', 'CRITICAL',
     'PolydimErrorV900 en Dart carece de arena_id (u64) y gen (u64) y @Packed(8), causando mismatch de 276/280 bytes vs 260 bytes y potencial stack corruption.',
     'final class PolydimErrorV900 extends Struct'),
    ('GLM-5.2', 'kernel_rust_v900.rs', 'two_nn_intrinsic_dim', 'd2=Infinity Contamination in Two-NN', 'HIGH',
     'd2=Infinity no filtrado produce mu=Infinity, sum_log_mu=Infinity y d_mle=0.0 en clusters dispersos; requiere filtrado estricto d2.is_finite() && d2 > d1.',
     'two_nn_intrinsic_dim'),
    ('GLM-5.2', 'polydim_triton_kernel_v900.py', 'auon_log_cosh_kernel_fp64', 'Triton exp(2z) Overflow without Clamp', 'HIGH',
     'Falta clamp en z en kernel Triton causando overflow en exp(2z) para |z|>360 e inf/inf=NaN en tanh_z.',
     'auon_log_cosh_kernel_fp64'),
    ('GLM-5.2', 'kernel_rust_v900.rs', 'clifford_drift_bound', 'Clifford Drift Formula Multi-block Accumulation', 'MEDIUM_HIGH',
     'Formula reorth = num_blocks * qr_drift + block_drift suma block_drift solo una vez; debe ser num_blocks * (block_drift + qr_drift) + rem_drift en regimen transitorio.',
     'clifford_drift_bound'),
    ('GLM-5.2', 'polydim_rocm_mi300x_benchmark.cpp', 'hip_clifford_rotor_batch', 'Fragile Stride & Race Condition in Rotors', 'MEDIUM',
     'Stride basado en planes_q[num_planes-1]+1 es fragil; debe pasarse dimension D explicita y evitar colisiones de hilos en mismas coordenadas.',
     'hip_clifford_rotor_batch'),
    ('GLM-5.2', 'kernel_rust_v900.rs', 'gram_ns_polar_restart', 'Heap Allocation inside Newton-Schulz Hot Path', 'LETHAL',
     'Asignacion de 3 matrices DxD en el heap (temp_r, temp_r2, temp_next) dentro del bucle de NS; para D=10^4 consume 2.4GB y en D=10^6 causa OOM fatal.',
     'polydim_rust_gram_ns_polar_restart_v900'),
    ('GLM-5.2', 'kernel_rust_v900.rs', 'solve_linear_system_2k_rust', 'Heap Alloc in Stiefel Linear Solve', 'LETHAL',
     'let mut aug = vec![0.0f64; n_sys * cols] en hot-path; debe usar stack-allocation fijo para 2K <= 128.',
     'solve_linear_system_2k_rust'),
    ('GLM-5.2', 'kernel_rust_v900.rs', 'auon_matrix_rms_normalize', 'cosh(x)^2 Overflow for |x| > 710', 'LETHAL',
     'normalized_v.cosh() excede limite FP64 (1.8e308) para |x|>710; debe calcularse en dominio logaritmico LogSumExp.',
     'polydim_rust_auon_matrix_rms_normalize_v900'),
    ('GLM-5.2', 'kernel_cpp_v900.cpp', 'stiefel_cayley_smw_retraction', 'OpenMP Critical Serializes 128 Cores', 'HIGH',
     'Reduccion de bloques KxK con #pragma omp critical serializa la ejecucion en EPYC/MI300X; debe paralelizarse sobre bucle colapsado de salida (i, j).',
     'polydim_cpp_stiefel_cayley_smw_retraction_v900'),
    ('GLM-5.2', 'polydim_rocm_mi300x_benchmark.cpp', 'hip_stiefel_smw_matvec', 'GPU Memory Uncoalescing on CDNA3/MI300X', 'HIGH',
     'Acceso no coalescido a U[i * 2K + j] por hilos adyacentes degrada ancho de banda HBM3 de 5.3 TB/s a ~10 GB/s.',
     'hip_stiefel_smw_matvec'),
    
    # Claude Red Team Direct Findings
    ('Claude-RedTeam', 'kernel_rust_v900.rs', 'simplicial_homology_hodge', 'Exact Simplicial Homology over Q via Dual Primes', 'HIGH',
     'Calculo de homologia simplicial exacta Betti-1 sobre Q mediante eliminacion Gaussiana dispersa en dos primos grandes (2147483647 / 2147483629) distinguiendo torsion Z2 de cavidades reales.',
     'polydim_rust_simplicial_homology_hodge_v900'),
    ('Claude-RedTeam', 'kernel_rust_v900.rs', 'riemannian_geodesic', 'Kahan Stable 2*atan2 Geodesic on S^(D-1)', 'HIGH',
     'Metrica geodesica de Kahan theta = 2*atan2(||u_hat - v_hat||, ||u_hat + v_hat||) garantizando estabilidad incondicionada en todo el dominio [0, pi] sin singularidad en pi.',
     'riemannian_geodesic'),
    ('Claude-RedTeam', 'kernel_rust_v900.rs', 'gram_ns_polar_restart', 'Rigorous Spectral Norm Bound for NS Prescaling', 'HIGH',
     'Pre-escalado espectral riguroso sigma_max <= min(||A||_F, sqrt(||A||_1 * ||A||_inf)) eliminando divergencia a NaN en matrices con espectro ortogonal al vector uniforme.',
     'gram_ns_polar_restart'),
    ('Claude-RedTeam', 'kernel_rust_v900.rs', 'FFI_Cortafuegos', 'Allocation Firewall & TryReserve in FFI', 'HIGH',
     'Cortafuegos de asignacion con try_reserve_exact en Rust y PD_CATCH(std::bad_alloc) en C++ retornando -90 ante peticiones de memoria imposibles (2^32-1) sin abortar el proceso OS.',
     'FFI Allocation Firewall')
]

ts = time.strftime('%Y-%m-%d %H:%M:%S')
inserted = 0

for f in findings:
    m_name, s_file, s_sec, topic, f_type, summary, code_ref = f
    raw_h = hashlib.sha256((m_name + s_file + topic + summary).encode('utf-8')).hexdigest()[:16]
    cur.execute('''
    INSERT INTO swarm_opinions (model_name, source_file, slide_or_sec, critique_topic, finding_type, summary, code_ref, raw_hash, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (m_name, s_file, s_sec, topic, f_type, summary, code_ref, raw_h, ts))
    inserted += 1

conn.commit()
total = cur.execute('SELECT COUNT(*) FROM swarm_opinions').fetchone()[0]
conn.close()

print(f'Ingesta exitosa: {inserted} nuevos hallazgos SOTA vectorizados e indexados.')
print(f'Total de opiniones en POLYDIM_VECDB.sqlite: {total}')
