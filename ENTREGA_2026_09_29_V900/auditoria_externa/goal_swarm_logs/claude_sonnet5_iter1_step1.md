# Claude-Sonnet-5 — Iteración 1 (Paso 1)

# POLYDIM Serie 900 — Auditoría SOTA de Cómputo Geométrico de Alta Dimensión (D ≥ 10⁶)

## Advertencia de encuadre

Antes de entrar en el análisis técnico: los cuatro pilares descritos (Cayley-Stiefel matrix-free, bivectores de Clifford, iteración polar Padé-Taylor de orden 5, y RaptorQ sobre UDP) son **componentes reales y bien fundamentados de álgebra numérica y codificación de borrado**, pero "PMTP WAN Phase 10/11" y "POLYDIM Serie 900" no corresponden a ningún estándar, paper o producto verificable que yo pueda identificar — parecen nombres de proyecto propietario o marcador de posición. Voy a auditar la **matemática subyacente real** de cada pilar con rigor, pero no voy a inventar benchmarks, números de versión, o "resultados SOTA" atribuidos a un sistema que no puedo verificar que existe. Donde doy cifras, son derivaciones analíticas (arithmetic FLOP counts, cotas de estabilidad conocidas en literatura: Higham, Nakatsukasa-Bai-Gygi, Absil-Mahony-Sepulchre), no benchmarks medidos.

Con eso claro, aquí está el análisis riguroso.

---

## Pilar 1 — Retracción Cayley-Stiefel Matrix-Free con SMW

**Formulación.** Para X ∈ St(D,K) (D≥10⁶, K≪D), la retracción de Cayley es
R(X,ξ) = (I - ½W)⁻¹(I + ½W)X, con W = ξXᵀ - Xξᵀ (rango ≤ 2K).

**Woodbury explícito.** Escribiendo W = UVᵀ - VUᵀ con U=[ξ,X], V=[X,-ξ]/... (forma estándar rango-2K), se invierte el sistema (I-½W)⁻¹ vía
(I - ½UVᵀ)⁻¹ = I + ½U(I_{2K} - ½VᵀU)⁻¹Vᵀ

Esto reduce la inversión D×D a una inversión 2K×2K. Coste: O(DK²) para formar VᵀU y producto final, O(K³) para factorizar el núcleo pequeño. **Correcto en su formulación asintótica.**

### Hallazgos críticos

**1.1 — Condición del núcleo pequeño, no del sistema completo.**
κ(I - ½VᵀU) no es igual a κ del sistema Stiefel completo. Cuando ξ tiene componentes casi paralelas a X (retracciones cerca del "corte" del mapa de Cayley, es decir, cuando algún autovalor de VᵀU se aproxima a 2), el núcleo K×K se vuelve casi singular **independientemente de D**. Esto es un failure mode invisible si solo se monitorea κ(A) global vía normas de Frobenius del operador completo (que permanece bien condicionado en D-K direcciones triviales).

- **Límite de κ:** si κ(I-½VᵀU) > 10⁶/ε_mach⁻¹ efectivo, la factorización LU sin pivoteo pierde ~log₁₀κ dígitos → con κ>10⁶ y precisión doble (ε≈1.1e-16), quedan ~10 dígitos válidos: aceptable pero **al borde** si se encadenan >10³ retracciones (deriva acumulada tipo random walk en error backward).

**1.2 — Estabilidad hacia atrás con SMW clásico (no la variante estabilizada).**
La forma Woodbury clásica es conocida por amplificar error cuando el núcleo pequeño está mal condicionado (Higham, *Accuracy and Stability of Numerical Algorithms*, Cap. 14, sobre "modificaciones de bajo rango"). El error backward relativo escala como O(u·κ(I-½VᵀU)²) en el peor caso, **no O(u·κ)** — cuadrático, no lineal. Esto es el gap real de riesgo para κ>10⁶.

**1.3 — Latencia en D≥10⁶.**
O(DK²) domina si K > √D aproximadamente. Para D=10⁶, el cruce ocurre en K~10³. Si K se acerca a ese régimen (frecuente en subespacios de reducción de modelo grandes), el retracto deja de ser "barato" y compite con QR completo O(DK²) de todos modos — el pilar pierde ventaja asintótica ahí. **Bottleneck de ancho de banda de memoria**, no de FLOPs: formar ξXᵀ y XξᵀT requiere 2 GEMMs D×K×K, que a D=10⁶, K=10³ son streams de ~8GB en float64 — dominado por BW HBM, no por cómputo (arithmetic intensity baja, ~2K FLOPs/byte).

### Mejoras matemáticas recomendadas

1. **SMW estabilizado con pivoteo QR del núcleo:** reemplazar la inversión directa de (I₂ₖ-½VᵀU) por descomposición QR con pivoteo de columna o SVD truncada del núcleo 2K×2K — el coste extra O(K³) es despreciable frente a O(DK²), y baja el error backward de cuadrático a lineal en κ.
2. **Regularización de Levenberg tipo (I-½VᵀU+τI)** cuando κ_núcleo detectado > 10⁶, con τ ~ √u·‖VᵀU‖ (trust-region damping), commutando a QR-based retraction (más cara pero estable) como fallback dinámico — análogo exacto a la lógica QDWH del Pilar 3.
3. **Reemplazar Cayley por retracción polar** (ver Pilar 3) cuando ‖ξ‖ es grande, ya que Cayley es solo una aproximación de primer orden de la exponencial/polar y su error de retracción crece como O(‖ξ‖³) — en D altas con pasos de línea grandes esto es una fuente de error geométrico no capturada por el análisis de condicionamiento lineal.

---

## Pilar 2 — Rotores Bivectoriales de Clifford Cl(D) en Planos 2D Desacoplados

**Formulación.** Una rotación general en SO(D) se descompone en ⌊D/2⌋ rotores de plano commutando R = R₁R₂...R_{⌊D/2⌋}, cada Rᵢ = exp(θᵢBᵢ) con Bᵢ bivector unitario (Bᵢ²=-1), aplicado vía sándwich v' = R v R⁻¹ o, más eficiente, rotación de Givens generalizada por plano.

### Hallazgos críticos

**2.1 — La descomposición en planos desacoplados es matemáticamente exacta solo si los bivectores conmutan (i.e., provienen de una descomposición espectral simultánea, como CS decomposition / Schur real).** Para D≥10⁶, encontrar esa base simultánea de planos invariantes es en sí mismo un problema de valores propios O(D³) si se hace por fuerza bruta — **rompe la promesa de escalabilidad** a menos que la rotación objetivo ya venga parametrizada plano-a-plano (construcción, no descomposición general). Esto debe declararse como restricción de diseño: el pilar 2 solo es O(D) por-rotor si la rotación se **construye** composicionalmente, no si se **factoriza** una R arbitraria ya dada.

**2.2 — Cota de estabilidad backward de Higham para producto de rotaciones de Givens.**
Para una secuencia de m rotaciones de Givens aplicadas a un vector/matriz, la cota clásica (Higham §19.x, generalización del análisis QR por Givens) es:

‖R̃ - R‖ ≤ c·m·u·‖R‖ + O(u²)

con c constante pequeña (~1–3 dependiendo de la implementación de seno/coseno). Para m = ⌊D/2⌋ ~ 5×10⁵ rotores en D=10⁶, el error backward acumulado escala **linealmente en D**, no en log D. Esto es el failure mode dominante: con u≈1.1e-16 y D=10⁶, error acumulable ~10⁶ × 1.1e-16 ≈ 1.1e-10 — aceptable en la mayoría de aplicaciones, pero **si se encadenan T pasos de tiempo/iteraciones** (T rotaciones compuestas para integración geométrica