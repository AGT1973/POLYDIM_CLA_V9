import os

# 1. Update Python Monolith for V909 (CliffordNet Telemetry & FFI)
file_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V909\polydim_v909_monolito.py'
with open(file_path, 'r', encoding='utf-8') as f: content = f.read()

# Fix cliffordnet args
old_ffi = '''        raw_energy_out = ctypes.c_double(0.0)
        metric_energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV909()
        res = self.cpp.polydim_cpp_cliffordnet_bivector_interact_v909(
            n, k,
            vecs_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivecs_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(raw_energy_out),
            ctypes.byref(metric_energy_out),
            ctypes.byref(err)
        )
        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        return bivecs_out, raw_energy_out.value, metric_energy_out.value'''

new_ffi = '''        raw_energy_out = ctypes.c_double(0.0)
        metric_energy_out = ctypes.c_double(0.0)
        constraint_res_out = ctypes.c_double(0.0)
        err = PolydimErrorV909()
        res = self.cpp.polydim_cpp_cliffordnet_bivector_interact_v909(
            n, k,
            vecs_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivecs_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(raw_energy_out),
            ctypes.byref(metric_energy_out),
            ctypes.byref(constraint_res_out),
            ctypes.byref(err)
        )
        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        return bivecs_out, raw_energy_out.value, metric_energy_out.value, constraint_res_out.value'''
content = content.replace(old_ffi, new_ffi)
content = content.replace('ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),\n            ctypes.POINTER(PolydimErrorV909)', 'ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),\n            ctypes.POINTER(PolydimErrorV909)')

with open(file_path, 'w', encoding='utf-8') as f: f.write(content)

# 2. Update C++ Kernel for V909
cpp_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V909\kernel_cpp_v909.cpp'
with open(cpp_path, 'r', encoding='utf-8') as f: cpp_content = f.read()

old_cpp_cliff = '''POLYDIM_EXPORT int polydim_cpp_cliffordnet_bivector_interact_v909(
    uint32_t num_vectors,
    uint32_t dim_k,
    const double* vectors_in,
    double* bivectors_out,
    double* raw_energy_out,
    double* metric_energy_out,
    PolydimErrorv909* err
) noexcept {'''

new_cpp_cliff = '''POLYDIM_EXPORT int polydim_cpp_cliffordnet_bivector_interact_v909(
    uint32_t num_vectors,
    uint32_t dim_k,
    const double* vectors_in,
    double* bivectors_out,
    double* raw_energy_out,
    double* metric_energy_out,
    double* constraint_res_out,
    PolydimErrorv909* err
) noexcept {'''
cpp_content = cpp_content.replace(old_cpp_cliff, new_cpp_cliff)

old_cpp_ret = '''        if (raw_energy_out) *raw_energy_out = total_raw_energy;
        if (metric_energy_out) *metric_energy_out = total_metric_energy;
        
        return 0;
    } catch (...) {'''

new_cpp_ret = '''        if (raw_energy_out) *raw_energy_out = total_raw_energy;
        if (metric_energy_out) *metric_energy_out = total_metric_energy;
        if (constraint_res_out) {
            // Simulated constraint residual: |raw_norm^2 - r^2|
            double residual = std::abs(total_raw_energy - total_metric_energy);
            *constraint_res_out = residual;
        }
        
        return 0;
    } catch (...) {'''
cpp_content = cpp_content.replace(old_cpp_ret, new_cpp_ret)

with open(cpp_path, 'w', encoding='utf-8') as f: f.write(cpp_content)

# 3. Update Rust Kernel for V909
rust_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V909\kernel_rust_v909.rs'
with open(rust_path, 'r', encoding='utf-8') as f: rust_content = f.read()

old_rust_cliff = '''pub extern "C" fn polydim_rust_cliffordnet_bivector_interact_v909(
    num_vectors: c_uint,
    dim_k: c_uint,
    vectors_in: *const c_double,
    bivectors_out: *mut c_double,
    raw_energy_out: *mut c_double,
    metric_energy_out: *mut c_double,
    err: *mut V909Error,
) -> c_int {'''

new_rust_cliff = '''pub extern "C" fn polydim_rust_cliffordnet_bivector_interact_v909(
    num_vectors: c_uint,
    dim_k: c_uint,
    vectors_in: *const c_double,
    bivectors_out: *mut c_double,
    raw_energy_out: *mut c_double,
    metric_energy_out: *mut c_double,
    constraint_res_out: *mut c_double,
    err: *mut V909Error,
) -> c_int {'''
rust_content = rust_content.replace(old_rust_cliff, new_rust_cliff)

old_rust_ret = '''        if !metric_energy_out.is_null() {
            *metric_energy_out = total_metric_energy;
        }
        
        0
    }
}'''

new_rust_ret = '''        if !metric_energy_out.is_null() {
            *metric_energy_out = total_metric_energy;
        }
        if !constraint_res_out.is_null() {
            *constraint_res_out = (total_raw_energy - total_metric_energy).abs();
        }
        
        0
    }
}'''
rust_content = rust_content.replace(old_rust_ret, new_rust_ret)
with open(rust_path, 'w', encoding='utf-8') as f: f.write(rust_content)
