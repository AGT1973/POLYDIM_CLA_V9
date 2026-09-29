# Contexto Histórico — Sesión V817 Auditoría & Reparación
# Fecha: 2026-09-29 ~14:00–15:37 (Argentina)
# Regla 13: Anti-Token Explosion — Resumen para continuación

---

## Estado de la Tarea Principal

**Objetivo:** Ariel envió la entrega V817 a 7 IAs auditoras (Claude, DeepSeek, Kimi, Gemini, Qwen, ChatGPT, Z_AI). Se recibieron los 7 reportes en `E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V817\respuestas\*.md`. Se consolidaron todos los errores, se priorizaron, y se comenzó la reparación uno por uno.

---

## Checklist de Errores — Estado al Corte

### ✅ PARCHADOS (15 de 22)
1–13: Ver PERMANENT_MEMORY.md sección [2026-09-29].
14. **Baraniuk-Wakin C=0.5 → C=1.0** — Rust L587, C++ L345 parchados. Test_9 reescrito con tabla multi-epsilon honesta (ya no assertea `is_feasible` para eps=0.15).
15. **`assert` → `require()`** — Función `require()` agregada en test suite L43-45. Todos los `assert` del archivo reemplazados por `require()` via script Python. Inmune a `python -O`.

### ❌ PENDIENTE INMEDIATO #16: c_char_p → c_void_p en monolito
- **Archivo:** `E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V817\polydim_v817_monolito.py` líneas 153-158
- **Qué hacer:** Cambiar argtypes de `polydim_rust_qsbr_snapshot_copy_v817` de `ctypes.c_char_p` a `ctypes.c_void_p` para src y dst. Evita null-termination marshaling con datos binarios.
- **Fix es 2 líneas.**

### ❌ PENDIENTE INMEDIATO #17: Gram-NS kernel (cúbico → quíntico + convergencia real)
- **Archivo:** `E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V817\kernel_rust_v817.rs` líneas 640-713
- **Problemas:**
  1. El NS es cúbico (`Q_next = 0.5 * Q * (3I - R)`). Debería ser quíntico Muon con coeficientes `a=3.4445, b=-4.7750, c=2.0315`.
  2. No hay pre-escalado por `‖X‖_F` antes del NS. Sin esto los valores singulares de entrada están fuera del radio de convergencia.
  3. `is_converged_out = 1` SIEMPRE (L701). No hay criterio de convergencia real.
- **Fix:**
  ```rust
  // 1. Pre-escalar: X = X / ‖X‖_F
  // 2. Iteración quíntica: R = Q*Q^T, Q_next = a*Q + (b*R + c*R²) @ Q
  // 3. Criterio: ‖Q^T Q - I‖_F < 1e-6 → converged = true
  ```
- **C++ mirror:** `kernel_cpp_v817.cpp` tiene el mismo NS cúbico, hay que parchear también.

### ❌ PENDIENTE INMEDIATO #18: Test_10 sin oráculo SVD
- **Archivo:** `test_v817_comprehensive_suite.py` L407-419
- **Qué hacer:** Agregar comparación contra el factor polar real `U·Vᵀ` del SVD:
  ```python
  u_svd, _, vt = np.linalg.svd(a_mat)
  polar_true = u_svd @ vt
  polar_err = np.linalg.norm(q_ortho - polar_true, 'fro') / np.sqrt(n)
  require(polar_err < 1e-4, f"Q no es el factor polar: err={polar_err:.3e}")
  ```
- **NOTA:** Este fix depende de que el kernel NS converja bien (#17). Si el NS sigue cúbico con 5 pasos, el error será grande y el test fallará. Arreglar #17 primero.

### ❌ AXIOMÁTICOS/SPEC (V818+ roadmap, no bloqueantes para V817):
19. No hay kernel Cayley-Stiefel (axioma 3)
20. Clifford drift claim incorrecto para D>>1 (axioma 2)
21. Axiomas 2,3,6 sin tests (no hay kernels)
22. Claim "7810%" ya eliminado del readme_first.md

---

## Estado del Build

- **Último build exitoso:** Tests 1-7 pasaron. Test 8 falló por ctypes type (fix aplicado pero NO re-testeado).
- **Cambios desde último build:** C=1.0 en ambos kernels, `require()` global, test_9 reescrito.
- **Acción necesaria:** Recompilar ambas DLLs y ejecutar `python build_and_test_v817.py`.

## Ingesta a POLYDIM_VECDB.sqlite

- DeepSeek: 7 rows en `swarm_opinions` ✅
- Claude, Kimi, Gemini, Qwen, ChatGPT, Z_AI: leídos y analizados en chat, NO ingested a DB.

## Archivos .rs.txt / .cpp.txt

- Las copias con doble extensión (`kernel_rust_v817.rs.txt`, `kernel_cpp_v817.cpp.txt`) necesitan re-sync tras los parches.
- El build script hace el sync automáticamente.

## Git

- Commit `2f88c99` es pre-parche. Falta nuevo commit con todos los fixes.

---

## 🛡️ Conocimientos y Protocolo de Aplicación de la Regla 13 (Anti-Token Explosion)

### 1. ¿Cuándo se activa la Regla 13?
- **Umbral de saturación de ventana:** La sesión actual acumuló lecturas profundas de los 7 reportes de auditoría (`claude.md`, `deepseek.md`, `kimi.md`, `gemini.md`, `qwen.md`, `chatgpt.md`, `z_ai.md`), generación de matrices comparativas y múltiples iteraciones de parches numéricos.
- **Transición Post-Ingesta (Regla 19):** Terminada la fase de diagnóstico y consolidación de los 22 errores, la ventana de contexto entra en zona crítica antes de la fase de compilación masiva y re-ejecución del test suite.
- **Principio Inviolable:** Prohibido dejar tareas a medias o perder el hilo de qué líneas exactas se tocaron y cuáles faltan por parchar.

### 2. Protocolo de Snapshot Seguro y Continuidad (Cero Pérdida):
- **Adición Estricta (No Borrar Nada):** Tanto `PERMANENT_MEMORY.md` como este `contexto_historico.md` se actualizan exclusivamente de forma aditiva/incremental. Se preserva todo el historial forense.
- **Desacoplamiento de Carga:** El próximo agente NO debe re-leer los archivos crudos de `respuestas/*.md` (ahorrando decenas de miles de tokens de entrada). Debe arrancar inmediatamente desde la sección **Checklist de Errores — Estado al Corte** de este documento.

### 3. Secuencia de Trabajo para la Sesión Entrante (Paso a Paso):
1. **Paso 1:** Parchear `E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V817\polydim_v817_monolito.py` (L153-158): reemplazar `ctypes.c_char_p` por `ctypes.c_void_p` en `argtypes` de QSBR.
2. **Paso 2:** Parchear `kernel_rust_v817.rs` (L640-713) y `kernel_cpp_v817.cpp`: migrar Gram-NS a iteración quíntica Muon (`a=3.4445, b=-4.7750, c=2.0315`), pre-escalar por norma Frobenius inicial, y computar convergencia real con tolerancia `1e-6`.
3. **Paso 3:** Parchear `test_v817_comprehensive_suite.py` (L407-419): incorporar el oráculo SVD (`polar_true = U @ V.T`) contra `q_ortho`.
4. **Paso 4:** Ejecutar `python build_and_test_v817.py` desde `E:\POLYDIM_EINSOF\ENTREGA_2026_09_29_V817\` para recompilar ambas DLLs y correr la suite completa 10/10.
5. **Paso 5:** Verificar sincronización de `.rs.txt` y `.cpp.txt`, e interactuar con git para commit y push.
