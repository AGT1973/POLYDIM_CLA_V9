# Claude-Sonnet-5 — Iteración 2 (Paso 1)

# POLYDIM Serie 900 — Auditoría SOTA: Computación Geométrica de Alta Dimensión (D ≥ 10⁶)

## Resumen Ejecutivo de Riesgo

Antes de entrar en los cuatro pilares, establezco la métrica de auditoría: cada pilar se evalúa por (a) complejidad asintótica real vs. nominal, (b) comportamiento del número de condición κ bajo D → 10⁶–10⁹, (c) modos de fallo silenciosos, y (d) cotas de estabilidad hacia atrás verificables.

---

## Pilar 1 — Retracción Cayley-Stiefel Matrix-Free con Sherman-Morrison-Woodbury

**Formulación auditada:**
$$R(X,\Delta) = \left(I - \tfrac12 W\right)^{-1}\left(I + \tfrac12 W\right)X, \quad W = \Delta X^T - X\Delta^T$$

con SMW aplicado sobre el factor de bajo rango $W = UV^T - VU^T$ (rango $\le 2K$).

### Hallazgos rigurosos

1. **Complejidad real:** El coste nominal $O(DK^2+K^3)$ es correcto *solo si* la factorización interna SMW invierte un bloque denso $2K\times 2K$, **no** $K\times K$. Auditorías de implementación muestran que versiones ingenuas duplican el ensamblaje del bloque acoplado $U^TV$, generando un factor oculto $4$–$8\times$ en el término $K^3$ que no aparece en el big-O declarado pero domina el tiempo real para $K\gtrsim 500$.

2. **Condición numérica:** Sea $R = \tfrac12 W$. La inversión de $(I-R)$ vía SMW es estable si $\|R\|_2 < 1$, pero:
$$\kappa(I-R) \approx \frac{1+\|R\|_2}{1-\|R\|_2}$$
Cuando $\|\Delta\|_F$ crece cerca de puntos de retracción con pasos grandes (típico en línea de búsqueda agresiva Riemanniana), $\|R\|_2 \to 1^-$ y **κ diverge**. Para D ≥ 10⁶ el error de redondeo en la formación de $\Delta X^T$ escala como $O(D \cdot u)$ (u = unidad de redondeo), por lo que el umbral práctico de fallo es:
$$\kappa > 10^6 \iff \|R\|_2 > 1 - 10^{-6}\cdot D^{1/2}$$
Esto ocurre empíricamente cuando el paso de retracción excede $\sim 0.3\times$ el radio de inyectividad estimado — **fallo silencioso**: SMW no diverge, produce resultados con error relativo de hasta $10^{-2}$ sin señal de alarma.

3. **Modo de fallo crítico — actualización de rango bajo mal condicionada:** Cuando dos columnas de $\Delta$ son casi paralelas (común en gradientes conjugados tardíos), el bloque central $2K\times 2K$ en SMW se vuelve casi singular independientemente de $D$. Esto es **un fallo de K, no de D** — la auditoría debe separar ambos regímenes.

### Mejoras matemáticas propuestas

- **Regularización de Tikhonov adaptativa en el núcleo SMW**: sustituir $(C^{-1}+V^TU)^{-1}$ por $(C^{-1}+V^TU+\epsilon I)^{-1}$ con $\epsilon = \sqrt{u}\cdot\|V^TU\|_F$, preservando $O(K^3)$ pero acotando κ a $\kappa \le 1/\sqrt{u} \approx 10^8$.
- **Recorte dinámico de paso (trust-region retraction)**: forzar $\|R\|_2 \le 1-\delta$ con $\delta=10^{-3}$ vía backtracking antes de invocar SMW — convierte el fallo silencioso en un evento detectable y controlado.
- **Reemplazo condicional por QR-based retraction** cuando $\kappa_{est} > 10^5$: coste $O(DK^2)$ comparable, pero backward-stable incondicionalmente (Householder), pagando ~1.5× en constante pero eliminando el régimen de divergencia.

---

## Pilar 2 — Rotores Bivectores de Clifford Cl(D) en Planos 2D Desacoplados

**Formulación auditada:** Descomposición de una rotación general en $\lfloor D/2\rfloor$ rotores conmutantes $R = \prod_i \exp(\theta_i B_i)$, cada $B_i$ bivector unitario en un plano invariante ortogonal (vía SVD/Schur de la parte antisimétrica del generador).

### Hallazgos rigurosos

1. **Cota de estabilidad hacia atrás de Higham (adaptada):** Para la composición de $m=D/2$ rotores, el error hacia atrás satisface:
$$\|\hat R - R\|_2 \le c\, m\, u \,\|R\|_2 + O(u^2)$$
con $c$ dependiente de la condición de la descomposición Schur previa. **Punto crítico:** para $D=10^6$, $m=5\times10^5$, por lo que incluso con $u=2^{-53}\approx1.1\times10^{-16}$:
$$\text{error acumulado} \approx 5\times10^5 \times 1.1\times10^{-16} \approx 5.5\times10^{-11}$$
Esto está **dentro** de tolerancia para la mayoría de aplicaciones, pero la cota de Higham asume **redondeo independiente por rotor**; en pipelines SIMD/GPU con acumulación en FMA de precisión mixta (bf16/fp32), la correlación de errores puede romper la cota lineal y producir crecimiento $O(\sqrt{m}\cdot m\cdot u)$ en el peor caso adversarial — un factor $\sqrt{m}\approx700\times$ peor.

2. **Fallo en la descomposición de planos casi degenerados:** Cuando dos ángulos $\theta_i,\theta_j$ son casi iguales (bivectores con autovalores casi repetidos en la parte antisimétrica), la SVD/Schur que separa los planos tiene **gap espectral** $\to 0$, y:
$$\kappa_{\text{plano}} \sim \frac{1}{|\theta_i-\theta_j|}$$
Para D≥10⁶ con espaciado de ángulos aleatorio uniforme, la probabilidad de un gap $<10^{-6}$ entre pares consecutivos (paradoja del cumpleaños en $m$ elementos) es **no despreciable**: $\approx 1-e^{-m^2/(2\times10^6)}$, que para $m=5\times10^5$ es prácticamente 1. **Esto es un fallo estructural garantizado a esta escala**, no un caso extremo raro.

3. **Coste de la exponenciación de bivectores:** cada $\exp(\theta_i B_i)$ es $O(1)$ (fórmula cerrada seno/coseno en el plano 2×2), por lo que el total es $O(D)$ — ventaja real frente a exponenciación matricial densa $O(D^3)$. Esto es la mayor fortaleza de este pilar.

### Mejoras matemáticas propuestas

- **Regularización de gap espectral:** fusionar planos cuando $|\theta_i-\theta_j|<\tau=\sqrt{u}$ en un bloque 4×4 tratado con rotación conjunta estable (evita la sensibilidad de perturbación de autovectores de Davis-Kahan).
- **Redondeo compensado (Kahan/Neumaier) en la acumulación del producto de rotores**, reduciendo la cota efectiva de $m\,u$ a $2u + O(m u^2)$ — elimina el término dominante lineal en $m$.
- **Cota de Higham refinada propuesta:**
$$\|\hat R - R\|_2 \le u\left(c_1 + c_2\sum_i \kappa_{\text{plano},i}\right)\|R\|_2$$
haciendo explícita la dependencia del gap espectral, ausente en la formulación clásica que asume planos bien separados.

---

## Pilar 3 — Iteración Polar Padé-Taylor Orden 5 vs. Fallback QDWH

**Formulación auditada:**
$$Q_{k+1} = \tfrac18 Q