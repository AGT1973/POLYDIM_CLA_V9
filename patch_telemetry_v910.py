import os

file_path = r'E:\POLYDIM_EINSOF\ENTREGA_2026_09_30_V910\polydim_v910_monolito.py'
with open(file_path, 'r', encoding='utf-8') as f: content = f.read()

# Add the SOTA CUSUM/EWMA telemetry class
telemetry_class = '''
class NeumaierAccumulator:
    def __init__(self):
        self.sum = 0.0
        self.c = 0.0
    def add(self, val):
        y = val - self.c
        t = self.sum + y
        self.c = (t - self.sum) - y
        self.sum = t
    def get(self): return self.sum

class SOTATelemetryDriftMonitor:
    def __init__(self):
        self.raw_acc = NeumaierAccumulator()
        self.metric_acc = NeumaierAccumulator()
        self.constraint_acc = NeumaierAccumulator()
        
        # EWMA
        self.alpha = 0.05
        self.ewma_constraint = 0.0
        
        # CUSUM for drift detection
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        self.cusum_threshold = 1e-10
        self.drift_k = 1e-12
        
        self.steps = 0
        self.alarm_triggered = False

    def update(self, raw, metric, constraint):
        self.raw_acc.add(raw)
        self.metric_acc.add(metric)
        self.constraint_acc.add(constraint)
        
        if self.steps == 0:
            self.ewma_constraint = constraint
        else:
            self.ewma_constraint = self.alpha * constraint + (1 - self.alpha) * self.ewma_constraint
            
            # CUSUM Update
            diff = constraint - self.ewma_constraint
            self.cusum_pos = max(0.0, self.cusum_pos + diff - self.drift_k)
            self.cusum_neg = max(0.0, self.cusum_neg - diff - self.drift_k)
            
            if self.cusum_pos > self.cusum_threshold or self.cusum_neg > self.cusum_threshold:
                self.alarm_triggered = True
                
        self.steps += 1
'''

# Find a good place to insert the class, like after PolydimError
insert_marker = "class PolydimErrorV910(ctypes.Structure):"
content = content.replace(insert_marker, telemetry_class + "\n" + insert_marker)

# Update the wrapper to use it
old_interact = '''    def cpp_cliffordnet_interact(self, vectors: np.ndarray):
        require(vectors.ndim == 2, "Vectors must be 2D array")
        n, k = vectors.shape'''

new_interact = '''    def __init__(self, use_gpu=False):
        self.monitor = SOTATelemetryDriftMonitor()
        
    def cpp_cliffordnet_interact(self, vectors: np.ndarray):
        require(vectors.ndim == 2, "Vectors must be 2D array")
        n, k = vectors.shape'''
# Wait, __init__ is already in PolydimCoreV910. Let's find it.

old_init = '''    def __init__(self, use_gpu=False):
        self.use_gpu = use_gpu'''

new_init = '''    def __init__(self, use_gpu=False):
        self.use_gpu = use_gpu
        self.monitor = SOTATelemetryDriftMonitor()'''
content = content.replace(old_init, new_init)

old_ret = '''        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        return bivecs_out, raw_energy_out.value, metric_energy_out.value, constraint_res_out.value'''

new_ret = '''        require(res == 0, f"cpp_cliffordnet_interact returned {res}")
        err.check_ok()
        self.monitor.update(raw_energy_out.value, metric_energy_out.value, constraint_res_out.value)
        return bivecs_out, raw_energy_out.value, metric_energy_out.value, constraint_res_out.value'''
content = content.replace(old_ret, new_ret)

with open(file_path, 'w', encoding='utf-8') as f: f.write(content)
