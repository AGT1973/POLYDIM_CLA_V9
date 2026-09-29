# Cerebras-GPT-OSS-120B — Iteración 1 (Profundización SOTA)

## 1. Qué se rompe cuando **\(D = 10^{7}\)** y **\(1 000\) hilos** se ejecutan simultáneamente  

| Capa | Operación dominante | Complejidad | Cuello de botella al escalar |
|------|----------------------|-------------|------------------------------|
| **Algorítmica** | **Cayley‑Stiefel re‑tracción**  \(\;U^{\top}\Delta U\)  (producto “tall‑skinny”) | \(O(DK^{2})\)  (con \(K\le 256\)) | Cada hilo recorre **\(D\) filas** con stride \(K\).  Con 1 000 hilos el tráfico total es \(\approx 10^{7}\times K^{2}\times 1 000\) flops → **> 1 TB/s** de memoria, mucho más que el ancho de banda de cualquier nodo (≈ 300 GB/s). |
| **Numérica** | SMW / Sherman‑Morrison‑Woodbury | \(O(K^{3})\) (insignificante) | No es el factor limitante. |
| **Sistema** | Transferencias host ↔ GPU / “zero‑copy” | \(O(DK)\) | La latencia de 1000 hilos que compiten por la misma zona de memoria genera **false‑sharing** y **cache‑line thrashing**; los “page‑faults” de la memoria unificada se disparan. |

**Conclusión:** el **cuello de botella de ancho de banda y de contención de caché** es el *único* punto de ruptura que, si no se controla, hace que el tiempo por iteración crezca de \(\mathcal{O}(\mu s)\) a \(\mathcal{O}(ms)\) y que la precisión numérica se degrade por errores de redondeo acumulados.  

> **En otras palabras:** la arquitectura colapsa porque **\(1 000\) hilos intentan leer/escribir la misma matriz “tall‑skinny” \(U\in\mathbb R^{D\times K}\) con un patrón de acceso de salto \(K\)**, saturando el bus de memoria y destruyendo la localidad de caché.

---

## 2. Marco teórico que cuantifica el límite

### 2.1. Teorema de “Bloque‑Caché‑Oblivio” (adaptado a la re‑tracción)

> **Teorema 1 (Bloque‑Caché‑Oblivio para \(U^{\top}\Delta U\)).**  
> Sea \(U,\Delta U\in\mathbb R^{D\times K}\) con \(K\) fijo y \(D\gg K\).  Si la multiplicación se realiza con un **bloque interno** de tamaño \(b\) (número de columnas procesadas simultáneamente) tal que \(b\le \frac{L_{2}}{8\,\text{bytes}}\) (es decir, el bloque cabe en la caché L2), entonces el número total de transferencias de caché (cache‑misses) es

\[
\boxed{T_{\text{miss}}(D,K,b)=\Theta\!\left(\frac{DK}{b}\right)} .
\]

*Demostración resumida*  

1. Cada bloque de \(b\) columnas de \(U\) y \(\Delta U\) se carga una sola vez en L2.  
2. Dentro del bloque, el producto interno \((U_{i,:})^{\top}(\Delta U_{i,:})\) se realiza usando registros y SIMD, sin volver a tocar la memoria principal.  
3. El número de bloques es \(\lceil K/b\rceil\); para cada fila \(i\) se incurre en **un solo miss** por bloque.  
4. Sumando sobre todas las \(D\) filas se obtiene \(D\cdot\lceil K/b\rceil = \Theta(DK/b)\).

> **Corolario 1.1** – Si se elige \(b = K\) (el algoritmo “naïve”), \(T_{\text{miss}} = \Theta(DK)\) → tráfico lineal en \(K\).  Si se elige \(b = \sqrt{K}\) (p.e. \(b=16\) para \(K=256\)), el tráfico se reduce en un factor \(\sqrt{K}\).  

> **Corolario 1.2** – Con **\(P\) hilos** que comparten la misma memoria, el tráfico total es  
> \[
> T_{\text{total}} = P\;T_{\text{miss}} = \Theta\!\left(P\,\frac{DK}{b}\right).
> \]  
> Para que el ancho de banda físico \(B_{\text{mem}}\) no sea excedido, se necesita  
> \[
> P\;\frac{DK}{b}\;\frac{8\;\text{bytes}}{\text{operación}} \le B_{\text{mem}} .
> \]  
> Con \(D=10^{7}, K=256, B_{\text{mem}}=300\;\text{GB/s}\) y \(P=1000\) el límite de \(b\) es **\(b\ge 64\)**.  En la práctica, elegir \(b=64\) o \(b=128\) (ajustado a la L2) mantiene el tráfico bajo control.

---

## 3. Solución práctica: **Bloqueo + Zero‑Copy + SIMD**  

### 3.1. Principios de diseño

| Principio | Acción concreta |
|-----------|-----------------|
| **Bloqueo de columnas** | Procesar la matriz en “tiles” de ancho \(b\) (p.e. 64) que caben en la caché L2. |
| **Thread‑local buffers** | Cada hilo tiene su propio bloque de salida \(\Omega_{\text{local}}\) alineado a 64 B, evitando false‑sharing. |
| **Zero‑Copy / GPU‑Direct** | Registrar la zona de memoria de \(U\) como *pinned* y mapearla directamente en la GPU; los hilos de CPU solo leen, la GPU escribe los resultados. |
| **SIMD‑fusión** | Usar intrínsecos AVX‑512 (o NEON en ARM) para calcular simultáneamente 8‑16 productos escalares por iteración. |
| **Prefetch explícito** | `__builtin_prefetch` (C++) o `core::arch::x86_64::_mm_prefetch` (Rust) para la fila siguiente del bloque. |

### 3.2. Parches de código  

#### 3.2.1. C++ (OpenMP + AVX‑512) – bloque de re‑tracción

```cpp
// ---------------------------------------------------------------
//  file: cayley_retraction_blocked.hpp
//  Compilación: g++ -O3 -march=native -fopenmp -mavx512f
// ---------------------------------------------------------------
#pragma once
#include <immintrin.h>
#include <omp.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cassert>

// ----------------------------------------------------------------
//  Parámetros de bloque (ajustar a la L2 del nodo)
// ----------------------------------------------------------------
constexpr std::size_t BLOCK_COLS = 64;          // 64 * 8 bytes = 512 B < L2 line
constexpr std::size_t ALIGNMENT   = 64;         // alineación de 64 B

// ----------------------------------------------------------------
//  Función bloqueada:  Omega = Uᵀ ΔU  (K×K)