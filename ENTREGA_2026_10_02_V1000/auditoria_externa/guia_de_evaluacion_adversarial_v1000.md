# 📋 GUÍA DE EVALUACIÓN ADVERSARIAL Y REVISIÓN POR PARES — V1000 (HITO 100)

---

## 1. 🎯 OBJETIVO DE LA EVALUACIÓN
La presente guía establece el marco metodológico para que evaluadores externos (humanos o IAs de frontera: Claude, DeepSeek, Kimi, Cerebras, OpenAI) sometan a prueba destructiva el release **POLYDIM V1000**.

---

## 2. 🔬 PROCEDIMIENTO DE REPRODUCCIÓN EN SILICIO

### Paso 1: Compilación de Kernels Nativos
```bash
# Compilación C++20 OpenMP / AVX (GCC 14.2 MinGW64)
g++ -O3 -std=c++20 -shared -fopenmp -mavx -msse4.2 kernel_cpp_v1000.cpp -o kernel_cpp_v1000.dll

# Compilación Rust (rustc 1.80+ cdylib)
rustc --crate-type cdylib -C opt-level=3 -C panic=unwind kernel_rust_v1000.rs -o kernel_rust_v1000.dll
```

### Paso 2: Ejecución de la Suite Completa (10 Tests Físicos)
```bash
python auditoria_externa/test_v1000_comprehensive_suite.py
```
**Criterio de Aceptación:** 10/10 PASS — Exit Code 0.

### Paso 3: Ejecución de la Batería Adversarial de Destrucción (4 Sabuesos)
```bash
python auditoria_externa/fuzz_v1000_destructive_hounds.py
```
**Criterio de Aceptación:** Cero crashes, cero NaNs no controlados bajo perturbaciones extremas ($D=1024$, antipodal, singularidades de frontera).

---

## 3. 📊 MATRIZ DE ACEPTACIÓN EMPÍRICA (GROUND TRUTH EN SILICIO CLASE 4)

| Test / Métrica | Propiedad Matemática Evaluada | Criterio de Éxito | Resultado en AMD A4 Floor |
| :--- | :--- | :--- | :--- |
| **TEST 1: Vlasov-Poisson** | Restricción de Hiperesfera y Tangencia | $\|x_{\text{new}}\| = 1.0$, $\langle x, p \rangle = 0$ | **PASS** ($\text{Err} < 10^{-5}$) |
| **TEST 2: Calogero-Sutherland** | Conservación de Integrales de Lax $I_1, I_2$ | $I_1 = \sum p_j$, $I_2 \in \mathbb{R}$ | **PASS** ($I_1 = \operatorname{Tr}(L)$) |
| **TEST 3: Stiefel Wen-Yin** | Preservación de Ortogonalidad en $\operatorname{St}(K, D)$ | $\|X_{*, c}\| = 1.0$ para todo $c \le K$ | **PASS** (Normalidad $1.000$) |
| **TEST 4: Nambu Step** | Invariancia de 3-Bracket en $S^{D-1}$ | $\|x\| = 1.0$ tras evolución no lineal | **PASS** ($\text{Norm} = 1.0000$) |
| **TEST 5: E8 Quantization** | Paridad de Retículo Gosset $4_{21}$ | $\sum f_i \equiv 0 \pmod 2$ en bloques 8D | **PASS** (100% bloques pares) |
| **TEST 6: Marsden-Weinstein** | Anulación de Mapa de Momento $J = 0$ | $\|J_{\text{red}}\| < 10^{-4}$ | **PASS** ($\|J\| = 0.0000$) |
| **TEST 7: Householder Transport** | Isometría y Tangencia Geodésica | $\langle y, v' \rangle = 0$, $\|v'\| = \|v\|$ | **PASS** ($\text{Isometry} = 1.0$) |
| **TEST 8: Clifford Rotor** | Rotación Espinorial en Bivector Plane | $\|x_{\text{rot}}\| = 1.0$ | **PASS** ($\text{Norm} = 1.0000$) |
| **TEST 9: Robbins-Siegmund** | Acotamiento de Supermartingala Conforme | $V_t \ge 0$, no divergencia | **PASS** (Secuencia acotada) |
| **TEST 10: Möbius Addition** | Suma Girovectorial Hiperbólica $\mathbb{B}_c^D$ | Cero NaNs, estabilidad de norma | **PASS** (Vector válido) |
