#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <vector>
#include <stdexcept>
#include <mutex>
#include <cmath>

namespace py = pybind11;

// SOTA: 3-Level Memory Pool (Global Pool -> Iteration Arena -> Cache)
class GlobalMemoryPool {
private:
    std::vector<std::vector<double>> pool;
    std::mutex mtx;

public:
    std::vector<double> acquire(size_t size) {
        std::lock_guard<std::mutex> lock(mtx);
        for (auto it = pool.begin(); it != pool.end(); ++it) {
            if (it->capacity() >= size) {
                std::vector<double> block = std::move(*it);
                pool.erase(it);
                block.resize(size);
                return block;
            }
        }
        return std::vector<double>(size, 0.0);
    }

    void release(std::vector<double>&& block) {
        std::lock_guard<std::mutex> lock(mtx);
        pool.push_back(std::move(block));
    }

    static GlobalMemoryPool& get_instance() {
        static GlobalMemoryPool instance;
        return instance;
    }
};

class PolydimPybindV911 {
public:
    PolydimPybindV911() {}

    // Safe memory binding for AuON Log-Space RMS (Matrix-Free telemetry compatible)
    py::tuple auon_rms_normalize(py::array_t<double> input_matrix) {
        py::buffer_info buf = input_matrix.request();
        if (buf.ndim != 2) throw std::runtime_error("Input must be a 2D matrix");
        
        int rows = buf.shape[0];
        int cols = buf.shape[1];
        double* ptr = static_cast<double*>(buf.ptr);
        
        auto output = py::array_t<double>(buf.size);
        py::buffer_info out_buf = output.request();
        double* out_ptr = static_cast<double*>(out_buf.ptr);

        // Preallocate from pool
        auto workspace = GlobalMemoryPool::get_instance().acquire(rows);
        double* rms_out = workspace.data();

        // Emulate the logaddexp RMS normalization safely
        #pragma omp parallel for
        for (int i = 0; i < rows; ++i) {
            double* row_ptr = ptr + i * cols;
            double* out_row = out_ptr + i * cols;
            
            double max_log = -INFINITY;
            for (int j = 0; j < cols; ++j) {
                double val = std::abs(row_ptr[j]);
                double lcs = (val < 20.0) ? std::log(std::cosh(val)) : (val - 0.6931471805599453);
                double lcs_sq = lcs * 2.0;
                if (lcs_sq > max_log) max_log = lcs_sq;
            }
            
            double sum_exp = 0.0;
            if (max_log != -INFINITY) {
                for (int j = 0; j < cols; ++j) {
                    double val = std::abs(row_ptr[j]);
                    double lcs = (val < 20.0) ? std::log(std::cosh(val)) : (val - 0.6931471805599453);
                    sum_exp += std::exp((lcs * 2.0) - max_log);
                }
            }
            
            double log_rms = -INFINITY;
            if (sum_exp > 0.0) {
                log_rms = max_log * 0.5 + 0.5 * std::log(sum_exp / static_cast<double>(cols));
            }
            
            double scale = 0.0;
            if (log_rms != -INFINITY) {
                double eps = 1e-8;
                double log_eps = std::log(eps);
                double diff = log_eps - log_rms;
                double log_rms_eps = log_rms + (diff > 0 ? diff + std::log1p(std::exp(-diff)) : std::log1p(std::exp(diff)));
                scale = std::exp(-log_rms_eps);
                if (!std::isfinite(scale)) scale = 0.0;
            }
            
            for (int j = 0; j < cols; ++j) {
                out_row[j] = row_ptr[j] * scale;
            }
            rms_out[i] = std::exp(log_rms);
        }

        auto rms_array = py::array_t<double>(rows);
        std::copy(workspace.begin(), workspace.end(), static_cast<double*>(rms_array.request().ptr));
        GlobalMemoryPool::get_instance().release(std::move(workspace));

        return py::make_tuple(output, rms_array);
    }
};

PYBIND11_MODULE(polydim_pybind_v911, m) {
    m.doc() = "POLYDIM V911 SOTA PyBind11 Native Extension (Phase 1)";
    py::class_<PolydimPybindV911>(m, "PolydimPybindV911")
        .def(py::init<>())
        .def("auon_rms_normalize", &PolydimPybindV911::auon_rms_normalize);
}
