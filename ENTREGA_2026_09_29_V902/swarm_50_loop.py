import os
import sys
import time
import subprocess
import json

def run_loop():
    print("=== INICIANDO PROTOCOLO SWARM VECTOR BUS (-.-) : 50 ITERACIONES ===")
    base_dir = r"E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V902"
    audit_dir = os.path.join(base_dir, "auditoria_externa")
    test_script = os.path.join(audit_dir, "test_v902_comprehensive_suite.py")
    hounds_script = os.path.join(audit_dir, "fuzz_v902_destructive_hounds.py")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = base_dir + os.pathsep + audit_dir + os.pathsep + env.get("PYTHONPATH", "")
    env["POLYDIM_ADVERSARIAL_LEVEL"] = "EXTREME"
    
    success_count = 0
    start_time = time.time()
    
    with open("raw_silicon_test_log_v902.txt", "w", encoding="utf-8") as master_log:
        for i in range(1, 51):
            print(f"\n--- Iteración {i}/50 ---")
            master_log.write(f"\n--- Iteración {i}/50 ---\n")
            
            # Run test suite
            res_test = subprocess.run([sys.executable, test_script], cwd=audit_dir, env=env, capture_output=True, text=True)
            master_log.write(res_test.stdout)
            master_log.write(res_test.stderr)
            
            # Run destructive hounds
            res_hounds = subprocess.run([sys.executable, hounds_script], cwd=audit_dir, env=env, capture_output=True, text=True)
            master_log.write(res_hounds.stdout)
            master_log.write(res_hounds.stderr)
            
            if res_test.returncode == 0 and res_hounds.returncode == 0:
                print(f"Iteración {i}: PASS (Exit Code 0)")
                success_count += 1
            else:
                print(f"Iteración {i}: FAIL (Test={res_test.returncode}, Hounds={res_hounds.returncode})")
                print("ABORTANDO CICLO POR REGLA DE CERO TOLERANCIA.")
                break
                
    elapsed = time.time() - start_time
    print(f"\n=== PROTOCOLO COMPLETADO ===")
    print(f"Iteraciones Exitosas: {success_count}/50")
    print(f"Tiempo Total: {elapsed:.2f} segundos")
    
    if success_count == 50:
        print("CERTIFICACIÓN SOTA ALCANZADA (EXIT CODE 0).")
        sys.exit(0)
    else:
        print("FALLA ASINTÓTICA DETECTADA.")
        sys.exit(1)

if __name__ == "__main__":
    run_loop()
