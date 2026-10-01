import os

file_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V908\polydim_v908_monolito.py'
with open(file_path, 'r', encoding='utf-8') as f: content = f.read()

# Fix cliffordnet args
content = content.replace('ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),\n            ctypes.POINTER(PolydimErrorV908)', 'ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),\n            ctypes.POINTER(PolydimErrorV908)')

# Fix the FFI wrapping
old_ffi = '''    def cpp_cliffordnet_interact(self, vectors: np.ndarray):
        require(vectors.ndim == 2, "Vectors must be 2D array")
        n, k = vectors.shape
        bivec_dim = (k * (k - 1)) // 2
        vecs_c = np.ascontiguousarray(vectors, dtype=np.float64)
        bivecs_out = np.zeros((n, bivec_dim), dtype=np.float64)
        energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV908()
        res = self.cpp.polydim_cpp_cliffordnet_bivector_interact_v908(
            n, k,
            vecs_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            bivecs_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.byref(energy_out),
            ctypes.byref(err)
        )
        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        return bivecs_out, energy_out.value'''

new_ffi = '''    def cpp_cliffordnet_interact(self, vectors: np.ndarray):
        require(vectors.ndim == 2, "Vectors must be 2D array")
        n, k = vectors.shape
        bivec_dim = (k * (k - 1)) // 2
        vecs_c = np.ascontiguousarray(vectors, dtype=np.float64)
        bivecs_out = np.zeros((n, bivec_dim), dtype=np.float64)
        raw_energy_out = ctypes.c_double(0.0)
        metric_energy_out = ctypes.c_double(0.0)
        err = PolydimErrorV908()
        res = self.cpp.polydim_cpp_cliffordnet_bivector_interact_v908(
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
content = content.replace(old_ffi, new_ffi)

# FFI Python MMap: Fix CreateFileMappingA ownership using RAII and c_wchar_p (W)
old_mmap = '''            CreateFileMappingA = ctypes.windll.kernel32.CreateFileMappingA
            CreateFileMappingA.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]'''
new_mmap = '''            CreateFileMappingW = ctypes.windll.kernel32.CreateFileMappingW
            CreateFileMappingW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p]'''
content = content.replace(old_mmap, new_mmap)
content = content.replace('CreateFileMappingA', 'CreateFileMappingW')
content = content.replace("mapping_name.encode('utf-8')", "mapping_name") # Because W expects wide string directly in Python 3

with open(file_path, 'w', encoding='utf-8') as f: f.write(content)

# Rust file patch for cliffordnet
rust_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V908\kernel_rust_v908.rs'
with open(rust_path, 'r', encoding='utf-8') as f: rust_content = f.read()

old_rust_cliff = '''pub extern "C" fn polydim_rust_cliffordnet_bivector_interact_v908(
    num_vectors: c_uint,
    dim_k: c_uint,
    vectors_in: *const c_double,
    bivectors_out: *mut c_double,
    energy_out: *mut c_double,
    err: *mut V908Error,
) -> c_int {'''

new_rust_cliff = '''pub extern "C" fn polydim_rust_cliffordnet_bivector_interact_v908(
    num_vectors: c_uint,
    dim_k: c_uint,
    vectors_in: *const c_double,
    bivectors_out: *mut c_double,
    raw_energy_out: *mut c_double,
    metric_energy_out: *mut c_double,
    err: *mut V908Error,
) -> c_int {'''

rust_content = rust_content.replace(old_rust_cliff, new_rust_cliff)
with open(rust_path, 'w', encoding='utf-8') as f: f.write(rust_content)
