# Staging Theory V907 - Avances y Correcciones (Regla 19)

## 1. AuON Log-Space RMS Normalize (Freno de Sobreflujo Exponencial)
Se identificó una vulnerabilidad crítica de sobreflujo (overflow) en la normalización RMS Log-Sum-Exp. Anteriormente, el algoritmo revertía el espacio logarítmico extrayendo $RMS = \exp(\max/2) \cdot \sqrt{\dots}$ para luego calcular $scale = 1 / (RMS + \epsilon)$. Para tensores donde $\max(|x_i|) \ge 710$, $RMS$ evaluaba a `Infinity` (debido al límite de IEEE 754 de $\exp(709)$), lo cual anulaba la escala ($scale \to 0$) destruyendo el gradiente y congelando la topología latente.
**Solución Geométrica (V907):** La división se reescribió como una substracción en el espacio logarítmico: $scale = \exp(-\log_{RMS})$. Esto garantiza que los valores masivos decaigan naturalmente por underflow $scale \to 0$ sin colapsar el pipeline a subnormales NaN o arrojar `Inf`.

## 2. Estabilidad de Geodésicas Riemannianas en S^(D-1) (Catastrophic Cancellation)
El kernel previo computaba la distancia de cuerda usando una suma directa de varianzas: `chordal_sq += (u_i - v_i)^2`. En $D \ge 10^7$ (espacios masivos), la acumulación ingenua sufre deriva por punto flotante y cancelación catastrófica para vectores adyacentes.
Además, vectores antiparalelos ($dot < -0.9999$) eran delegados a $\arccos(dot)$, que posee inestabilidad numérica extrema cerca de -1.
**Solución (V907):**
1. Se integró una suma de *Kahan* compensada para `dot` y `chordal_sq`.
2. Se introdujo una métrica antipodal explícita computando la cuerda opuesta: $chord_{anti}^2 = \sum (u_i + v_i)^2$ y usando $\pi - 2\arcsin(chord_{anti} / 2)$, asegurando continuidad suave en todo el límite esférico.

## 3. Embotellamiento de Memoria en Retracción Cayley-Stiefel (Matrix-Free)
El solver LU lineal `solve_linear_system_2k` operaba en la ruta crítica del optimizador iterativo, instanciando `std::vector<double>` masivamente por bloque, induciendo latencias agudas y fragmentación del heap (Heap Fragmentation Bottleneck).
**Solución (V907):** Se implementó una reserva estática (stack/arena array) de tamaño constante $256 \times 384$ para acoplar la dimensión $K \le 128$ del proyector Stiefel, evadiendo completamente la invocación al OS `malloc/free` durante el flujo iterativo tensorial.

## 4. Fuga de Memoria/GC en Puentes FFI PMTP
Se parchearon estructuras `c_char_p` que inducían la posibilidad de un dangling pointer en los Mappings de SharedMemory en Python debido a políticas de recolección de basura, pasando a `c_void_p` estricto, blindando el contrato de la FFI.
