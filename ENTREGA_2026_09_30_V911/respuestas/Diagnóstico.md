<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## Diagnóstico

La brecha V911 está bien identificada: el problema no es `thread_local`, sino que `solve_linear_system_2k` materializa y resuelve un sistema denso ampliado de dimensión $2K$. La eliminación Gaussiana introduce $O(K^3)$ operaciones y $O(K^2)$ memoria, aunque la actualización de Cayley solo tiene rango efectivo $O(K)$.

La alternativa SOTA razonable es una cadena:

$$
\text{Cayley matrix-free}
\;+\;
\text{FGMRES}
\;+\;
\text{precondicionador Woodbury de bajo rango}
\;+\;
\text{restarts y precisión mixta}.
$$

La literatura sobre optimización en Stiefel confirma que la transformación de Cayley puede aprovechar la estructura de rango reducido mediante Sherman–Morrison–Woodbury, mientras que los métodos de Krylov matrix-free ya se han aplicado a ecuaciones de Newton riemannianas sobre Stiefel.[^1_1][^1_2]

## Estructura algebraica

Para $X\in\mathrm{St}(n,K)$ y una dirección tangente $Z$, una forma típica de la retracción de Cayley es

$$
Y(\alpha)
=
\left(I-\frac{\alpha}{2}\Omega\right)^{-1}
\left(I+\frac{\alpha}{2}\Omega\right)X,
$$

donde $\Omega^\top=-\Omega$. En vez de construir la matriz ampliada densa, debe explotarse que $\Omega$ actúa sobre $X$ y $Z$ mediante un espacio de dimensión pequeña.

Una factorización útil es

$$
\Omega = U V^\top - V U^\top,
$$

con $U,V\in\mathbb{R}^{n\times r}$ y $r\leq 2K$. Entonces

$$
I-\frac{\alpha}{2}\Omega
=
I + U_c V_c^\top,
$$

para matrices $U_c,V_c$ de dimensión $n\times r'$, con $r'=O(K)$. La identidad de Woodbury da

$$
(I+U_cV_c^\top)^{-1}b
=
b-U_c
\left(I+V_c^\top U_c\right)^{-1}
V_c^\top b.
$$

El sistema grande se sustituye por:

1. productos matriz-vector o matriz-bloque con $U_c,V_c$;
2. productos $V_c^\top b$;
3. una resolución densa de tamaño $r'\times r'$, típicamente $2K\times 2K$ o menor.

Esto no elimina toda dependencia cúbica si se factoriza el sistema pequeño en cada llamada, pero cambia el coste dominante de una resolución densa de tamaño ambiental a una resolución de dimensión proporcional al rango:

$$
O(nK^2+K^3),
$$

en lugar de una operación densa sobre el sistema completo. Si el núcleo reducido se reutiliza durante varios pasos, el coste amortizado puede aproximarse a

$$
O(nK^2)+O(K^2)
$$

por aplicación.

El punto importante es no ensamblar nunca $[A\mid B]$, ni la matriz $2K\times 2K$ completa cuando el operador pueda aplicarse como composición de productos y sumas.

## Qué debe hacer FGMRES

FGMRES es apropiado porque el precondicionador puede cambiar entre iteraciones, ser inexacto o utilizar diferentes niveles de precisión. En FGMRES se guardan dos bases:

- $V_j$: base ortonormal de los residuos;
- $Z_j=M_j^{-1}V_j$: vectores precondicionados.

La relación de Arnoldi es

$$
A Z_j = V_{j+1} H_j.
$$

La solución aproximada es

$$
x_m=x_0+Z_m y_m,
$$

donde

$$
y_m=\arg\min_y\|\beta e_1-H_my\|_2.
$$

La separación entre $V_j$ y $Z_j$ es precisamente lo que permite usar un precondicionador variable o inexacto. La formulación estándar de FGMRES se basa en esta descomposición y requiere conservar ambas familias de vectores.[^1_3]

### Aplicación al caso Cayley

El operador lineal que debe proporcionar `solve_linear_system_2k` no debería ser una matriz almacenada, sino una función:

```text
apply_A(x):
    return x - alpha/2 * omega_apply(x)
```

y el precondicionador:

```text
apply_Minv(r, iteration):
    return woodbury_preconditioner(r, iteration)
```

El algoritmo exterior sería:

```text
r = b - apply_A(x)
v[^1_0] = r / norm(r)

for j = 0 .. restart-1:
    z[j] = apply_Minv(v[j], j)
    w = apply_A(z[j])

    for i = 0 .. j:
        h[i,j] = dot(v[i], w)
        w -= h[i,j] * v[i]

    h[j+1,j] = norm(w)
    v[j+1] = w / h[j+1,j]

    apply_givens_rotations()
    test_residual()

solve_small_least_squares()
x += sum_j z[j] * y[j]
```

Para una implementación numéricamente robusta conviene usar MGS con reortogonalización selectiva, no una única pasada de Gram–Schmidt clásico.

## Precondicionador Woodbury recomendado

La opción más directa es separar el operador como

$$
A=P+UV^\top,
$$

donde $P$ es barato de invertir o aplicar aproximadamente. Entonces

$$
A^{-1}
=
P^{-1}
-
P^{-1}U
\left(I+V^\top P^{-1}U\right)^{-1}
V^\top P^{-1}.
$$

Un precondicionador aplicable a un residual $r$ es:

```text
q = apply_Pinv(r)
S = I + Vt * apply_Pinv(U)
t = solve_small(S, Vt * q)
z = q - apply_Pinv(U) * t
```

No se debe llamar a `apply_Pinv(U)` columna por columna si se dispone de BLAS de nivel 3: conviene aplicar el precondicionador a todo el bloque $U$. La matriz pequeña

$$
S=I+V^\top P^{-1}U
$$

debe factorizarse una sola vez mientras $P,U,V$ permanezcan invariantes. Para cambios suaves, puede actualizarse mediante QR o una refactorización periódica.

### Elección de $P$

Hay tres niveles prácticos:


| Nivel | $P$ | Ventaja | Riesgo |
| :-- | :-- | :-- | :-- |
| Básico | $I$ o diagonal | Muy simple | Muchas iteraciones |
| Intermedio | bloque diagonal / aproximación local | Buen equilibrio | Requiere identificar bloques |
| Avanzado | ILU/IC truncado, factorización dispersa o aproximación espectral | Menor número de iteraciones | Mayor coste y mantenimiento |

En este caso recomendaría empezar con

$$
P = I-\frac{\alpha}{2}\Omega_{\mathrm{local}},
$$

donde $\Omega_{\mathrm{local}}$ conserva los acoplamientos dominantes o una aproximación diagonal por bloques. El término restante se trata como corrección de bajo rango.

Si la matriz es antisimétrica y el problema es bien condicionado, $P$ puede ser casi unitario; en ese escenario un precondicionador excesivamente sofisticado puede costar más que las iteraciones que ahorra.

## Reducción adicional de rango

El rango algebraico máximo puede ser $2K$, pero el rango numérico puede ser considerablemente menor. Conviene calcular una compresión:

$$
UV^\top \approx U_rV_r^\top,\qquad r\ll 2K,
$$

mediante:

- QR con pivotado;
- SVD truncada;
- interpolative decomposition;
- eigendecomposición pequeña de $V^\top U$;
- randomized range finder, si $K$ es grande.

El criterio debe ser relativo:

$$
\sigma_{r+1}\leq \tau \sigma_1,
$$

con $\tau$ ligado a la tolerancia de FGMRES, por ejemplo entre $10^{-6}$ y $10^{-10}$, dependiendo de la precisión objetivo.

No debe comprimirse a ciegas: una reducción agresiva puede destruir la ortogonalidad de la retracción o empeorar el espectro del sistema precondicionado.

## Estrategia híbrida recomendada

La arquitectura que implementaría es:

### Fase 1: operador matrix-free

Implementar únicamente:

```cpp
void omega_apply(const Vec& x, Vec& y);
void cayley_apply(const Vec& x, Vec& y);
void preconditioner_apply(const Vec& r, Vec& z);
```

`omega_apply` debe explotar la factorización de rango reducido y no construir $\Omega$.

### Fase 2: FGMRES reiniciado

Usar FGMRES($m$) con:

- $m\in[20,80]$ como punto de partida;
- Givens rotations para el least-squares incremental;
- MGS con reortogonalización;
- restart adaptativo;
- criterio de parada basado en residual verdadero.

La literatura de FGMRES enfatiza que el método es adecuado precisamente cuando el precondicionador cambia o solo se aplica aproximadamente.[^1_4][^1_3]

### Fase 3: Woodbury reutilizable

Construir una caché que contenga:

```text
U
V
PinvU
S = I + Vᵀ PinvU
factorization(S)
```

Recalcularla solo cuando cambie significativamente $\alpha$, $X$, $Z$ o la aproximación local $P$.

### Fase 4: control inexacto

No es necesario resolver el sistema pequeño con precisión máxima en cada iteración. Puede usarse:

- FP32 para productos y FGMRES;
- FP64 para el pequeño sistema Woodbury y correcciones;
- refinamiento iterativo si el residual verdadero se estanca.

La precisión interna debe adaptarse al residual exterior. Al inicio pueden permitirse solves internos inexactos; cerca de convergencia hay que aumentar la precisión.

## Alternativas SOTA

### 1. Newton-Krylov truncado

Si el sistema procede de una ecuación de Newton riemanniana, no es necesario resolver exactamente en cada paso. Usar un método Newton–Krylov truncado con forcing term de Eisenstat–Walker:

$$
\|F(x)+J(x)s\|
\leq
\eta_k\|F(x)\|.
$$

Esto evita sobrerresolver los sistemas lineales lejos de la solución. La combinación matrix-free Newton + Krylov ya está documentada para Newton riemanniano sobre Stiefel.[^1_5][^1_6]

### 2. Recycling FGMRES

Entre iteraciones de optimización, los sistemas de Cayley suelen cambiar gradualmente. Se puede reciclar un subespacio aproximado de Ritz o armónico:

$$
\mathcal{U}_k=\operatorname{span}\{u_1,\dots,u_q\}.
$$

Métodos como GCRO-DR, recycled GMRES o RFGMRES pueden reducir drásticamente el número de iteraciones cuando $X$, $\alpha$ y el Hessiano varían poco.

### 3. Deflation

Si existen modos lentos asociados a valores propios cercanos a cero, incorporar deflación o coarse correction. Esto es especialmente útil si la matriz ampliada tiene modos geométricos o grados de libertad casi redundantes.

### 4. Multi-preconditioning

En lugar de elegir un único precondicionador, puede combinarse:

- Woodbury de bajo rango;
- diagonal por bloques;
- aproximación espectral;
- una iteración fija de Richardson o Chebyshev.

FGMRES permite cambiar de precondicionador, mientras que MPGMRES puede combinar varios precondicionadores en una base más rica. La literatura de multi-preconditioned GMRES muestra que esta estrategia puede ser útil, aunque el método completo aumenta rápidamente coste y almacenamiento; la variante truncada es más práctica.[^1_3]

### 5. Iteración fija de Cayley

Para ciertos regímenes, puede sustituirse la resolución por una iteración fija:

$$
Y_{j+1}
=
X+\frac{\alpha}{2}\Omega(X+Y_j).
$$

Es una alternativa matrix-free que solo necesita productos con $\Omega$. Sin embargo, debe evaluarse su radio espectral:

$$
\rho\left(\frac{\alpha}{2}\Omega\right)<1.
$$

Si $\alpha\|\Omega\|$ es grande, la iteración puede ser lenta o divergir. La literatura reciente también identifica esta alternativa como forma de evitar la inversión explícita en la transformación de Cayley. [^1_7][^1_8]

## Complejidad esperada

Suponiendo $n$ filas y rango efectivo $r=O(K)$:


| Operación | Implementación densa actual | Propuesta matrix-free |
| :-- | --: | --: |
| Construcción del sistema | $O(K^2)$ memoria ampliada | No se construye |
| Resolución principal | $O(K^3)$ | $O(r^3)$ reducido o iterativo |
| Aplicación a vector | Implícita en solve denso | $O(nr)$–$O(nr+r^2)$ |
| Memoria | $O(K^2)$ o mayor | $O(nr+mr)$ |
| Paralelismo | Limitado por solve denso | Productos por bloques y Arnoldi |
| Reutilización | Baja | Alta mediante caché Woodbury |

La afirmación correcta no es que FGMRES elimine automáticamente toda complejidad cúbica. El resultado depende de que:

1. $r\ll n$;
2. el sistema Woodbury reducido pueda reutilizarse;
3. el número de iteraciones no crezca proporcionalmente con $K$;
4. el operador matrix-free sea barato.

En el mejor caso práctico, el cuello de botella pasa de una factorización cúbica a productos de bloque y un solve pequeño amortizado.

## Plan de implementación

### Prioridad P0

- Extraer `omega_apply`.
- Eliminar la construcción de $[A\mid B]$.
- Implementar FGMRES($m$) con solve least-squares incremental.
- Añadir residual verdadero cada $5$–$10$ iteraciones.
- Comparar contra el solver Gaussiano actual en problemas pequeños.


### Prioridad P1

- Implementar Woodbury con $P=I$.
- Añadir caché de $V^\top P^{-1}U$.
- Introducir compresión QR/SVD del rango.
- Añadir mixed precision.
- Instrumentar tiempo en:
    - productos;
    - ortogonalización;
    - solve reducido;
    - reconstrucción de $x$.


### Prioridad P2

- $P$ diagonal por bloques o ILU truncado.
- Recycling entre retractions consecutivas.
- Forcing terms para Newton-Krylov truncado.
- Restart adaptativo y deflación.
- Paralelización de productos por bloques.


### Validación científica

El benchmark debe incluir:

- error relativo de la solución lineal;
- error de ortogonalidad $\|Y^\top Y-I\|_F$;
- número de iteraciones FGMRES;
- número de aplicaciones de $A$ y $M^{-1}$;
- tiempo y memoria pico;
- sensibilidad a $\alpha$, $K$, tolerancia y rango truncado;
- comparación contra:
    - eliminación Gaussiana;
    - QR;
    - Cayley-Woodbury directo;
    - FGMRES sin precondicionar;
    - FGMRES con Woodbury;
    - iteración fija de Cayley.

La métrica central no debe ser solo el tiempo por iteración, sino el coste total hasta alcanzar simultáneamente

$$
\frac{\|b-Ax\|}{\|b\|}
\leq \varepsilon_{\mathrm{lin}}
\quad\text{y}\quad
\|Y^\top Y-I\|_F\leq\varepsilon_{\mathrm{orth}}.
$$

## Recomendación final

La solución más sólida para V911 es implementar primero **FGMRES matrix-free con precondicionador Woodbury reutilizable y compresión de rango**, manteniendo el solver denso como ruta de verificación para tamaños pequeños. Después conviene añadir Newton-Krylov truncado, recycling y precisión mixta.

La sustitución directa por iteración fija de Cayley puede ser muy barata, pero debe considerarse una ruta aproximada y condicionada por $\alpha\|\Omega\|$. Para una solución científica robusta, FGMRES ofrece mejor control de convergencia, tolera precondicionadores variables y encaja naturalmente con la estructura de bajo rango del problema.

<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://scipost.org/SciPostPhys.10.2.040/pdf

[^1_2]: https://www.comm.tcu.ac.jp/aiharak-sc/publication_en.html

[^1_3]: https://www.cs.ubc.ca/sites/default/files/tr/2011/TR-2011-12_0.pdf

[^1_4]: https://par.nsf.gov/servlets/purl/10439492

[^1_5]: https://www.semanticscholar.org/paper/A-matrix-free-implementation-of-Riemannian-Newton’s-Aihara-Sato/0dd8158481f5ec72e098af12bf0c20c21584301c

[^1_6]: https://sites.google.com/site/hiroyukisatojpn/home/publication

[^1_7]: https://www.cise.ufl.edu/research/cad/Publications/qce24characterization.pdf

[^1_8]: https://arxiv.org/html/2609.21039v1

[^1_9]: https://www.osti.gov/servlets/purl/1438714

[^1_10]: https://www.cs.ubc.ca/~greif/Publications/grs2012.pdf

[^1_11]: https://kaken.nii.ac.jp/ja/file/KAKENHI-PROJECT-15K17498/15K17498seika.pdf

[^1_12]: https://hal.science/hal-05071696v1/document

[^1_13]: https://arxiv.org/html/2410.07465v1

[^1_14]: https://icl.utk.edu/files/publications/2014/icl-utk-762-2014.pdf

[^1_15]: https://pure.rug.nl/ws/files/76262613/1_s2.0_S0020740318302790_main.pdf

[^1_16]: https://www.cerfacs.fr/algor/reports/2006/TR_PA_06_09.pdf

[^1_17]: https://hrcak.srce.hr/file/498938

[^1_18]: https://raw.githubusercontent.com/mlresearch/v235/main/assets/vary24a/vary24a.pdf

[^1_19]: https://sites.google.com/site/hiroyukisatojpn/home/talks

[^1_20]: https://openreview.net/pdf/b5f2172ec2d8f0327b737b6a108a28189233304b.pdf

[^1_21]: https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-15K17498/

[^1_22]: https://arxiv.org/html/2311.00907v2

[^1_23]: https://www.jstage.jst.go.jp/article/jsiamt/28/4/28_205/\_article/-char/en

[^1_24]: https://optimization-online.org/wp-content/uploads/2016/09/5617.pdf

[^1_25]: https://optimization-online.org/wp-content/uploads/2022/07/Accelerated-gradient-methods-on-the-Grassmann-and-Stiefel-manifolds-1.pdf

[^1_26]: https://sites.google.com/site/hiroyukisatoeng/home/publications-and-talks

[^1_27]: https://cseweb.ucsd.edu/classes/sp24/cse291-e/papers/StiefelManifold/StiefelNotes.pdf


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La mejora SOTA no es únicamente sustituir la eliminación Gaussiana por FGMRES. El diseño más sólido para V911 es una **reformulación de bajo rango de la transformación de Cayley**, resuelta mediante **FGMRES flexible, deflación/recycling, precondicionamiento Woodbury, precisión mixta y control inexacto tipo Newton–Krylov**.

## 1. Reformulación correcta de Cayley

La actualización de Wen–Yin puede escribirse como

$$
Y(\tau)
=
X-\tau U
\left(I_{2K}+\frac{\tau}{2}V^\top U\right)^{-1}
V^\top X,
$$

donde $U,V\in\mathbb{R}^{n\times 2K}$. Esta fórmula ya evita resolver el sistema ambiental grande: solo requiere un sistema reducido de dimensión $2K$. La literatura la identifica como una actualización equivalente a Cayley/Crank–Nicolson y especialmente eficiente para restricciones de ortogonalidad.[^2_1][^2_2]

La consecuencia práctica es importante:

- no resolver un sistema denso $n\times n$;
- no ensamblar $[A\mid B]$;
- no aplicar eliminación Gaussiana sobre un sistema artificial de tamaño $2K$ si puede evitarse;
- trabajar con productos $Uq$, $V^\top x$ y un operador reducido.

La implementación debería exponer la acción

$$
q\mapsto V^\top q,\qquad
c\mapsto Uc,
$$

y construir el operador de Cayley solo como composición de estas acciones.

## 2. Qué parte debe ser iterativa

Hay dos escenarios diferentes.

### Caso A: sistema reducido pequeño

Si $K$ es moderado, la mejor solución puede ser:

$$
S=I_{2K}+\frac{\tau}{2}V^\top U,
$$

factorizar $S$ mediante pivotado o QR, y reutilizar la factorización. En este escenario FGMRES no necesariamente mejora el coste: resolver exactamente un sistema reducido $2K\times 2K$ puede ser más barato y más estable.

### Caso B: $K$ grande o sistema ampliado implícito

Si el sistema actual escala con $K$, si se usa un bloque grande o si el operador viene de una Hessiana/Jacobiano implícito, entonces conviene FGMRES matrix-free:

$$
\mathcal{A}(z)=Pz+UV^\top z,
$$

sin materializar $\mathcal{A}$. FGMRES resulta apropiado porque acepta precondicionadores variables, inexactos o no lineales. Esta flexibilidad es central cuando la inversión interna se aproxima o cambia durante Arnoldi.[^2_3][^2_4]

La decisión debe basarse en un benchmark, no en la etiqueta “matrix-free”: para $2K\leq 100$, un solve directo pequeño probablemente ganará; para $K$ grande, FGMRES empieza a ser atractivo.

## 3. Precondicionador Woodbury de nivel avanzado

La descomposición recomendada es

$$
\mathcal A=P+UCV^\top,
$$

con $P$ barato de aplicar o invertir. Entonces

$$
\mathcal A^{-1}
=
P^{-1}
-
P^{-1}U
\left(C^{-1}+V^\top P^{-1}U\right)^{-1}
V^\top P^{-1}.
$$

Para un residual $r$:

$$
q=P^{-1}r,
$$

$$
G=P^{-1}U,
$$

$$
S=C^{-1}+V^\top G,
$$

$$
z=q-GS^{-1}V^\top q.
$$

La matriz $S$ tiene tamaño igual al rango reducido, no al tamaño ambiental. La inversión de $S$ debe realizarse una vez y reutilizarse hasta que cambien sustancialmente $P,U,V$.

### Mejoras relevantes

#### Compresión adaptativa

No asumir que el rango es exactamente $2K$. Aplicar QR pivotado o SVD truncada:

$$
UV^\top\approx U_rV_r^\top,\qquad r\ll 2K.
$$

Una regla adecuada es elegir el menor $r$ que satisfaga

$$
\frac{\|UV^\top-U_rV_r^\top\|}{\|UV^\top\|}
\leq \tau_{\mathrm{rank}}.
$$

Para estabilidad de la retraction, $\tau_{\mathrm{rank}}$ no debe elegirse independientemente de la precisión geométrica. Como regla inicial:

$$
\tau_{\mathrm{rank}}
\leq
0.1\,\varepsilon_{\mathrm{orth}}.
$$

#### Precondicionador espectral

En lugar de usar solo $P=I$, construir una aproximación de los modos lentos:

$$
P^{-1}\approx I+Q(\Lambda^{-1}-I)Q^\top.
$$

Esto es útil cuando el problema tiene autovalores pequeños o clusters espectrales. Las aproximaciones randomizadas de bajo rango y los precondicionadores basados en Nyström son líneas activas para acelerar GMRES evitando inversas grandes.[^2_5][^2_6]

#### Precondicionador compuesto

Usar en secuencia:

$$
M^{-1}
=
M_{\mathrm{local}}^{-1}
M_{\mathrm{Woodbury}}^{-1},
$$

donde $M_{\mathrm{local}}$ puede ser diagonal por bloques, ILU truncado o una aproximación de Hessiana. FGMRES permite variar el número de pasos internos o cambiar $M_{\mathrm{local}}$ entre iteraciones.

## 4. FGMRES con precondicionamiento inexacto

El error interno no necesita ser constante. Definir una tolerancia adaptativa:

$$
\|r_{\mathrm{inner},j}\|
\leq
\eta_j\|r_{\mathrm{outer},j}\|.
$$

Una estrategia práctica:

$$
\eta_j
=
\min\left(\eta_{\max},
c\left(\frac{\|r_j\|}{\|r_0\|}\right)^\gamma\right),
$$

con, por ejemplo,

$$
\eta_{\max}=10^{-1},\qquad
c=0.5,\qquad
\gamma\in[0.5,1].
$$

Esto evita resolver con alta precisión las primeras iteraciones, cuando el vector de Newton todavía es aproximado. El análisis moderno de FGMRES también estudia explícitamente su convergencia en dos fases según la precisión del precondicionador interno.[^2_7]

La interpretación es:

- fase inicial: precondicionamiento barato e inexacto;
- fase final: precondicionamiento preciso y residual confiable.


## 5. Recycling y deflación

En una optimización sobre Stiefel, las sucesivas matrices de Cayley suelen cambiar gradualmente. Reiniciar FGMRES desde cero desperdicia información.

Se recomienda mantener un subespacio reciclado:

$$
\mathcal U=\operatorname{span}\{u_1,\dots,u_q\},
$$

formado por vectores de Ritz asociados a los modos lentos. En cada nuevo solve:

1. proyectar el residual contra $\mathcal U$;
2. ejecutar FGMRES sobre el complemento;
3. actualizar $\mathcal U$ periódicamente.

La combinación FGMRES con deflación/restart es una dirección SOTA especialmente relevante cuando hay autovalores cercanos a cero; GMRES reiniciado puede perder información al final de cada ciclo, mientras que deflación conserva los modos difíciles.[^2_8]

Para V911, una versión razonable es:

- $q=5$–$20$ vectores reciclados;
- restart $m=30$–$80$;
- actualización de $\mathcal U$ cada 3–10 retracciones;
- descartar vectores cuya energía o norma caiga por debajo del umbral.


## 6. Ortogonalización: posible cuello de botella oculto

Cuando $m$ crece, Arnoldi puede dejar de estar dominado por `apply_A`; la ortogonalización pasa a costar $O(nm^2)$. Por ello:

- usar Modified Gram–Schmidt;
- reortogonalizar solo si el nuevo vector pierde ortogonalidad;
- usar Householder/TSQR para bloques;
- considerar randomized block orthogonalization en arquitecturas paralelas.

La ortogonalización randomizada y el sketching para GMRES bloqueado son líneas recientes para reducir sincronizaciones y mejorar estabilidad.[^2_9][^2_10]

Para una primera implementación CPU:

```text
w = apply_A(z_j)

for i = 0..j:
    h[i,j] = dot(v_i, w)
    w -= h[i,j] * v_i

if norm(w) deteriorates:
    repeat orthogonalization
```

Para GPU o sistemas distribuidos, conviene pasar pronto a bloques y reducir global reductions.

## 7. Precisión mixta

Una ruta eficiente es:


| Componente | Precisión recomendada |
| :-- | :-- |
| Productos $Uq$, $V^\top x$ | FP32 o TF32 |
| Arnoldi | FP32 con corrección selectiva |
| Matriz reducida Woodbury | FP64 |
| Residual verdadero | FP64 |
| Ortogonalidad $Y^\top Y-I$ | FP64 |
| Refinamiento final | FP64 |

La precisión mixta no debe aplicarse uniformemente. Los productos dominantes pueden ejecutarse en baja precisión, pero la factorización del sistema reducido, el residual verdadero y la comprobación de ortogonalidad requieren mayor precisión. Estudios recientes señalan que la elección entre precondicionamiento izquierdo, derecho y flexible afecta significativamente la robustez bajo precisión mixta.[^2_11]

La arquitectura recomendada es:

$$
\text{FGMRES}_{\mathrm{FP32}}
+
\text{Woodbury}_{\mathrm{FP64}}
+
\text{residual/refinement}_{\mathrm{FP64}}.
$$

## 8. Newton–Krylov truncado

Si `solve_linear_system_2k` forma parte de una iteración de Newton o Gauss–Newton, no conviene resolver cada sistema lineal con la misma tolerancia. Usar un forcing term:

$$
\|F(x_k)+J(x_k)s_k\|
\leq
\eta_k\|F(x_k)\|.
$$

Una política típica:

$$
\eta_k
=
\min\left(0.9,\,
\frac{\|F(x_k)-F(x_{k-1})-J(x_{k-1})s_{k-1}\|}
{\|F(x_{k-1})\|}\right).
$$

Lejos de la solución se permite un solve aproximado; cerca de la solución se aumenta la precisión. Esto evita que el coste cúbico o las iteraciones Krylov dominen cuando todavía no se necesita una dirección exacta.

## 9. Alternativas a FGMRES

### Cayley directa de Wen–Yin

Si la estructura de bajo rango es exacta, la fórmula reducida directa probablemente sea superior a FGMRES. Debe ser la ruta rápida para $K$ pequeño o moderado.[^2_1]

### BiCGSTAB o IDR(s)

Pueden usar menos memoria que FGMRES, pero son menos robustos cuando el precondicionador varía y pueden presentar picos de residual. No serían la ruta principal para V911.

### MINRES

Solo si el sistema reformulado es simétrico o hermítico. La matriz de Cayley y muchos sistemas ampliados asociados no son necesariamente SPD, por lo que no debe asumirse aplicabilidad.

### Iteración fija

Una iteración Richardson/Cayley es válida si el operador precondicionado satisface

$$
\rho(I-M^{-1}A)<1.
$$

Es extremadamente barata, pero menos robusta que FGMRES y sensible al escalado.

### Multigrid o domain decomposition

Si el sistema ambiental tiene estructura espacial o PDE, un precondicionador geométrico/algebraico multinivel puede superar a Woodbury. Woodbury debería tratar la corrección global de bajo rango, mientras que multigrid elimina los errores locales:

$$
A\approx P_{\mathrm{MG}}+UV^\top.
$$

## 10. Diseño de software

La interfaz debe separar estrictamente operador, precondicionador y geometría:

```cpp
struct LinearOperator {
    void apply(const Vector& x, Vector& y) const;
    void apply_block(const Matrix& X, Matrix& Y) const;
};

struct FlexiblePreconditioner {
    void apply(const Vector& r, Vector& z, int iteration) const;
};

struct CayleyContext {
    Matrix U;
    Matrix V;
    Matrix PinvU;
    Matrix S_factor;
    double tau;
};
```

La ruta crítica debe ser:

```cpp
apply_A(x, y):
    tmp = V.transpose() * x
    y = P * x + U * tmp

apply_Minv(r, z):
    q = apply_Pinv(r)
    t = V.transpose() * q
    s = solve_small(S_factor, t)
    z = q - PinvU * s
```

Buenas prácticas:

- usar almacenamiento column-major para bloques;
- fusionar $V^\top x$ y $Uq$ cuando sea posible;
- evitar asignaciones dentro de Arnoldi;
- reservar todas las bases al inicio;
- usar vistas y `thread_local` solo para buffers, no para resolver el problema algorítmico;
- almacenar $U,V$ en formato bloqueado compatible con BLAS-3;
- no formar productos como $UV^\top$.


## 11. Complejidad refinada

Con $n$ dimensión ambiental, rango $r$, restart $m$, y $s$ ciclos:

### Preprocesamiento

$$
O(nr^2+r^3)
$$

para construir y factorizar el sistema reducido.

### Cada aplicación de operador

$$
O(nr)
$$

o $O(nr+r^2)$, según el precondicionador.

### Cada ciclo FGMRES

$$
O(mnr+nm^2).
$$

El primer término corresponde a las aplicaciones matrix-free y el segundo a Arnoldi. Si $m$ es demasiado grande, la ortogonalización domina.

### Memoria

$$
O(n(r+m)+r^2).
$$

Esto es preferible a almacenar una matriz densa ampliada de tamaño $2K$ cuando $n$ o el número de bloques crece.

## 12. Plan experimental SOTA

El benchmark debe variar independientemente:

- $n$;
- $K$;
- rango numérico $r$;
- $\tau$;
- condición de $S$;
- tolerancia lineal;
- restart;
- precisión;
- variabilidad del precondicionador.

Comparar:

1. Gauss denso actual.
2. QR directo.
3. Cayley reducida Wen–Yin.
4. FGMRES sin precondicionador.
5. FGMRES + Woodbury.
6. FGMRES + Woodbury + compresión.
7. FGMRES-DR/recycling.
8. FGMRES con precisión mixta.
9. Newton–Krylov truncado.

Medir:

$$
\frac{\|b-Ax\|}{\|b\|},
\qquad
\|Y^\top Y-I\|_F,
\qquad
\frac{\|Y-Y_{\mathrm{direct}}\|}{\|Y_{\mathrm{direct}}\|},
$$

además de tiempo total, memoria, número de productos y número de factorizaciones reducidas.

## Recomendación concreta

La ruta científica con mejor equilibrio entre riesgo y rendimiento es:

1. **Implementar primero la fórmula reducida de Cayley** y compararla con el solve actual.
2. **Eliminar completamente $[A\mid B]$** de la ruta de producción.
3. Añadir **FGMRES matrix-free** solo para el operador grande o inexacto.
4. Usar **Woodbury con $P$ diagonal por bloques**.
5. Comprimir $U,V$ mediante **QR pivotado**.
6. Añadir **recycling/deflación** entre retracciones.
7. Aplicar **forcing terms** de Newton–Krylov.
8. Usar precisión mixta, con residual y ortogonalidad en FP64.
9. Mantener el solver directo como oráculo de validación para tamaños pequeños.

La mejora más importante no será simplemente pasar de $O(K^3)$ a “FGMRES”. Será reemplazar la representación densa por una factorización operatorial de bajo rango y lograr que el solve reducido, el precondicionador y el subespacio de Krylov se **reutilicen** entre iteraciones.

<span style="display:none">[^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_20][^2_21][^2_22][^2_23][^2_24][^2_25][^2_26][^2_27][^2_28][^2_29][^2_30][^2_31][^2_32]</span>

<div align="center">⁂</div>

[^2_1]: https://optimization-online.org/wp-content/uploads/2013/01/3721.pdf

[^2_2]: https://scispace.com/authors/zaiwen-wen-3l3hbzcvtw

[^2_3]: https://par.nsf.gov/servlets/purl/10439492

[^2_4]: https://www.cs.ubc.ca/sites/default/files/tr/2011/TR-2011-12_0.pdf

[^2_5]: https://www.informs-sim.org/wsc25papers/inv132.pdf

[^2_6]: https://www.emergentmind.com/topics/nystrom-preconditioner

[^2_7]: https://arxiv.org/pdf/2604.27971v1.pdf

[^2_8]: https://arxiv.org/html/2110.04017v2

[^2_9]: https://householder-symposium.github.io/schedule.pdf

[^2_10]: https://arxiv.org/html/2503.16717v3

[^2_11]: https://bvieuble.me/publications/

[^2_12]: https://www.sciencedirect.com/science/article/abs/pii/S0377042724002747

[^2_13]: https://proceedings.iclr.cc/paper_files/paper/2025/file/3bb7e33e4da1fd19ebc6f0899e45a9dc-Paper-Conference.pdf

[^2_14]: https://onlinelibrary.wiley.com/doi/10.1002/nla.70077

[^2_15]: https://link.springer.com/article/10.1007/s10444-021-09880-9?error=cookies_not_supported\&code=cea0cf86-7335-45fd-89de-2a0b8183a50b

[^2_16]: https://journals.sagepub.com/doi/10.1177/10943420251317994

[^2_17]: https://sparsedays.cerfacs.fr/wp-content/uploads/sites/72/2025/05/Sparse-days-2025-booklet.pdf

[^2_18]: https://grandmaster.colorado.edu/copper/2025/program-static/index.html

[^2_19]: https://jso.dev/Krylov.jl/stable/preconditioners/

[^2_20]: https://github.com/JunLi-Galios/Optimization-on-Stiefel-Manifold-via-Cayley-Transform

[^2_21]: https://www.emergentmind.com/topics/krylov-solvers

[^2_22]: https://www.firedrakeproject.org/firedrake/matrix-free.html

[^2_23]: https://epubs.siam.org/doi/abs/10.1137/0720023

[^2_24]: https://epubs.siam.org/doi/10.1137/0907058

[^2_25]: https://epubs.siam.org/doi/10.1137/20M1348571

[^2_26]: https://arxiv.org/html/2512.15455v1

[^2_27]: https://openreview.net/attachment?id=HJxV-ANKDH\&name=original_pdf

[^2_28]: https://openreview.net/pdf?id=c2OtbtZXFC

[^2_29]: https://www2.cse.iitk.ac.in/~iwml/2016/papers/iWML_2016_paper_20.pdf

[^2_30]: https://arxiv.org/html/2609.21039v1

[^2_31]: https://arxiv.org/html/2311.00907v2

[^2_32]: https://optimization-online.org/wp-content/uploads/2016/09/5617.pdf


---

# 2. Cadena de Herramientas de Compilación (pybind11 Incompleto) evalua mejoras y soluciones cientificas SOTA

Brecha (V911): Se inyectó el código C++ para pybind11 y setup_v911.py, pero la compilación transparente vía g++ falló debido al mapeo de librerías estáticas de Python (cannot find .2 - error de linkeo/PowerShell con el flag -msse4.2). Por lo tanto, el módulo ctypes sigue soportando la carga.
Solución Asintótica Pendiente: Intervención profunda en la infraestructura de build. Se debe configurar CMakeLists.txt nativo para Windows o forzar la compilación explícita mediante setuptools, asegurando el binding C++-Python seguro (Fase 2).

La brecha V911 no debe resolverse intentando perfeccionar el comando `g++` actual. El fallo revela una mezcla de toolchains y modelos de enlace: Python oficial para Windows se construye con MSVC, mientras que `g++`/MinGW busca bibliotecas con convenciones distintas. La solución SOTA es convertir el binding en un artefacto nativo reproducible, con **CMake + `FindPython` moderno**, y usar **setuptools o scikit-build-core** como backend de empaquetado, no como sustituto improvisado del linker.

## Diagnóstico del fallo

### Error `cannot find .2`

Un error como:

```text
cannot find .2
```

suele indicar que un flag de enlace se ha partido incorrectamente o que una ruta terminada en `.2` fue interpretada como nombre de biblioteca. Las causas probables son:

- uso de `python-config` o `python3-config` de Unix en PowerShell;
- expansión incorrecta de flags shell;
- conversión defectuosa de `-lpython3.x` a una ruta Windows;
- mezcla de `g++`, Python MSVC y bibliotecas `.lib`;
- una variable de CMake que contiene flags separados por espacios cuando debería ser una lista;
- generación manual de `-L...`, `-l...` y `-Wl,...` para una plataforma que utiliza `/LIBPATH:` y `.lib`.

En Windows no debe copiarse literalmente el comando Linux:

```bash
g++ ... $(python3-config --includes) ... $(python3-config --ldflags)
```

Ese patrón depende de sustitución de comandos Unix y no es una estrategia portable.

### Flag `-msse4.2`

`-msse4.2` es un flag de GCC/Clang. Con MSVC no es el mecanismo correcto; además, habilitarlo globalmente puede producir un módulo que no arranque en CPUs antiguas.

Usar:

- MSVC: `/arch:AVX2` solo si se acepta esa dependencia, o ninguna opción explícita para SSE;
- GCC/Clang: `-msse4.2`, `-mavx2`, etc., exclusivamente cuando el compilador sea GCC/Clang;
- dispatch dinámico: compilar rutas SSE/AVX separadas y seleccionar en runtime.

El binding de pybind11 debería mantenerse neutral respecto a SIMD; las optimizaciones deben quedar en el núcleo numérico.

## Arquitectura recomendada

Separar el proyecto en tres capas:

```text
v911/
├── pyproject.toml
├── CMakeLists.txt
├── cmake/
├── cpp/
│   ├── core/
│   └── bindings/
├── python/
│   └── v911/
└── tests/
```


### Núcleo C++

El solver no debe depender de Python:

```text
cpp/core/
    solver.hpp
    solver.cpp
    cayley.hpp
    krylov.hpp
```


### Binding

El binding solo convierte tipos y gestiona excepciones:

```text
cpp/bindings/module.cpp
```


### Frontend Python

Debe tener fallback explícito:

```python
try:
    from ._v911_native import solve_linear_system
except ImportError:
    from ._v911_ctypes import solve_linear_system
```

Esto conserva la ruta `ctypes`, pero hace que el módulo nativo sea el backend preferido cuando esté disponible.

## CMakeLists.txt recomendado

Para una extensión Python en Windows, usar `FindPython` moderno y targets importados. pybind11 recomienda `find_package(Python COMPONENTS Interpreter Development)` y `find_package(pybind11 CONFIG REQUIRED)`; `pybind11_add_module` configura automáticamente include paths, extensión, flags específicos y enlace de módulo.[^3_1][^3_2]

```cmake
cmake_minimum_required(VERSION 3.20...4.2)

project(v911 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(PYBIND11_FINDPYTHON ON)

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

add_library(v911_core STATIC
    cpp/core/solver.cpp
    cpp/core/cayley.cpp
    cpp/core/krylov.cpp
)

target_include_directories(v911_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/cpp/core
)

if(MSVC)
    target_compile_options(v911_core PRIVATE /W4 /EHsc)
else()
    target_compile_options(v911_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

pybind11_add_module(_v911_native
    cpp/bindings/module.cpp
)

target_link_libraries(_v911_native
    PRIVATE
        v911_core
        pybind11::module
)

set_target_properties(_v911_native PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

install(TARGETS _v911_native
    LIBRARY DESTINATION v911
    RUNTIME DESTINATION v911
)
```

Puntos importantes:

- no escribir manualmente `-lpython`;
- no usar `PythonLibs` antiguo;
- no pasar `-msse4.2` a todos los compiladores;
- usar `Python::Module`/`pybind11::module` para una extensión;
- reservar `pybind11::embed` para un ejecutable que incrusta el intérprete.

La documentación distingue explícitamente entre `pybind11::module`, para extensiones, y `pybind11::embed`, para incrustar Python.[^3_2][^3_1]

## Configuración Windows

### Visual Studio

Es la ruta recomendada para CPython oficial. La documentación de empaquetado señala que Windows usa Visual C para construir CPython y que las extensiones compatibles deben construirse con MSVC.[^3_3]

Configurar desde “Developer PowerShell for VS”:

```powershell
py -3.12 -m pip install -U pip cmake ninja pybind11 scikit-build-core
cmake -S . -B build `
  -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DPython_EXECUTABLE="$((Get-Command py).Source)"
cmake --build build --parallel
```

Sin embargo, `Python_EXECUTABLE` debe apuntar al ejecutable real de Python, no necesariamente al launcher `py.exe`. Es más robusto:

```powershell
$PY = python -c "import sys; print(sys.executable)"
$PYPATH = python -c "import pybind11; print(pybind11.get_cmake_dir())"

cmake -S . -B build -G Ninja `
  -DPython_EXECUTABLE="$PY" `
  -Dpybind11_DIR="$PYPATH" `
  -DCMAKE_BUILD_TYPE=Release
```


### CMake Visual Studio

Alternativamente:

```powershell
cmake -S . -B build `
  -G "Visual Studio 17 2022" `
  -A x64 `
  -DPython_EXECUTABLE="$PY" `
  -Dpybind11_DIR="$PYPATH"

cmake --build build --config Release
```

No mezclar en el mismo árbol:

- Ninja + MSVC;
- Visual Studio generator + MinGW;
- x64 + Python x86;
- Python de Conda + librerías de Python oficial.

Después de cambiar de compilador o de Python, borrar el cache:

```powershell
Remove-Item -Recurse -Force build
```

La propia documentación de pybind11 recomienda limpiar `CMakeCache.txt` cuando CMake encuentra una instalación Python incorrecta.[^3_4]

## Backend de empaquetado recomendado

Para producción, usar `scikit-build-core` como backend CMake moderno:

```toml
[build-system]
requires = [
    "scikit-build-core>=0.10",
    "pybind11>=3.0"
]
build-backend = "scikit_build_core.build"

[project]
name = "v911"
version = "0.1.0"
requires-python = ">=3.10"

[tool.scikit-build]
wheel.packages = ["python/v911"]
cmake.build-type = "Release"
```

La documentación actual de pybind11 presenta `scikit-build-core` como una ruta directa para proyectos CMake y señala que ya no son necesarios `setup.py`, `setup.cfg` ni `MANIFEST.in` en ese modelo.[^3_2]

Construcción:

```powershell
python -m pip install -v .
```

Wheel:

```powershell
python -m pip install build
python -m build
```

Instalación editable:

```powershell
python -m pip install -v -e .
```

Esto evita que `setup_v911.py` tenga que reconstruir manualmente flags de Python y de linker.

## Cuándo usar setuptools

Setuptools sigue siendo válido si el proyecto es pequeño o si ya existe una infraestructura basada en `setup.py`. Debe utilizarse `Pybind11Extension`, no `Extension` con flags manuales:

```python
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

ext_modules = [
    Pybind11Extension(
        "v911._v911_native",
        [
            "cpp/bindings/module.cpp",
            "cpp/core/solver.cpp",
            "cpp/core/cayley.cpp",
            "cpp/core/krylov.cpp",
        ],
        cxx_std=17,
    ),
]

setup(
    name="v911",
    version="0.1.0",
    packages=["v911"],
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
```

Y `pyproject.toml`:

```toml
[build-system]
requires = [
    "setuptools>=68",
    "pybind11>=3.0"
]
build-backend = "setuptools.build_meta"
```

pybind11 proporciona explícitamente `Pybind11Extension` y `build_ext` para este flujo.[^3_2]

### Elección

| Opción | Uso recomendado | Evaluación |
| :-- | :-- | :-- |
| CMake + scikit-build-core | Proyecto científico con varios archivos C++ | Mejor opción |
| CMake directo | Desarrollo y CI nativo | Excelente |
| setuptools + Pybind11Extension | Módulo pequeño o compatibilidad heredada | Adecuado |
| `g++` manual | Prototipos Unix | No usar en Windows |
| ctypes | Fallback ABI | Mantener como respaldo, no como ruta principal |

## ABI, versiones y distribución

Una extensión CPython normal no garantiza compatibilidad entre versiones menores de Python. Para una extensión científica de pybind11, lo habitual es construir wheels para cada versión de Python soportada.

El ABI estable `abi3` puede reducir la matriz de builds, pero solo es aplicable si toda la superficie usada por el módulo es compatible con Limited API. La documentación de empaquetado explica que los wheels `abi3` pueden funcionar entre varias versiones Python 3.x, pero no debe activarse sin verificar las restricciones reales del código.[^3_3]

Recomendación:

- fase de desarrollo: ABI normal, por ejemplo `cp312-win_amd64`;
- distribución inicial: wheels separados para CPython soportado;
- fase posterior: evaluar `abi3`;
- no asumir que `abi3` resolverá diferencias internas de NumPy, C++ runtime o dependencias externas.


## Seguridad del binding

El binding debe ser seguro tanto para memoria como para excepciones.

### Excepciones

Nunca dejar excepciones C++ atravesar el límite Python:

```cpp
PYBIND11_MODULE(_v911_native, m) {
    m.def("solve_linear_system",
          [](py::array_t<double, py::array::c_style | py::array::forcecast> b) {
              try {
                  return solve_impl(b);
              } catch (const std::invalid_argument& e) {
                  throw py::value_error(e.what());
              } catch (const std::runtime_error& e) {
                  throw py::runtime_error(e.what());
              }
          });
}
```


### Validación de arrays

Validar:

- dtype;
- dimensionalidad;
- contigüidad;
- alineación;
- tamaño;
- ausencia de alias peligroso;
- valores finitos.

```cpp
auto buf = x.request();

if (buf.ndim != 2)
    throw py::value_error("x must be a 2D array");

if (buf.shape[^3_0] == 0 || buf.shape[^3_1] == 0)
    throw py::value_error("x cannot be empty");
```


### GIL

Liberar el GIL solo cuando el núcleo no toque objetos Python:

```cpp
m.def("solve", [](py::array_t<double> x) {
    py::gil_scoped_release release;
    return solve_native(x);
});
```

No liberar el GIL si:

- se invocan callbacks Python;
- se accede a `py::object`;
- se lanzan operaciones que dependen del intérprete;
- se mantienen referencias Python en hilos nativos.

El código de alto coste numérico debe aceptar buffers ya validados y operar sobre memoria C++.

### Ownership

Preferir:

```cpp
py::array_t<double> output({n, k});
```

y copiar el resultado al array Python, salvo que exista una política explícita de ownership. No devolver punteros a memoria temporal o a buffers gestionados por `thread_local`.

## SIMD y optimización

No colocar:

```cmake
add_compile_options(-msse4.2)
```

a nivel global. Hacerlo por compilador:

```cmake
if(MSVC)
    target_compile_options(v911_core PRIVATE /O2)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(v911_core PRIVATE -O3 -march=native)
endif()
```

Para wheels distribuibles, evitar `-march=native`, porque generaría binarios incompatibles con otras máquinas. Mejor:

```cmake
if(V911_NATIVE_OPT)
    if(MSVC)
        target_compile_options(v911_core PRIVATE /O2)
    else()
        target_compile_options(v911_core PRIVATE -O3 -march=native)
    endif()
endif()
```

Para la ruta portable:

- baseline SSE2/x86-64;
- kernels AVX2 opcionales;
- detección en runtime;
- dispatch por función;
- benchmarks por microarquitectura.

La generación de código optimizado debe residir en `v911_core`, no en `module.cpp`.

## CMake Presets

Para hacer reproducible el build, añadir `CMakePresets.json`:

```json
{
  "version": 6,
  "configurePresets": [
    {
      "name": "windows-release",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/build/windows-release",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_CXX_STANDARD": "17",
        "PYBIND11_FINDPYTHON": "ON"
      }
    }
  ],
  "buildPresets": [
    {
      "name": "windows-release",
      "configurePreset": "windows-release",
      "jobs": 0
    }
  ]
}
```

El ejecutable Python debe fijarse desde el entorno activo:

```powershell
cmake --preset windows-release `
  -DPython_EXECUTABLE="$PY" `
  -Dpybind11_DIR="$PYPATH"

cmake --build --preset windows-release
```

Esto evita que PowerShell, CMake y Visual Studio usen interpretaciones diferentes de los flags.

## CI científico y reproducible

El pipeline debe probar al menos:

- Windows x64 + MSVC;
- Linux x64 + GCC;
- Python 3.10–3.13 según soporte;
- Debug y Release;
- fallback `ctypes`;
- backend pybind11;
- tests numéricos cruzados.

Ejemplo conceptual con cibuildwheel:

```toml
[tool.cibuildwheel]
build = ["cp310-*", "cp311-*", "cp312-*", "cp313-*"]
skip = ["*-win32", "*-manylinux_i686"]
test-command = "python -m pytest {project}/tests"
```

El empaquetado binario requiere wheels por plataforma, arquitectura y versión ABI; usar CI evita que cada usuario tenga que disponer de un compilador local. La guía de empaquetado recomienda distribuir wheels y conservar también el código fuente.[^3_3]

## Protocolo de diagnóstico

Antes de corregir código, registrar:

```powershell
python -c "import sys, sysconfig; print(sys.executable); print(sys.version); print(sysconfig.get_platform())"
cmake --version
where.exe cmake
where.exe cl
where.exe g++
python -m pybind11 --cmakedir
python -m pip show pybind11
```

Después verificar:

```powershell
cmake -S . -B build -G Ninja --trace-expand
```

Buscar específicamente:

- `Python_EXECUTABLE`;
- `Python_INCLUDE_DIRS`;
- `Python_Development.Module_FOUND`;
- `pybind11_DIR`;
- arquitectura del compilador;
- nombre final del archivo `.pyd`.

El criterio de éxito no es solo que compile:

```powershell
python -c "import v911._v911_native as m; print(m)"
```

También deben pasar:

```powershell
python -m pytest -q
python -m pip wheel . --no-deps -v
```


## Plan de migración V911

### Fase 1: estabilizar el núcleo

- separar `v911_core` del binding;
- eliminar flags manuales de Python;
- borrar el build cache;
- validar MSVC + Python x64;
- compilar con CMake directo.


### Fase 2: binding seguro

- migrar a `py::array_t`;
- validar shape/dtype/contigüidad;
- traducir excepciones;
- liberar GIL en el solver;
- comprobar ausencia de fugas con sanitizers disponibles.


### Fase 3: empaquetado

- añadir `pyproject.toml`;
- adoptar scikit-build-core;
- generar wheel local;
- añadir fallback ctypes;
- probar instalación desde wheel limpio.


### Fase 4: rendimiento

- benchmark pybind11 frente a ctypes;
- medir conversión de arrays;
- reducir copias;
- usar bloques contiguos;
- añadir kernels SIMD por plataforma;
- perfilar núcleo y binding por separado.


### Fase 5: CI y distribución

- cibuildwheel;
- wheels Windows/Linux;
- tests de importación;
- tests numéricos de equivalencia;
- publicación de artefactos;
- reproducibilidad mediante presets y versiones fijadas.


## Diagnóstico final

El error V911 no debe tratarse como un problema aislado de una librería faltante. Es un problema de **selección de toolchain, descubrimiento de Python y enlace específico de plataforma**.

La configuración recomendada es:

$$
\boxed{
\text{MSVC}
+
\text{CMake moderno}
+
\text{FindPython}
+
\text{pybind11::module}
+
\text{scikit-build-core}
}
$$

`ctypes` debe conservarse como fallback y herramienta de comparación ABI, pero no como solución de producción para el solver. La ruta correcta evita completamente el enlace manual contra `libpython`, elimina la dependencia accidental de `-msse4.2`, hace reproducible el build en Windows y permite avanzar después hacia wheels, CI, precisión mixta y optimizaciones nativas sin volver a romper la infraestructura.

<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_16][^3_17][^3_5][^3_6][^3_7][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://pybind11.readthedocs.io/en/stable/cmake/index.html

[^3_2]: https://pybind11.readthedocs.io/en/stable/compiling.html

[^3_3]: https://packaging.python.org/en/latest/guides/packaging-binary-extensions/

[^3_4]: https://pybind11.readthedocs.io/en/stable/faq.html

[^3_5]: https://www.osti.gov/servlets/purl/1438714

[^3_6]: https://pybind11.readthedocs.io/en/stable/upgrade.html

[^3_7]: https://pybind11.readthedocs.io/en/stable/basics.html?highlight=install

[^3_8]: https://pybind11.readthedocs.io/\_/downloads/en/latest/pdf/

[^3_9]: https://pybind11.readthedocs.io/\_/downloads/en/stable/pdf/

[^3_10]: https://pybind11.readthedocs.io/en/stable/installing.html

[^3_11]: https://pybind11.readthedocs.io/en/stable/advanced/embedding.html

[^3_12]: https://pybind11.readthedocs.io/en/stable/changelog.html

[^3_13]: https://pybind11.readthedocs.io/en/latest/changelog.html

[^3_14]: https://github.com/pybind/pybind11/blob/master/docs/compiling.rst

[^3_15]: https://github.com/pybind/pybind11

[^3_16]: https://gem5.googlesource.com/public/gem5/+/eed80d083e9e39473ce70c1d5a379c1a32941ad5/ext/pybind11/docs/compiling.rst

[^3_17]: https://pybind11.com/


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La solución SOTA para la cadena de compilación V911 es pasar de un `setup_v911.py` que intenta controlar manualmente el compilador a un **backend PEP 517 nativo**, preferentemente `scikit-build-core + CMake + pybind11`, con wheels reproducibles y una matriz CI por plataforma. Para un proyecto C++ científico, `meson-python` es una alternativa válida, pero CMake ofrece mejor continuidad si ya existe código nativo, dependencias BLAS/SIMD o futuras extensiones CUDA.[^4_1]

## 1. Decisión arquitectónica

La cadena recomendada es:

$$
\texttt{pyproject.toml}
\rightarrow
\texttt{scikit-build-core}
\rightarrow
\texttt{CMake}
\rightarrow
\texttt{MSVC/GCC/Clang}
\rightarrow
\texttt{wheel}
$$

Esto evita que Python, PowerShell y el linker interpreten manualmente flags como `-lpython`, `.2` o `-msse4.2`.

`scikit-build-core` está diseñado precisamente para construir extensiones C/C++ mediante CMake y soporta wheels, compilación editable, cross-compilation y configuración moderna.[^4_2][^4_3]

Para V911:

- **Producción:** `scikit-build-core`.
- **CMake directo:** depuración del toolchain.
- **setuptools + `Pybind11Extension`:** compatibilidad heredada.
- **ctypes:** fallback de runtime.
- **nanobind:** posible migración futura si el binding se convierte en cuello de botella.


## 2. Estructura de proyecto

Migrar a una estructura `src`:

```text
v911/
├── pyproject.toml
├── CMakeLists.txt
├── CMakePresets.json
├── LICENSE
├── README.md
├── src/
│   └── v911/
│       ├── __init__.py
│       ├── _ctypes_backend.py
│       └── _native.cpp
├── cpp/
│   ├── CMakeLists.txt
│   ├── core/
│   │   ├── solver.cpp
│   │   ├── solver.hpp
│   │   ├── cayley.cpp
│   │   └── krylov.cpp
│   └── bindings/
│       └── module.cpp
└── tests/
```

La extensión debe ser privada:

```python
# src/v911/__init__.py
try:
    from ._v911_native import solve_linear_system
    backend = "pybind11"
except ImportError:
    from ._ctypes_backend import solve_linear_system
    backend = "ctypes"
```

El usuario importa `v911`, no `_v911_native`. Esto permite cambiar pybind11, nanobind o ctypes sin modificar la API pública.

## 3. `pyproject.toml` robusto

Una base moderna es:

```toml
[build-system]
requires = [
    "scikit-build-core>=0.12",
    "pybind11>=3.0"
]
build-backend = "scikit_build_core.build"

[project]
name = "v911"
version = "0.2.0"
description = "Matrix-free Cayley and Krylov solvers"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "BSD-3-Clause" }

[tool.scikit-build]
minimum-version = "build-system.requires"
wheel.packages = ["src/v911"]
build-dir = "build/{wheel_tag}"
sdist.reproducible = true
```

No añadir innecesariamente `cmake`, `ninja`, `setuptools` o `wheel` en `build-system.requires`: scikit-build-core puede resolver o utilizar las herramientas disponibles según el entorno.[^4_2]

Para una extensión científica distribuible, fijar rangos compatibles en vez de depender siempre de la última versión:

```toml
requires = [
    "scikit-build-core>=0.12,<2",
    "pybind11>=3.0,<4"
]
```


## 4. CMake moderno y portátil

```cmake
cmake_minimum_required(VERSION 3.15...4.4)

project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

add_library(v911_core STATIC
    cpp/core/solver.cpp
    cpp/core/cayley.cpp
    cpp/core/krylov.cpp
)

target_include_directories(v911_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/cpp
)

if(MSVC)
    target_compile_options(v911_core PRIVATE /W4 /EHsc)
else()
    target_compile_options(v911_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

pybind11_add_module(_v911_native
    src/v911/_native.cpp
)

target_link_libraries(_v911_native PRIVATE v911_core)

install(
    TARGETS _v911_native
    LIBRARY DESTINATION v911
    RUNTIME DESTINATION v911
)
```

No utilizar:

```cmake
target_link_libraries(_v911_native python3.12)
```

ni:

```cmake
set(CMAKE_EXE_LINKER_FLAGS "-lpython3.12")
```

Una extensión Python normalmente no debe enlazarse manualmente contra una biblioteca estática de Python. Debe enlazar mediante los targets de Python/pybind11 que correspondan a una extensión. La documentación actual muestra tanto `pybind11_add_module` como `python_add_library(... MODULE ...)` como rutas válidas.[^4_2]

## 5. Solución específica al error `.2`

Debe eliminarse el origen del flag roto, no parchearse con una librería ficticia.

Diagnóstico:

```powershell
python -c "import sys; print(sys.executable); print(sys.version)"
python -m pybind11 --cmakedir
cmake --version
where.exe cl
where.exe g++
where.exe ninja
```

Luego configurar con un generador coherente:

```powershell
$PY = python -c "import sys; print(sys.executable)"
$PYBIND11 = python -m pybind11 --cmakedir

Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue

cmake -S . -B build `
  -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DPython_EXECUTABLE="$PY" `
  -Dpybind11_DIR="$PYBIND11"

cmake --build build --parallel
```

Si se usa Visual Studio:

```powershell
cmake -S . -B build `
  -G "Visual Studio 17 2022" `
  -A x64 `
  -DPython_EXECUTABLE="$PY" `
  -Dpybind11_DIR="$PYBIND11"

cmake --build build --config Release
```

No mezclar:

- Python x64 con compilador x86;
- Python MSVC con bibliotecas MinGW;
- Ninja configurado con un compilador distinto al esperado;
- cache CMake generado con otro Python;
- flags Linux obtenidos mediante `python-config`.

El error `.2` es consistente con una expansión incorrecta de flags y no con la ausencia real de una biblioteca llamada `.2`.

## 6. SIMD y ABI

Eliminar de la configuración global:

```cmake
-msse4.2
```

El flag debe estar condicionado:

```cmake
option(V911_NATIVE_OPT "Enable host-specific optimizations" OFF)

if(V911_NATIVE_OPT)
    if(MSVC)
        target_compile_options(v911_core PRIVATE /O2)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(v911_core PRIVATE -O3 -march=native)
    endif()
endif()
```

Para wheels públicas, mantener `V911_NATIVE_OPT=OFF`. `-march=native` crea binarios optimizados para la máquina de compilación, no necesariamente compatibles con el usuario.

Para mejorar científicamente el rendimiento:

1. compilar un baseline portable;
2. compilar kernels SIMD opcionales;
3. detectar capacidades en runtime;
4. hacer dispatch por función;
5. comparar SSE/AVX2/AVX-512 mediante benchmark.

La ruta de enlace del binding debe ser independiente del dispatch SIMD.

## 7. pybind11 frente a nanobind

Si el tiempo de compilación o el tamaño de `_v911_native.pyd` se vuelve significativo, nanobind merece un benchmark. Sus benchmarks publicados reportan compilación hasta aproximadamente $4\times$ más rápida, binarios varias veces más pequeños y menor overhead de llamadas que pybind11, aunque son resultados dependientes del caso y de la versión.[^4_4]

No migraría inmediatamente. Para V911:


| Criterio | pybind11 | nanobind |
| :-- | :-- | :-- |
| Madurez/ecosistema | Muy alta | Alta y creciente |
| Migración desde código existente | Fácil | Requiere cambios |
| Compilación | Puede ser más pesada | Generalmente más ligera |
| Binario | Mayor | Menor |
| API C++ | Amplia | Más restringida |
| Riesgo actual | Bajo | Moderado |

Recomendación:

- Fase 2: estabilizar pybind11.
- Fase 3: medir.
- Fase 4: prototipo nanobind en una rama.
- Migrar solo si el coste del binding aparece en perfiles reales.

El solver matrix-free probablemente dominará el tiempo total, por lo que optimizar pybind11 prematuramente puede producir una mejora irrelevante.

## 8. Diseño de la frontera Python-C++

El binding debe aceptar arrays contiguos y transferir el menor número posible de buffers:

```cpp
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

namespace py = pybind11;

py::array_t<double> solve_native(
    py::array_t<double, py::array::c_style | py::array::forcecast> b
) {
    auto info = b.request();

    if (info.ndim != 1) {
        throw py::value_error("b must be one-dimensional");
    }

    const auto n = static_cast<std::size_t>(info.shape[^4_0]);
    py::array_t<double> result(n);

    auto out = result.mutable_unchecked<1>();
    const auto in = b.unchecked<1>();

    {
        py::gil_scoped_release release;
        solve_core(in, out, n);
    }

    return result;
}
```

Reglas:

- aceptar `c_style | forcecast` si el coste de copia es tolerable;
- ofrecer una ruta `strict` para evitar copias;
- verificar dimensiones antes de liberar el GIL;
- no retener punteros a memoria Python después de la llamada;
- no lanzar excepciones C++ sin traducir;
- no acceder a objetos Python desde hilos nativos sin recuperar el GIL.

Para matrices grandes, ofrecer una API de salida reutilizable:

```python
solve(b, out=buffer)
```

Esto evita asignaciones repetidas durante FGMRES y reduce la presión del allocator.

## 9. ABI estable: cuándo usar `abi3`

`abi3` puede reducir el número de wheels, pero solo debe usarse si el binding se restringe a la Stable ABI. Para V911 hay que evaluar cuidadosamente:

- APIs de pybind11 usadas;
- acceso a NumPy;
- subinterpreter/free-threading;
- dependencias binarias;
- soporte de Python mínimo.

El beneficio principal es reducir la matriz de builds, no mejorar el rendimiento. Para la Fase 2, recomiendo ABI específica por versión:

```text
cp310-win_amd64
cp311-win_amd64
cp312-win_amd64
cp313-win_amd64
```

Después, estudiar `abi3` con un módulo mínimo. El sistema de build actual también contempla configuraciones ABI3 y free-threaded, pero estas requieren restricciones adicionales y no deben activarse como solución automática al fallo de linkeo.[^4_2]

## 10. Wheels reproducibles

Una instalación local exitosa no demuestra que el artefacto sea distribuible. Deben generarse wheels por plataforma y versión de Python. La guía de Scientific Python recomienda producir wheels redistribuibles mediante CI/cibuildwheel para evitar que cada usuario compile el código nativo.[^4_1]

Pipeline mínimo:

```yaml
name: wheels

on:
  push:
  pull_request:

jobs:
  build-wheels:
    strategy:
      matrix:
        os: [windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: pypa/cibuildwheel@v2
        env:
          CIBW_BUILD: "cp310-* cp311-* cp312-* cp313-*"
          CIBW_TEST_COMMAND: "python -m pytest {project}/tests"

      - uses: actions/upload-artifact@v4
        with:
          name: wheels-${{ matrix.os }}
          path: wheelhouse/*
```

Para Windows, verificar:

```powershell
python -m pip install .\wheelhouse\v911-*.whl
python -c "import v911; print(v911.backend)"
python -m pytest -q
```


## 11. Reproducibilidad científica

Fijar y registrar:

- compilador;
- versión de CMake;
- versión de pybind11;
- versión del backend;
- Python;
- arquitectura;
- flags;
- BLAS;
- SIMD;
- commit Git;
- opciones del solver.

Exponer metadatos:

```python
import v911

print(v911.__version__)
print(v911.backend)
print(v911.build_info())
```

`build_info()` debería informar:

```text
compiler=MSVC 19.x
cxx_standard=17
build_type=Release
simd=baseline
openmp=off
git_commit=...
```

No debe incluir rutas privadas ni información sensible.

Para binarios reproducibles:

- fijar versiones en CI;
- usar `sdist.reproducible = true`;
- excluir timestamps volátiles;
- construir en contenedores o runners definidos;
- comparar hashes cuando sea posible.

`scikit-build-core` incluye una opción de distribución reproducible para sdists.[^4_3]

## 12. Testing en cuatro niveles

### Importación

```python
def test_import():
    import v911
    assert v911.backend in {"pybind11", "ctypes"}
```


### Equivalencia de backends

```python
def test_native_matches_ctypes():
    y_native = native.solve(x)
    y_ctypes = ctypes_backend.solve(x)
    assert np.allclose(y_native, y_ctypes, rtol=1e-11, atol=1e-12)
```


### Seguridad de memoria

Usar:

- AddressSanitizer;
- UndefinedBehaviorSanitizer;
- `/fsanitize=address` con MSVC cuando sea compatible;
- Valgrind en Linux;
- tests de arrays no contiguos;
- arrays de dtype incorrecto;
- entradas vacías;
- NaN/Inf;
- excepciones durante el solve.


### Propiedades numéricas

Para la retracción:

$$
\|Y^\top Y-I\|_F
$$

debe estar dentro de la tolerancia. Para el solver:

$$
\frac{\|b-Ax\|_2}{\|b\|_2}
$$

debe compararse entre backend nativo y `ctypes`.

## 13. Observación sobre Python 3.13 free-threaded

El soporte free-threaded no debe suponerse automáticamente. Requiere revisar:

- uso del GIL;
- estado global mutable;
- `thread_local`;
- caches estáticas;
- bibliotecas BLAS;
- ABI del binding;
- tags de wheel.

La guía reciente de compilación distingue configuraciones ABI3 y free-threaded, y señala requisitos particulares para `abi3t`.[^4_2]

Para V911:

1. estabilizar CPython con GIL;
2. hacer el solver thread-safe;
3. eliminar estado global no protegido;
4. probar `Py_GIL_DISABLED`;
5. solo entonces generar wheels free-threaded.

La presencia de `thread_local` no garantiza seguridad lógica: evita compartir una variable concreta, pero no resuelve aliasing, caches globales, estados del BLAS o acceso concurrente al mismo buffer.

## 14. Meson como alternativa

Meson-python también es una solución SOTA para C/C++ y puede ser preferible si el equipo quiere:

- configuración más declarativa;
- builds rápidos;
- menos complejidad histórica de CMake;
- integración simple con `pybind11`.

La guía de Scientific Python considera `scikit-build-core` y `meson-python` opciones modernas para C/C++/Fortran.[^4_1]

No cambiaría a Meson en medio de V911 salvo que:

- CMake se convierta en un problema de mantenimiento;
- el proyecto no dependa de tooling CMake existente;
- se valore fuertemente la velocidad y simplicidad del build;
- se pueda migrar todo el CI de una sola vez.


## 15. Plan final de Fase 2

### Fase 2A: eliminar el fallo actual

- eliminar invocaciones manuales a `g++`;
- borrar `build/` y `CMakeCache.txt`;
- usar MSVC x64 con Python x64;
- configurar `FindPython`/pybind11;
- eliminar `-msse4.2`;
- comprobar importación del `.pyd`.


### Fase 2B: empaquetado moderno

- añadir `pyproject.toml`;
- migrar a `scikit-build-core`;
- instalar mediante `pip install .`;
- construir wheel;
- probar instalación desde entorno limpio.


### Fase 2C: robustez científica

- equivalencia nativo/ctypes;
- validación residual y ortogonalidad;
- ASan/UBSan;
- benchmarks sin copias;
- registro de build metadata.


### Fase 2D: distribución

- cibuildwheel;
- Windows y Linux;
- Python 3.10–3.13;
- artefactos reproducibles;
- documentación de toolchain;
- fallback ctypes.


### Fase 2E: optimización avanzada

- salida reutilizable;
- GIL release;
- bloques contiguos;
- SIMD dispatch;
- benchmark nanobind;
- evaluación ABI3.


## Conclusión

La solución SOTA para V911 es:

$$
\boxed{
\text{scikit-build-core}
+
\text{CMake}
+
\text{pybind11}
+
\text{MSVC coherente}
+
\text{cibuildwheel}
+
\text{tests ABI/numerical}
}
$$

El error `.2` y el flag `-msse4.2` deben desaparecer del flujo de Windows, no ser parcheados. El binding nativo debe ser una extensión privada y segura, mientras `ctypes` queda como fallback verificable. Una vez estabilizado el build, las mejoras con mayor impacto probable son liberar el GIL, eliminar copias, reutilizar buffers del FGMRES y medir si nanobind aporta una ganancia real frente al coste de migración.

<span style="display:none">[^4_10][^4_11][^4_12][^4_13][^4_14][^4_15][^4_16][^4_17][^4_18][^4_19][^4_20][^4_21][^4_22][^4_23][^4_24][^4_5][^4_6][^4_7][^4_8][^4_9]</span>

<div align="center">⁂</div>

[^4_1]: https://learn.scientific-python.org/development/guides/packaging-compiled/

[^4_2]: https://scikit-build-core.readthedocs.io/en/latest/guide/getting_started.html

[^4_3]: https://github.com/scikit-build/scikit-build-core

[^4_4]: https://nanobind.readthedocs.io/en/latest/benchmark.html

[^4_5]: https://proceedings.scipy.org/articles/FMKR8387.pdf

[^4_6]: https://peps.python.org/pep-0517/

[^4_7]: https://pydevtools.com/handbook/how-to/how-to-package-python-projects-with-native-extensions/

[^4_8]: https://scikit-build-core.readthedocs.io/en/latest/getting_started.html

[^4_9]: https://scikit-build-core.readthedocs.io/en/latest/guide/faqs.html

[^4_10]: https://scikit-build-core.readthedocs.io/en/stable/configuration/

[^4_11]: https://scikit-build-core.readthedocs.io/en/latest/configuration/index.html

[^4_12]: https://itripleyyy.github.io/pip-docs-jp/en/latest/reference/build-system/index.html

[^4_13]: https://arxiv.org/html/2603.04668v1

[^4_14]: https://pybind11.readthedocs.io/en/latest/compiling.html

[^4_15]: https://pypi.org/project/pybind11/

[^4_16]: https://scikit-build-core.readthedocs.io/en/stable/guide/faqs.html

[^4_17]: https://github.com/scientific-python/cookie

[^4_18]: https://pybind11.readthedocs.io/en/stable/compiling.html

[^4_19]: https://pybind11.readthedocs.io/en/stable/changelog.html

[^4_20]: https://pybind11.readthedocs.io/en/latest/changelog.html

[^4_21]: https://pybind11.readthedocs.io/\_/downloads/en/latest/pdf/

[^4_22]: https://pybind11.readthedocs.io/en/stable/upgrade.html

[^4_23]: https://pybind11.readthedocs.io/en/stable/cmake/index.html

[^4_24]: https://pybind11.readthedocs.io/en/stable/faq.html


---

# 3. Falta de Zero-Copy Inter-Device (DLPack) evalua mejoras y soluciones cientificas SOTA

Brecha (V911): Aunque pybind11 anclará la recolección de basura, las matrices numpy y los tensores GPU se seguirán comunicando a través de buffers expuestos de Python.
Solución Asintótica Pendiente: Implementar DLPack en el interior de C++ y Rust para permitir que PyTorch (ROCm/CUDA) inyecte punteros directos hacia la memoria HBM3, eliminando todo overhead de marshaling.
Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La solución correcta para V911 no es “pasar punteros GPU a C++” sin más. Un puntero HBM3 no contiene por sí mismo el **dispositivo, dtype, strides, ownership ni stream** necesarios para operar de forma segura. La arquitectura SOTA debe combinar:

$$
\boxed{
\text{DLPack}
+
\text{C Exchange API}
+
\text{stream-aware execution}
+
\text{deleter/lifetime correcto}
+
\text{kernels CUDA/HIP}
}
$$

DLPack permite intercambio zero-copy de arrays densos y estridados; PyTorch comparte la memoria con el consumidor cuando es posible, pero la responsabilidad de sincronización y vida útil sigue siendo del productor/consumidor.[^5_1][^5_2]

## 1. Corrección conceptual

### Lo que DLPack sí elimina

DLPack puede eliminar:

- copia Python → C++;
- copia C++ → Python;
- serialización de tensores;
- reconstrucción manual de shapes;
- marshaling de buffers intermedios;
- copia host-device cuando ambos frameworks comparten el dispositivo.


### Lo que DLPack no elimina

DLPack no elimina:

- lanzamiento de kernels;
- sincronización entre streams;
- validación de dtype y strides;
- retención del productor;
- coste de convertir metadata;
- copias inevitables entre dispositivos;
- sincronizaciones si el consumidor usa un stream incompatible.

Por eso “zero-copy” no significa “zero-overhead”. El objetivo real es:

$$
T_{\mathrm{interop}}
\approx
T_{\mathrm{metadata}}
+
T_{\mathrm{event/stream}}
+
T_{\mathrm{kernel}},
$$

sin un término

$$
T_{\mathrm{copy}}(n).
$$

## 2. Dos niveles de integración

### Nivel N1: protocolo Python

Implementar:

```python
tensor.__dlpack__(stream=...)
tensor.__dlpack_device__()
```

y consumir mediante:

```python
torch.from_dlpack(obj)
```

o desde C++ invocando los métodos Python.

Es la opción más sencilla y portable, pero todavía cruza Python y crea un `PyCapsule`. Es apropiada para:

- ingestión ocasional;
- prototipos;
- resultados que deben mantenerse vivos;
- API pública sencilla.


### Nivel N0: C Exchange API

Para kernels que se ejecutan inmediatamente sobre un tensor de PyTorch, la vía SOTA es la **DLPack C Exchange API**. Esta API permite obtener un `DLTensor` sin construir una cápsula gestionada, consultar el stream actual y lanzar el kernel en ese mismo stream. La especificación describe funciones como `dltensor_from_py_object_no_sync` y `current_work_stream`, diseñadas para el camino rápido sin sincronización.[^5_3]

La estrategia recomendada para V911 es:

- usar N1 como fallback;
- usar N0 cuando el tensor solo se necesita durante la llamada;
- reservar `DLManagedTensor` para resultados que sobrevivan al retorno.


## 3. Importación segura en C++

### Cabecera

Incluir una versión fijada de `dlpack.h` en el proyecto o usar una dependencia versionada:

```cpp
#include <dlpack/dlpack.h>
```

No copiar una estructura local incompleta. DLPack contiene dispositivos como CUDA, ROCm, memoria host fijada, managed memory y otros; además, las versiones modernas contienen flags de solo lectura, copias y tipos de precisión reducida.[^5_3]

### Descriptor interno

Crear un descriptor propio, independiente de Python:

```cpp
struct DeviceTensorView {
    void* data;
    int device_type;
    int device_id;
    int ndim;
    std::vector<int64_t> shape;
    std::vector<int64_t> strides;
    DLDataType dtype;
    uint64_t byte_offset;
    bool read_only;
};
```

El descriptor no debe asumir:

- contiguous;
- row-major;
- `float32`;
- device 0;
- `byte_offset == 0`;
- strides no nulos.


### Validación

Antes de lanzar el kernel:

```cpp
void validate(const DLTensor& t) {
    if (t.data == nullptr && t.ndim != 0) {
        throw std::invalid_argument("null tensor data");
    }

    if (t.device.device_type != kDLCUDA &&
        t.device.device_type != kDLROCM) {
        throw std::invalid_argument("unsupported device");
    }

    if (t.dtype.bits != 16 && t.dtype.bits != 32 &&
        t.dtype.bits != 64) {
        throw std::invalid_argument("unsupported dtype width");
    }

    if (t.ndim < 0 || t.ndim > 8) {
        throw std::invalid_argument("unsupported rank");
    }
}
```

La validación debe comprobar overflow al calcular el span de memoria:

$$
\mathrm{span}
=
\mathrm{byte\_offset}
+
\sum_i (d_i-1)|s_i|\frac{\mathrm{bits}}{8}.
$$

No convertir `shape` a `size_t` sin verificar valores negativos y multiplicaciones desbordadas.

## 4. Ownership y deleter

El error más peligroso de DLPack es devolver una vista que sobrevive al tensor productor.

Un `DLManagedTensor` contiene:

- `dl_tensor`;
- `manager_ctx`;
- `deleter`.

El consumidor debe invocar el `deleter` cuando deja de usar la memoria. El productor sigue siendo dueño de la asignación; DLPack describe y coordina el préstamo, no transfiere automáticamente la memoria.[^5_3]

El patrón correcto es:

```cpp
struct Holder {
    PyObject* owner;
};

void deleter(DLManagedTensor* managed) {
    if (!managed) return;

    auto* holder = static_cast<Holder*>(managed->manager_ctx);

    if (Py_IsInitialized()) {
        PyGILState_STATE gil = PyGILState_Ensure();
        Py_XDECREF(holder->owner);
        PyGILState_Release(gil);
    }

    delete holder;
    delete managed;
}
```

Debe evitarse:

- liberar con `free()` memoria asignada por PyTorch;
- guardar solo `data_ptr`;
- decrementar referencias Python sin GIL;
- dejar que un tensor exportado sobreviva a la finalización del intérprete;
- consumir una cápsula más de una vez.

La especificación define que una cápsula `dltensor` se consume una sola vez y se renombra a `used_dltensor`; reutilizarla tiene comportamiento indefinido.[^5_2][^5_1]

## 5. Stream semantics: el punto crítico

CUDA y ROCm son asíncronos. El productor puede haber escrito el tensor en un stream $S_p$, mientras V911 lanza su kernel en $S_c$.

La secuencia correcta es:

$$
S_p
\rightarrow
\text{evento/fence}
\rightarrow
S_c
\rightarrow
\text{kernel V911}.
$$

O, mejor, ejecutar el kernel V911 directamente en el stream actual del productor/consumidor cuando el contrato lo permita.

La especificación DLPack establece que el consumidor debe proporcionar el stream que usará y que el productor debe sincronizar o esperar cuando sea necesario.[^5_1]

### CUDA

El kernel debe usar:

```cpp
cudaStream_t stream = ...;
kernel<<<grid, block, 0, stream>>>(...);
```

No usar siempre stream 0. Eso puede introducir:

- sincronizaciones ocultas;
- pérdida de concurrencia;
- deadlocks con streams no bloqueantes;
- incompatibilidad con CUDA Graph capture.


### ROCm/HIP

El equivalente es:

```cpp
hipStream_t stream = ...;
hipLaunchKernelGGL(kernel, grid, block, 0, stream, ...);
```

Los streams HIP son colas FIFO asíncronas; las operaciones posteriores en el mismo stream observan los efectos previos, pero streams distintos no se sincronizan automáticamente.[^5_4]

### Buen contrato

Definir dos modos:

```text
sync_mode = "external"
    El consumidor entrega un stream válido.
    V911 no sincroniza globalmente.

sync_mode = "event"
    V911 registra/espera eventos entre streams.
    Mayor seguridad, posible coste adicional.
```

No ofrecer un modo silencioso que lance en un stream arbitrario.

## 6. Implementación Python de fallback

Para una primera versión robusta:

```cpp
py::object from_dlpack_object(py::handle obj, uintptr_t stream) {
    py::object capsule = obj.attr("__dlpack__")(
        py::arg("stream") = py::int_(stream)
    );

    if (!PyCapsule_IsValid(capsule.ptr(), "dltensor") &&
        !PyCapsule_IsValid(capsule.ptr(), "dltensor_versioned")) {
        throw py::value_error("invalid DLPack capsule");
    }

    return capsule;
}
```

Sin embargo, no conviene retener la cápsula más allá de la llamada. El consumo debe ser inmediato:

```text
obtener capsule
extraer DLManagedTensor
renombrar como used_dltensor
lanzar kernel
mantener ownership hasta completar uso
llamar deleter
```

Para resultados Python, la ruta más segura suele ser crear un tensor de salida en PyTorch/CuPy mediante sus APIs y escribir directamente sobre él, en vez de fabricar manualmente un objeto Python desde C++.

## 7. C Exchange API como evolución

La arquitectura N0 debe ser:

```text
PyObject* input
    ↓
buscar __dlpack_c_exchange_api__
    ↓
obtener función dltensor_from_py_object_no_sync
    ↓
obtener current_work_stream
    ↓
validar descriptor
    ↓
lanzar kernel en el stream actual
    ↓
no retener vista después del retorno
```

Pseudocódigo:

```cpp
struct DLPackFastPath {
    const DLPackExchangeAPI* api;
    DLDataTensor view;
    void* stream;
};

DLPackFastPath import_no_sync(PyObject* obj) {
    auto* api = lookup_exchange_api(Py_TYPE(obj));

    DLDataTensor view{};
    int rc = api->dltensor_from_py_object_no_sync(obj, &view);
    if (rc != 0) throw_python_error();

    void* stream = nullptr;
    rc = api->current_work_stream(
        view.device.device_type,
        view.device.device_id,
        &stream
    );
    if (rc != 0) throw_python_error();

    return {api, view, stream};
}
```

El intercambio N0 es adecuado para una operación “consume y termina”. Si V911 guarda el tensor para FGMRES asíncrono, debe usar una ruta gestionada con ownership y eventos.

## 8. Integración CUDA/ROCm sin acoplarse a PyTorch

No conviene enlazar el núcleo de V911 directamente contra toda la ABI de PyTorch si el objetivo es soportar CUDA y ROCm.

Separar:

```text
v911_core
    - álgebra
    - descriptor DLPack
    - kernels abstractos

v911_cuda
    - CUDA runtime
    - kernels CUDA

v911_hip
    - HIP runtime
    - kernels HIP

v911_python
    - pybind11
    - protocolo DLPack/C Exchange
```

CMake:

```cmake
option(V911_ENABLE_CUDA "Enable CUDA backend" OFF)
option(V911_ENABLE_HIP "Enable HIP backend" OFF)

if(V911_ENABLE_CUDA)
    enable_language(CUDA)
    add_library(v911_cuda STATIC cpp/cuda/kernels.cu)
endif()

if(V911_ENABLE_HIP)
    find_package(hip REQUIRED)
    add_library(v911_hip STATIC cpp/hip/kernels.hip)
endif()
```

El runtime debe seleccionar:

```text
device_type == kDLCUDA → backend CUDA
device_type == kDLROCM → backend HIP
device_type == kDLCPU → backend CPU
```

No compilar CUDA y HIP simultáneamente en el mismo translation unit. Ambos usan abstracciones parecidas, pero no son ABI intercambiables.

## 9. PyTorch: extensión acoplada o backend independiente

### Extensión PyTorch

Ventajas:

- acceso natural a `at::Tensor`;
- stream actual;
- allocator PyTorch;
- dispatch por device;
- autograd si se implementa;
- integración directa con CUDA/HIP.

Desventajas:

- fuerte dependencia de versión de PyTorch;
- wheels más pesados;
- incompatibilidad potencial con diferentes builds;
- acoplamiento al ABI C++.

PyTorch documenta la construcción de extensiones C++/CUDA y el uso de pybind11 para exponerlas.[^5_5]

### Backend independiente vía DLPack

Ventajas:

- menor acoplamiento;
- interoperabilidad con PyTorch, CuPy, JAX y otros;
- un único descriptor de memoria;
- posibilidad de usar C++ y Rust.

Desventajas:

- hay que implementar ownership;
- stream semantics;
- dispatch de dispositivos;
- validación de tipos;
- no se obtiene autograd automáticamente.

Para V911 recomendaría:

- núcleo independiente DLPack;
- adaptador opcional ATen/PyTorch;
- no depender de `torch::Tensor` en el algoritmo central.


## 10. Rust y FFI

En Rust, no usar `usize` para shapes/strides sin validar conversiones. Definir las estructuras C compatibles:

```rust
#[repr(C)]
pub struct DLDevice {
    pub device_type: i32,
    pub device_id: i32,
}

#[repr(C)]
pub struct DLDataType {
    pub code: u8,
    pub bits: u8,
    pub lanes: u16,
}

#[repr(C)]
pub struct DLTensor {
    pub data: *mut std::ffi::c_void,
    pub device: DLDevice,
    pub ndim: i32,
    pub dtype: DLDataType,
    pub shape: *mut i64,
    pub strides: *mut i64,
    pub byte_offset: u64,
}
```

No convertir directamente a slices sin comprobar:

```rust
assert!(!tensor.shape.is_null());
assert!(tensor.ndim >= 0);
let ndim = usize::try_from(tensor.ndim)?;
```

La regla de seguridad es:

- `DLTensor` no es owner;
- `DLManagedTensor` sí transporta callback de destrucción;
- el callback puede ejecutarse desde un hilo sin GIL;
- nunca llamar APIs Python desde Rust sin adquirir el estado del intérprete;
- nunca liberar memoria de PyTorch con el allocator de Rust.

Para la primera integración Rust, conviene que Rust reciba un descriptor validado desde C++ y no manipule directamente `PyCapsule`. Eso reduce el área unsafe:

```text
Python/pybind11
    ↓
C++ DLPack importer
    ↓
validated C ABI descriptor
    ↓
Rust safe wrapper
```


## 11. Cero copia no significa autograd

Si V911 modifica un tensor de PyTorch directamente:

```text
x storage ← kernel V911
```

PyTorch no conocerá esa operación para autograd. Hay tres opciones:

1. marcar la operación como no diferenciable;
2. implementar `torch::autograd::Function`;
3. registrar un custom op con esquemas `torch.library`/dispatcher y kernels por backend.

Para un solver interno de optimización, normalmente conviene declarar claramente:

```text
requires_grad=True → error o ruta diferenciable explícita
requires_grad=False → fast path zero-copy
```

No mutar silenciosamente un tensor que participa en un grafo autograd.

## 12. Layouts y restricciones reales

DLPack soporta arrays densos y estridados, pero el kernel no necesariamente debe admitir todos los layouts. Definir contratos explícitos:

### Fast path

- dtype `float32`, `float64`, `bfloat16`;
- rank 1–3;
- strides no negativos;
- alineación suficiente;
- contiguous o row-major;
- dispositivo CUDA/ROCm;
- stream válido.


### General path

- strides arbitrarios;
- offsets;
- subviews;
- transposición;
- lectura solamente;
- posible kernel de gather.

Si no se cumple el fast path:

```text
raise BufferError("V911 requires contiguous tensor for zero-copy path")
```

No copiar silenciosamente. El estándar permite indicar explícitamente que no se puede evitar una copia cuando `copy=False`.[^5_6][^5_7]

## 13. Dtypes modernos

La especificación DLPack actual contempla tipos como:

- float8;
- float6;
- float4;
- bfloat16;
- complex;
- tipos booleanos;
- tipos sub-byte con flags de padding.

Pero V911 no debe aceptar un dtype solo porque exista en la enumeración. Debe comprobar:

$$
\text{dtype soportado}
\land
\text{kernel implementado}
\land
\text{alineación válida}
\land
\text{acumulación segura}.
$$

Para el solver Krylov:

- almacenamiento FP16/BF16;
- acumulación FP32;
- productos críticos FP64;
- residual true en FP64.

Para Woodbury:

- matriz reducida en FP64;
- vectores grandes en FP32/BF16 si se aplica iterative refinement;
- actualización de factores con criterio de condición.


## 14. Interoperabilidad HBM3 y host

DLPack puede evitar copias entre frameworks que ya comparten la misma memoria GPU. No puede convertir mágicamente memoria HBM3 en memoria accesible por CPU.

Separar rutas:

```text
GPU → GPU mismo dispositivo:
    DLPack zero-copy

GPU → GPU distinto dispositivo:
    peer copy o error si copy=False

GPU → CPU:
    copia explícita o unified/pinned memory

CPU → GPU:
    copia explícita salvo memoria unificada compatible
```

En un nodo multi-GPU, comprobar:

```text
device_id del productor
device_id del consumidor
peer access
stream ownership
allocator
```

No asumir que ambos frameworks numeran las GPU de igual forma; la especificación advierte que el `device_id` del productor y consumidor puede no tener exactamente el mismo significado.[^5_1]

## 15. Integración con FGMRES matrix-free

El solver V911 puede evitar incluso crear vectores intermedios Python:

```text
PyTorch tensor x
    ↓ DLPack/C Exchange
descriptor x
    ↓
apply_A_gpu(x, y, stream)
    ↓
descriptor y
    ↓
PyTorch view o tensor de salida
```

En FGMRES, almacenar bases en GPU:

$$
V=[v_1,\dots,v_m],\qquad Z=[z_1,\dots,z_m]
$$

y mantener:

- bases en HBM;
- Hessenberg $H_m$ en GPU o host pinned;
- reducciones dot/norm con kernels fusionados;
- solve pequeño $H_m y$ en CPU o GPU según $m$;
- un único stream principal;
- eventos solo cuando se cruza host/device.

La ventaja del zero-copy se pierde si cada Arnoldi step hace:

```text
GPU → CPU
dot en Python
CPU → GPU
```

Por tanto, la integración debe ser end-to-end GPU-resident.

### Operaciones críticas

- `apply_A`: fusionar productos;
- `dot`: reducción por bloques;
- `axpy`: fusionar cuando sea posible;
- normalización: una sola reducción;
- Givens: mantener $H$ pequeño;
- residual: no copiar el vector completo al host.

El cuello de botella futuro probablemente será la sincronización de reducciones, no DLPack. DLPack resuelve el intercambio de storage; no resuelve latencia global de Arnoldi.

## 16. CUDA Graphs y C Exchange

El C Exchange API tiene una ventaja relevante para CUDA Graph capture: puede obtener el stream actual y evitar sincronizaciones innecesarias. La especificación lo identifica como un camino deseable para ejecutar kernels directamente en el contexto del productor.[^5_3]

Para ser compatible con CUDA Graphs:

- no realizar asignaciones Python dentro de la región capturada;
- no consultar dinámicamente atributos Python durante cada kernel;
- no sincronizar el dispositivo;
- no llamar a APIs host-síncronas;
- reutilizar buffers y shapes;
- usar direcciones estables;
- cachear el descriptor si la vida útil está garantizada.

Diseñar dos modos:

```text
eager:
    máxima flexibilidad

graph-capture:
    shapes, dtypes, buffers y streams fijos
    cero asignaciones
    cero llamadas Python por iteración
```


## 17. Benchmark correcto

Medir por separado:

$$
T_{\mathrm{total}}
=
T_{\mathrm{Python}}
+
T_{\mathrm{capsule}}
+
T_{\mathrm{validation}}
+
T_{\mathrm{sync}}
+
T_{\mathrm{kernel}}
+
T_{\mathrm{copy}}.
$$

Comparar:

1. NumPy → ctypes → GPU.
2. PyTorch → pybind11 buffer.
3. PyTorch → DLPack Python capsule.
4. PyTorch → C Exchange API.
5. PyTorch custom op ATen.
6. Rust + DLPack.
7. C++ directo CUDA/HIP.

Métricas:

- throughput GB/s;
- latencia por tensor;
- número de sincronizaciones;
- kernels lanzados;
- HBM peak;
- host allocations;
- CPU utilization;
- overlap comunicación/cómputo;
- error numérico;
- escalabilidad con tamaño;
- comportamiento multi-stream;
- capture/replay de CUDA Graphs.

La comparación debe usar eventos CUDA/HIP, no solo `time.perf_counter()`, porque el lanzamiento GPU es asíncrono.

## 18. Pruebas de correctness

### Alias

Modificar el resultado y comprobar si el productor cambia:

```python
x = torch.arange(8, device="cuda")
y = v911.from_dlpack(x)
y[^5_0] = 99
assert x[^5_0] == 99
```

Solo realizar esto si el contrato permite escritura.

### Lifetime

```python
y = v911.import_tensor(x)
del x
torch.cuda.synchronize()
use(y)
```

Debe funcionar solo si V911 retiene correctamente el owner.

### Streams

- escribir `x` en stream A;
- importar en stream B;
- lanzar V911;
- comprobar resultado sin `synchronize()` global.


### Dispositivos

- CUDA device 0/1;
- ROCm device 0/1;
- tensor CPU rechazado en ruta GPU;
- dispositivo incompatible con `copy=False`.


### Strides

- contiguous;
- transposed;
- sliced;
- offset;
- stride negativo, si se rechaza;
- zero-size.


### Deleters

- consumir cápsula una vez;
- destruir cápsula sin consumir;
- destruir consumer antes del producer;
- finalizar Python después del consumer;
- ejecutar destructor desde otro hilo.


## 19. Roadmap de implementación

### Fase 1: DLPack Python N1

- importar `__dlpack__`;
- soportar CUDA y ROCm;
- validar device/dtype/shape/stride;
- implementar deleter;
- ejecutar un kernel simple;
- probar ownership y streams.


### Fase 2: salida zero-copy

- reservar salida en el framework productor;
- escribir directamente desde V911;
- devolver view sin copia;
- documentar mutabilidad;
- evitar creación de arrays intermedios.


### Fase 3: C Exchange N0

- detectar `__dlpack_c_exchange_api__`;
- obtener `DLTensor` no gestionado;
- consultar stream actual;
- lanzar el kernel en ese stream;
- fallback automático a `__dlpack__`.


### Fase 4: GPU-resident Krylov

- mover $V,Z,H$ a GPU;
- fusionar Arnoldi;
- usar mixed precision;
- minimizar reducciones;
- añadir CUDA Graphs;
- integrar Woodbury en device.


### Fase 5: Rust

- exponer C ABI validado;
- wrappers safe/unsafe separados;
- ownership explícito;
- pruebas Miri donde aplique;
- no exponer `PyCapsule` directamente a Rust inicialmente.


### Fase 6: custom operator

- registrar operación PyTorch;
- soporte autograd opcional;
- dispatch CUDA/HIP;
- compatibilidad con `torch.compile` solo después de estabilizar eager.


## Recomendación final

Para V911, la arquitectura recomendada es:

$$
\boxed{
\text{DLPack N1 como fallback}
+
\text{DLPack C Exchange N0 como fast path}
+
\text{CUDA/HIP stream-aware}
+
\text{kernels GPU-resident}
+
\text{C++/Rust ABI independiente de PyTorch}
}
$$

El orden correcto es:

1. implementar DLPack Python con lifetime y streams correctos;
2. medir dónde está realmente el overhead;
3. añadir C Exchange para eliminar cápsulas y llamadas Python repetitivas;
4. hacer FGMRES y Woodbury completamente residentes en HBM;
5. añadir Rust solo sobre un descriptor C validado;
6. integrar autograd/custom ops únicamente si el caso de uso lo exige.

La ganancia científica esperable no proviene solo de “pasar el puntero HBM3”. Proviene de mantener **datos, bases Krylov, precondicionador, kernels y reducciones en el mismo dispositivo y stream**, evitando tanto copias como sincronizaciones host-device.

<span style="display:none">[^5_10][^5_11][^5_12][^5_13][^5_14][^5_15][^5_16][^5_17][^5_18][^5_19][^5_20][^5_21][^5_22][^5_23][^5_24][^5_25][^5_26][^5_27][^5_28][^5_29][^5_8][^5_9]</span>

<div align="center">⁂</div>

[^5_1]: https://dmlc.github.io/dlpack/latest/python_spec.html

[^5_2]: https://docs.pytorch.org/docs/stable/dlpack.html

[^5_3]: https://dmlc.github.io/dlpack/latest/c_api.html

[^5_4]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.2.1/understand/programming_model.html

[^5_5]: https://docs.pytorch.org/tutorials/advanced/cpp_extension.html

[^5_6]: https://data-apis.org/array-api/2025.12/API_specification/generated/array_api.array.__dlpack__.html

[^5_7]: https://data-apis.org/array-api/latest/API_specification/generated/array_api.array.__dlpack__.html

[^5_8]: https://docs.pytorch.org/docs/2.8/dlpack.html

[^5_9]: https://docs.pytorch.org/docs/2.9/dlpack.html

[^5_10]: https://docs.pytorch.org/docs/2.8/generated/torch.from_dlpack.html

[^5_11]: https://docs.pytorch.org/docs/2.12/generated/torch.from_dlpack.html

[^5_12]: https://docs.cupy.dev/en/stable/reference/environment.html

[^5_13]: https://docs.cupy.dev/en/v13.5.1/reference/environment.html

[^5_14]: https://docs.cupy.dev/en/stable/reference/generated/cupy.from_dlpack.html

[^5_15]: https://pytorch.ac.cn/docs/2.5/dlpack.html

[^5_16]: https://www.doc.ic.ac.uk/project/2021/mscprj/g21mscprj08/project/venv/lib/python3.8/site-packages/torch/utils/dlpack.py

[^5_17]: https://dmlc.github.io/dlpack/latest/

[^5_18]: https://app.readthedocs.org/projects/cupy/downloads/pdf/latest/

[^5_19]: http://docs.pytorch.org/pytorch_sphinx_theme/advanced/cpp_extension.html

[^5_20]: https://rocmdocs.amd.com/projects/HIP/en/develop/how-to/faq.html

[^5_21]: https://docs.pytorch.org/tutorials/advanced/cpp_custom_ops.html

[^5_22]: https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/asynchronous.html

[^5_23]: https://rocm.docs.amd.com/projects/HIP/en/docs-5.2.1/user_guide/programming_manual.html

[^5_24]: https://rocm.docs.amd.com/projects/HIP/en/docs-5.4.4/user_guide/programming_manual.html

[^5_25]: https://rocm.docs.amd.com/projects/HIP/en/docs-5.7.0/user_guide/programming_manual.html

[^5_26]: https://rocm.github.io/hip/Synchonization.html

[^5_27]: https://rocm.docs.amd.com/projects/HIP/en/docs-5.6.1/user_guide/faq.html

[^5_28]: https://rocm.docs.amd.com/en/docs-6.4.0/about/release-notes.html

[^5_29]: https://supercharleszhu.github.io/posts/2026-06-26-00/


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La profundización más importante para V911 es que DLPack 1.x ya no debe tratarse solo como una cápsula Python. La ruta SOTA es implementar dos niveles:

$$
\text{N1: } \_\_dlpack\_\_ \text{ para retención/intercambio}
$$

y

$$
\text{N0: } \_\_dlpack\_c\_exchange\_api\_\_
\text{ para kernels inmediatos sin sincronización}.
$$

La especificación C actual define precisamente funciones para obtener un `DLTensor` temporal, consultar el stream de trabajo del productor y ejecutar el kernel sobre ese stream.[^6_1]

## 1. Corrección de la arquitectura

La afirmación “DLPack elimina todo overhead de marshaling” debe matizarse. Elimina el coste $O(N)$ de copiar datos, pero puede dejar:

$$
T_{\mathrm{interop}}
=
T_{\mathrm{metadata}}
+
T_{\mathrm{stream}}
+
T_{\mathrm{ownership}}
+
T_{\mathrm{launch}}.
$$

El diseño óptimo para V911 es evitar también:

- crear una `PyCapsule` por iteración;
- llamar a `__dlpack__` desde Python dentro de cada paso Krylov;
- sincronizar el dispositivo;
- copiar shapes/strides a estructuras temporales;
- consultar el stream mediante APIs Python;
- devolver cada vector intermedio a Python.

El camino de producción debería ser:

```text
PyTorch/CuPy tensor
    ↓
DLPack C Exchange API
    ↓
DLTensor temporal
    ↓
validación sin asignaciones
    ↓
kernel CUDA/HIP sobre el stream productor
    ↓
resultado en tensor preasignado
```

La ruta tradicional `__dlpack__` debe permanecer como fallback de compatibilidad.

## 2. DLPack versionado

El código debe distinguir entre:

- `DLManagedTensor`, interfaz heredada;
- `DLManagedTensorVersioned`, interfaz actual;
- `DLTensor`, vista temporal no propietaria.

La especificación actual usa versiones mayores para cambios ABI y versiones menores para adiciones compatibles; el consumidor debe validar la versión mayor antes de leer la estructura.[^6_1]

Implementar:

```cpp
if (version.major != DLPACK_MAJOR_VERSION) {
    managed->deleter(managed);
    throw std::runtime_error("unsupported DLPack ABI");
}
```

Para cápsulas:

```text
"dltensor"
"dltensor_versioned"
```

y después de consumirlas:

```text
"used_dltensor"
"used_dltensor_versioned"
```

Nunca consumir dos veces la misma cápsula. PyTorch documenta que el uso múltiple de una cápsula DLPack tiene comportamiento indefinido.[^6_2]

## 3. Fast path N0

La API C Exchange debe descubrirse en el tipo del objeto, no en cada instancia si puede evitarse:

```cpp
PyObject* type_obj = reinterpret_cast<PyObject*>(Py_TYPE(obj));
PyObject* cap =
    PyObject_GetAttrString(type_obj, "__dlpack_c_exchange_api__");
```

La cápsula debe tener el nombre:

```text
dlpack_exchange_api
```

Después:

```cpp
const DLPackExchangeAPI* api =
    static_cast<const DLPackExchangeAPI*>(
        PyCapsule_GetPointer(cap, "dlpack_exchange_api")
    );
```

Cachear el puntero por tipo Python:

```text
PyTypeObject* → ExchangeAPI*
```

con una referencia fuerte al tipo para evitar que desaparezca. La propia especificación recomienda buscar la API en el tipo y permite cachearla por tipo único.[^6_1]

### Dos funciones distintas

Para V911 hay que distinguir cuidadosamente:

#### `dltensor_from_py_object_no_sync`

Devuelve una vista temporal sin ownership. Es ideal para:

```text
importar
lanzar kernel
retornar
```

La memoria y metadata solo están garantizadas hasta que retorna el control.[^6_1]

#### `managed_tensor_from_py_object_no_sync`

Devuelve un tensor gestionado. Es necesario si:

- el kernel se completa después del retorno;
- se guarda el tensor en una cola asíncrona;
- se construye un grafo;
- el solver mantiene referencias entre iteraciones;
- el trabajo se entrega a otro hilo.

Regla:

$$
\text{uso síncrono dentro de la llamada}
\Rightarrow
\text{DLTensor temporal}
$$

$$
\text{uso asíncrono o retención}
\Rightarrow
\text{DLManagedTensorVersioned}
$$

## 4. Stream semantics exactas

La especificación Array API actual define semánticas específicas para CUDA y ROCm. En CUDA:

- `None` representa el stream por defecto heredado;
- `1` representa el legacy default stream;
- `2` representa el per-thread default stream;
- valores mayores representan streams concretos;
- `0` es ambiguo y no debe usarse.

En ROCm, los identificadores por defecto no son iguales: `None` y `0` tienen semántica de stream por defecto, mientras que `1` y `2` no están soportados.[^6_3]

Esto impide codificar un único valor universal:

```cpp
stream = 0; // incorrecto como abstracción portable
```

V911 debe tener un adaptador por backend:

```cpp
struct WorkStream {
    DeviceType device;
    int device_id;
    void* native_stream;
};
```

y:

```cpp
WorkStream get_current_work_stream(
    const DLPackExchangeAPI& api,
    DLDevice device
);
```

No convertir indiscriminadamente un stream HIP en `cudaStream_t`, aunque el tipo subyacente sea un puntero opaco.

## 5. Sincronización: tres políticas

### Política A: same-stream

El productor y V911 ejecutan en el mismo stream:

```text
producer writes x
V911 kernel reads x
V911 kernel writes y
consumer reads y
```

No requiere una sincronización adicional porque el stream garantiza orden FIFO.

Esta debe ser la política principal del fast path N0.

### Política B: event handoff

Cuando productor y consumidor usan streams diferentes:

$$
S_p
\xrightarrow{\text{record event}}
E
\xrightarrow{\text{wait event}}
S_c.
$$

Usar eventos, no:

```cpp
cudaDeviceSynchronize();
hipDeviceSynchronize();
```

La sincronización global destruye el solapamiento y puede inutilizar la ganancia de zero-copy.

### Política C: host synchronization

Solo para fallback o CPU. Es segura, pero debe marcarse como lenta:

```text
sync_mode="host"
```

No ocultar esta ruta bajo el nombre “zero-copy”.

## 6. Read-only y mutabilidad

DLPack moderno incorpora `DLPACK_FLAG_BITMASK_READ_ONLY`. El consumidor debe comprobarlo antes de escribir.[^6_1]

Definir dos APIs distintas:

```python
v911.apply(x, out)
v911.apply_inplace(x)
```

La primera exige que `x` sea solo lectura. La segunda exige:

- tensor writable;
- no ser una vista read-only;
- no tener alias peligroso;
- contrato explícito con autograd.

PyTorch documenta que los tensores obtenidos mediante DLPack comparten memoria y que las operaciones in-place pueden modificar el tensor de entrada.[^6_2]

Para evitar corrupción silenciosa:

```cpp
if (is_write && (flags & DLPACK_FLAG_BITMASK_READ_ONLY)) {
    throw py::value_error("input is read-only");
}
```


## 7. Autograd y aliasing

El zero-copy no crea automáticamente un nodo de autograd. Si V911 modifica directamente storage de PyTorch:

```text
x.storage ← V911
```

el grafo no conoce esa operación.

Tres modos claros:


| Modo | Comportamiento |
| :-- | :-- |
| `inference` | Zero-copy mutable o read-only |
| `no_grad` | Zero-copy sin registrar backward |
| `autograd` | Custom op explícita con forward/backward |

Nunca inferir autograd por el simple hecho de recibir un tensor PyTorch.

Para la fase inicial:

```cpp
TORCH_CHECK(!requires_grad, 
            "V911 fast path requires no_grad tensor");
```

Después, registrar un custom operator separado. PyTorch mantiene documentación específica para extensiones C++/CUDA y custom operators.[^6_4][^6_5]

## 8. FGMRES completamente residente en GPU

El verdadero beneficio aparece cuando DLPack alimenta un solver que no vuelve a Python entre iteraciones.

Guardar en HBM:

$$
V_m=[v_1,\ldots,v_m],
\qquad
Z_m=[z_1,\ldots,z_m].
$$

Guardar en GPU o memoria pinned:

$$
H_m\in\mathbb{R}^{(m+1)\times m}.
$$

La secuencia debe ser:

```text
x, b, V, Z, U, V_lowrank → HBM
apply_A → kernel CUDA/HIP
dot/norm → reductions GPU
Arnoldi → fused kernels
Woodbury small solve → GPU or pinned host
Givens → tiny matrix
```

El peor diseño sería:

```text
DLPack import
GPU→CPU residual
NumPy dot
CPU→GPU
next iteration
```

Eso elimina el beneficio del zero-copy. DLPack debe integrarse a nivel de todo el algoritmo, no solo de la función de entrada.

### Reducciones

FGMRES tiene muchas reducciones globales. Las mejoras SOTA son:

- fused dot + axpy;
- block Arnoldi;
- pipelined/reorganized GMRES;
- s-step GMRES;
- mixed precision;
- reducción en una sola llamada;
- bases de bloque para varios right-hand sides;
- comunicación GPU-direct en multi-GPU.

DLPack resuelve el intercambio de storage, pero la latencia de `dot` y la sincronización de streams pueden seguir dominando.

## 9. Woodbury en GPU

La parte de bajo rango debe permanecer en device:

$$
z
=
P^{-1}r
-
P^{-1}U
\left(C^{-1}+V^\top P^{-1}U\right)^{-1}
V^\top P^{-1}r.
$$

Precalcular:

$$
G=P^{-1}U,
\qquad
S=C^{-1}+V^\top G.
$$

Mantener:

- $U,V,G$ en HBM;
- $S$ en FP64;
- factorización de $S$ reutilizable;
- workspace persistente;
- ninguna copia por iteración.

Si $r$ es pequeño, resolver $S$ en host puede ser razonable, pero solo si:

- el sistema reducido se reutiliza;
- la transferencia es asíncrona;
- se solapan con otro kernel;
- no se hace una ida y vuelta por cada vector Krylov.

Mejor opción para muchas aplicaciones:

```text
factorizar S una vez
copiar factor pequeño a GPU
resolver todos los RHS mediante batched solve
```


## 10. CUDA Graphs y captura

El fast path N0 debe ser compatible con CUDA Graph capture. La documentación de CUDA indica que la captura convierte las operaciones sobre un stream en un grafo, y que hay restricciones específicas sobre streams y operaciones durante captura.[^6_6][^6_7]

Durante captura:

- no crear `PyCapsule`;
- no invocar `__dlpack__` en cada iteración;
- no asignar memoria;
- no llamar `cudaDeviceSynchronize`;
- no cambiar shapes;
- no cambiar punteros;
- no crear handles cuBLAS/cuSOLVER repetidamente;
- no usar operaciones host-síncronas.

Diseñar una fase de preparación:

```text
prepare_graph(x, y, workspace, shape, dtype, device)
capture()
replay()
```

El API debe distinguir:

```python
v911.prepare(...)
v911.run(...)
v911.replay(...)
```

No intentar hacer graph capture como efecto secundario de `solve()`.

## 11. Multi-GPU y HBM3

Para varias GPU:

```text
device_id productor
device_id V911
peer access
allocator
stream
```

deben validarse de forma conjunta.

Casos:


| Caso | Acción |
| :-- | :-- |
| Mismo dispositivo | Zero-copy |
| Dispositivo distinto con P2P | Peer copy explícita |
| Dispositivo distinto sin P2P | Error con `copy=False` |
| CPU pinned | Copia asíncrona |
| Unified memory | Tratar según backend, no asumir zero-copy efectivo |
| ROCm GPU | HIP stream/device path |

La semántica `copy=False` debe ser estricta: si la operación necesita copia, lanzar `BufferError`, como establece la especificación Array API.[^6_3]

## 12. Rust: arquitectura segura

No recomiendo que Rust consuma directamente una `PyCapsule` en la primera iteración. Mejor:

```text
Python
  ↓
C++/pybind11 DLPack importer
  ↓
ValidatedTensorDescriptor
  ↓
Rust FFI
  ↓
CUDA/HIP kernel
```

El descriptor C ABI:

```c
typedef struct {
    void* data;
    int32_t device_type;
    int32_t device_id;
    int32_t ndim;
    uint8_t dtype_code;
    uint8_t dtype_bits;
    uint16_t dtype_lanes;
    const int64_t* shape;
    const int64_t* strides;
    uint64_t byte_offset;
    uint64_t flags;
    void* stream;
} V911TensorView;
```

Rust recibe el descriptor solo durante la llamada:

```rust
pub unsafe fn validate_view(v: &V911TensorView) -> Result<View, Error> {
    if v.data.is_null() && v.ndim > 0 {
        return Err(Error::NullData);
    }
    if v.ndim < 0 || v.ndim > 8 {
        return Err(Error::Rank);
    }
    // validar shape, strides, dtype, device
    Ok(View { ... })
}
```

Separar:

```text
unsafe FFI boundary
safe validated view
kernel launcher
```

Si Rust retiene un buffer, debe retener también el owner/deleter, no solo el puntero.

## 13. Versiones y compatibilidad

DLPack actual introduce:

- `max_version`;
- `dl_device`;
- `copy`;
- arrays versionados;
- flags de read-only;
- tipos sub-byte;
- API C Exchange.

El consumidor debe intentar:

```text
1. C Exchange API
2. __dlpack__(max_version=(1, 0), copy=False, ...)
3. __dlpack__(stream=...)
4. legacy capsule
5. error explícito
```

No pasar argumentos nuevos sin capturar `TypeError`, porque productores antiguos pueden implementar solo la firma histórica.

Pseudocódigo:

```cpp
try:
    capsule = obj.__dlpack__(
        stream=stream,
        max_version=(1, 0),
        dl_device=device,
        copy=False
    )
except TypeError:
    capsule = obj.__dlpack__(stream=stream)
```

La especificación recomienda verificar incluso la versión solicitada, ya que el productor puede devolver una versión diferente.[^6_3]

## 14. Alternativas SOTA a DLPack

DLPack es el estándar interframework, pero no siempre es la ruta de máxima eficiencia dentro de un único ecosistema.

### PyTorch custom operator

Mejor si:

- todo el pipeline es PyTorch;
- se necesita autograd;
- se usa `torch.compile`;
- se requiere dispatcher CUDA/ROCm.


### CUDA Array Interface

Útil dentro del ecosistema CUDA Python, pero no sustituye la portabilidad de DLPack y tiene semánticas diferentes.

### C++ ATen/LibTorch

Mejor acceso a streams, allocator y dispatch PyTorch, pero mayor acoplamiento ABI.

### Apache Arrow CUDA buffers

Adecuado para intercambio columnar y ecosistemas Arrow, no como sustituto general de tensores estriados.

### TVM FFI / interfaces similares

Pueden reducir acoplamiento a una instalación concreta de PyTorch y aprovechar DLPack C Exchange. Son interesantes si V911 busca un ABI de runtime más estable, pero añaden una dependencia arquitectónica adicional.

La estrategia más sostenible es:

```text
DLPack como ABI de intercambio
custom op como integración PyTorch opcional
```


## 15. Benchmark científico

Medir con eventos CUDA/HIP:

```text
event_start.record(stream)
v911.run(...)
event_end.record(stream)
elapsed = event_start.elapsed_time(event_end)
```

Separar:

$$
T_{\mathrm{total}}
=
T_{\mathrm{import}}
+
T_{\mathrm{validation}}
+
T_{\mathrm{sync}}
+
T_{\mathrm{launch}}
+
T_{\mathrm{compute}}
+
T_{\mathrm{copy}}.
$$

Experimentos:

1. NumPy + ctypes.
2. PyTorch + pybind11 buffer.
3. PyTorch + `__dlpack__`.
4. PyTorch + C Exchange temporal.
5. Managed DLPack.
6. Custom op ATen.
7. CUDA Graph replay.
8. ROCm HIP equivalente.
9. Multi-GPU P2P.
10. FGMRES de 10, 50 y 100 iteraciones.

Escalar:

- $N=10^3$ hasta $10^8$;
- rank $r=8,32,128$;
- FP16/BF16/FP32/FP64;
- contiguous y strided;
- 1 y múltiples streams;
- una y múltiples GPU.

Reportar:

- GB/s efectivo;
- latencia µs;
- sincronizaciones por iteración;
- número de cápsulas;
- kernels;
- ocupación;
- HBM;
- norma residual;
- error de ortogonalidad;
- speedup frente a la ruta ctypes.


## 16. Plan de implementación actualizado

### Fase A: contrato DLPack

- fijar header y versión;
- implementar importación legacy y versionada;
- validar device/dtype/shape/strides;
- comprobar flags read-only;
- tests de deleter/lifetime.


### Fase B: fast path N0

- descubrir `__dlpack_c_exchange_api__`;
- cachear API por tipo;
- usar `dltensor_from_py_object_no_sync`;
- obtener `current_work_stream`;
- lanzar en el mismo stream;
- fallback N1.


### Fase C: backend GPU

- CUDA y HIP separados;
- workspace persistente;
- allocator por backend;
- streams explícitos;
- eventos entre streams;
- kernels fusionados.


### Fase D: solver residente

- FGMRES/Arnoldi GPU;
- Woodbury GPU;
- reducción de sincronizaciones;
- mixed precision;
- CUDA Graphs;
- multi-GPU opcional.


### Fase E: Rust

- C ABI validado;
- wrappers seguros;
- ownership explícito;
- tests de concurrencia;
- integración solo después de estabilizar C++.


## Recomendación final

El diseño SOTA para V911 es:

$$
\boxed{
\text{N0 C Exchange}
+
\text{N1 DLPack fallback}
+
\text{stream actual del productor}
+
\text{copy=False estricto}
+
\text{kernels CUDA/HIP residentes}
+
\text{FGMRES/Woodbury en HBM}
}
$$

La mejora más importante no será pasar de un buffer Python a un puntero HBM3 aislado. Será eliminar toda la cadena de sincronizaciones y copias que rodea al solver:

```text
sin CPU intermedio
sin cápsula por iteración
sin stream 0 forzado
sin device synchronize
sin arrays temporales
sin reconstrucción de metadata
```

DLPack debe funcionar como ABI de memoria y stream; el rendimiento SOTA se obtiene cuando esa ABI alimenta un solver Krylov completamente residente en GPU, con ownership, read-only, versiones y semántica de streams tratados como parte formal del algoritmo, no como detalles de binding.

<span style="display:none">[^6_10][^6_11][^6_12][^6_13][^6_14][^6_15][^6_16][^6_17][^6_18][^6_19][^6_20][^6_21][^6_22][^6_23][^6_24][^6_25][^6_26][^6_27][^6_8][^6_9]</span>

<div align="center">⁂</div>

[^6_1]: https://dmlc.github.io/dlpack/latest/c_api.html

[^6_2]: https://docs.pytorch.org/docs/stable/dlpack.html

[^6_3]: https://data-apis.org/array-api/latest/API_specification/generated/array_api.array.__dlpack__.html

[^6_4]: https://docs.pytorch.org/tutorials/advanced/cpp_extension.html

[^6_5]: https://docs.pytorch.org/tutorials/advanced/cpp_custom_ops.html

[^6_6]: https://docs.nvidia.com/cuda/cuda-runtime-api/group\_\_CUDART\_\_STREAM.html

[^6_7]: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/cuda-graphs.html

[^6_8]: https://arrow.apache.org/docs/python/dlpack.html

[^6_9]: https://data-apis.org/array-api/draft/API_specification/generated/array_api.array.__dlpack__.html

[^6_10]: https://data-apis.org/array-api/2024.12/API_specification/generated/array_api.array.__dlpack__.html

[^6_11]: https://data-apis.org/array-api/draft/API_specification/array_object.html

[^6_12]: https://numpy.org/devdocs//user/basics.interoperability.html

[^6_13]: https://numpy.org/doc/2.2/user/basics.interoperability.html

[^6_14]: https://numpy.org/doc/2.1/user/basics.interoperability.html

[^6_15]: https://github.com/dmlc/dlpack/blob/main/include/dlpack/dlpack.h

[^6_16]: https://docs.rs/dlpack-rs/latest/dlpack_rs/ffi/struct.DLPackExchangeAPI.html

[^6_17]: https://fossies.org/diffs/pytorch/2.9.1_vs_2.10.0/test/test_dlpack.py-diff.html

[^6_18]: https://docs.nvidia.com/deeplearning/dali/user-guide/docs/data_types.html

[^6_19]: https://docs.nvidia.com/dl-cuda-graph/cuda-graph-basics/constraints.html

[^6_20]: https://data-apis.org/array-api/2023.12/API_specification/generated/array_api.array.__dlpack__.html

[^6_21]: https://rocm.docs.amd.com/en/docs-7.2.3/compatibility/ml-compatibility/pytorch-compatibility.html

[^6_22]: https://github.com/pytorch/pytorch/pull/150217/files

[^6_23]: https://deepwiki.com/dmlc/dlpack/4.2-integration-guidelines

[^6_24]: https://github.com/jax-ml/jax/blob/main/jax/\_src/dlpack.py

[^6_25]: https://data-apis.org/array-api/2025.12/API_specification/generated/array_api.array.__dlpack__.html

[^6_26]: https://dmlc.github.io/dlpack/latest/python_spec.html

[^6_27]: https://dmlc.github.io/dlpack/latest/


---

# 4. Precisión Mixta Dinámica (Refinamiento Ausente) evalua mejoras y soluciones cientificas SOTA

Brecha (V911): Operamos a ciegas en float64, sobreutilizando registros vectoriales (AVX2/AVX512) para pasos intermedios de iteraciones que toleran baja precisión.
Solución Asintótica Pendiente: Implementar Tensor Cores (BF16 / FP16) para la reducción inicial en FGMRES, delegando el refinamiento del residual a float64 exclusivamente en el bucle externo (Mixed Precision Iterative Refinement).
Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La solución SOTA para V911 no es ejecutar todo FGMRES en BF16/FP16 y corregir al final. El diseño robusto es un **GMRES-IR de cinco precisiones**, con reducción inicial en Tensor Cores, acumulación FP32, ortogonalización adaptativa y residual externo FP64/FP64 ampliado.

La literatura reciente muestra que el refinamiento GMRES puede mantener precisión alta usando kernels de baja precisión, pero advierte que reducir indiscriminadamente producto matriz-vector u ortogonalización causa estancamiento. Los resultados más recientes de GMRES aumentado refuerzan la necesidad de conservar operaciones críticas o usar correcciones de alta precisión.[^7_1][^7_2]

## 1. Modelo correcto de precisión

Separar cinco precisiones:


| Símbolo | Componente | Candidato |
| :-- | :-- | :-- |
| $u$ | almacenamiento de solución/base | FP32 o FP64 |
| $u_f$ | factores/precondicionador | BF16/FP16/FP32 |
| $u_g$ | aritmética interna GMRES | FP16/BF16/FP32 |
| $u_p$ | aplicación precondicionada | FP16/BF16/FP32 |
| $u_r$ | residual y actualización externa | FP64 |

La arquitectura objetivo es:

$$
(u_g,u_p,u_f)=(\mathrm{BF16/FP16},\mathrm{FP32}),
\qquad
u_r=\mathrm{FP64}.
$$

El artículo sobre GMRES de cinco precisiones formaliza precisamente esta separación entre precisión de trabajo, factorización, residual, trabajo interno de GMRES y aplicación del precondicionador.[^7_2][^7_3]

## 2. Algoritmo GMRES-IR para V911

Sea el sistema:

$$
Ax=b.
$$

Mantener una solución externa de alta precisión $x_k^{(64)}$. En cada ciclo:

1. calcular el residual verdadero en FP64:

$$
r_k=b-Ax_k^{(64)};
$$
2. resolver aproximadamente:

$$
A\\delta x_k\\approx r_k
$$

mediante FGMRES de baja precisión;
3. 
# convertir y acumular: \[ x\_{k+1}^{(64)}

x_k^{(64)}+\\delta x_k^{(64)};
\]
4. recomputar el residual en FP64;
5. repetir mientras el backward error mejore.

Pseudocódigo:

```text
x64 = x0

for outer = 0 .. max_outer:
    r64 = b64 - A64(x64)
    eta = norm(r64) / (norm(A64)*norm(x64) + norm(b64))

    if eta <= tolerance:
        stop

    delta_low = FGMRES_low_precision(r64)
    x64 += cast_fp64(delta_low)

    r64_new = b64 - A64(x64)

    if norm(r64_new) >= stagnation_factor * norm(r64):
        increase_inner_precision()
        restart_or_rebuild_preconditioner()
```

La actualización de $x$ debe permanecer en FP64 aunque $\delta x$ se calcule en FP16/BF16/FP32. La mayor parte de la recuperación de precisión procede de recomputar el residual verdadero, no de convertir retrospectivamente una solución de baja precisión.

## 3. BF16 frente a FP16

### BF16

Ventaja:

$$
\text{exponente BF16} \approx \text{exponente FP32}
$$

Por tanto, ofrece mayor rango dinámico y menor riesgo de overflow/underflow.

Desventaja:

- solo 7 bits de significando;
- peor precisión relativa;
- puede necesitar escalado o acumulación FP32.


### FP16

Ventaja:

- más precisión relativa que BF16;
- Tensor Cores muy eficientes;
- mejor para problemas escalados.

Desventaja:

- rango dinámico reducido;
- más sensible a overflow;
- requiere escalado por bloque o global.


### Recomendación

- usar BF16 para almacenamiento de vectores si hay gran rango dinámico;
- usar FP16 para GEMM si el escalado está controlado;
- acumular siempre en FP32;
- mantener residual y solución externa en FP64;
- elegir automáticamente según:

$$
\\rho_A=\\frac{\\max |A\_{ij}|}{\\min\_{A\_{ij}\\ne0}|A\_{ij}|}.
$$

Si $\rho_A$ es grande, BF16 puede evitar overflow, pero su pérdida de significando puede exigir refinamiento adicional. Si el escalado es bueno, FP16 puede ofrecer mejor calidad.

## 4. Tensor Cores correctamente

Tensor Cores no deben usarse como si fueran un simple reemplazo de `double` por `half`.

El patrón recomendable es:

$$
C_{\mathrm{FP32}}
=
A_{\mathrm{FP16/BF16}}
B_{\mathrm{FP16/BF16}}
\quad\text{acumulado en FP32}.
$$

Los Tensor Cores de NVIDIA aceptan operandos FP16/BF16 y acumulan en FP32 en los modos apropiados. La literatura sobre refinamiento con Tensor Cores muestra que la estabilidad se recupera mediante GMRES/IR, escalado y redondeo adaptativo, no usando baja precisión sin control.[^7_4][^7_5][^7_6]

Para V911:

- almacenar $U,V$ de Woodbury en FP16/BF16;
- acumular $V^\top x$ en FP32;
- factorizar el sistema reducido $S$ en FP64;
- actualizar la solución en FP64;
- usar GEMM de Tensor Core para bases de bloque;
- evitar FP16 en las reducciones finales de norma y producto interno.


## 5. Arnoldi mixto: qué puede bajar de precisión

No todas las operaciones tienen la misma sensibilidad.


| Operación | Baja precisión | Precisión recomendada |
| :-- | --: | --: |
| `apply_A` aproximado | Sí | FP16/BF16 → FP32 |
| precondicionador Woodbury | Sí | storage bajo, solve reducido FP64 |
| GEMM de bloques | Sí | Tensor Core + acumulación FP32 |
| `axpy` interno | Sí | FP32 |
| dot products | Limitado | FP32 acumulado, corrección FP64 |
| ortogonalización | Adaptativa | FP32/FP64 |
| Hessenberg $H$ | No extrema | FP64 o FP32 con corrección |
| Givens | No | FP64 |
| residual verdadero | No | FP64 |
| actualización $x$ | No | FP64 |

El error más peligroso sería:

```text
matvec FP16
dot FP16
orthogonalization FP16
residual FP16
```

Eso suele producir pérdida de ortogonalidad y estancamiento en una tolerancia de orden de la precisión interna. Trabajos recientes sobre GMRES aumentado muestran justamente que bajar simultáneamente matvec y ortogonalización puede provocar stagnation; el esquema robusto debe reservar operaciones externas de alta precisión y elevar adaptativamente las internas.[^7_1]

## 6. Ortogonalización estable

Para Arnoldi:

$$
w=A z_j,
\qquad
h_{ij}=v_i^\top w,
\qquad
w\leftarrow w-h_{ij}v_i.
$$

Usar:

1. productos $v_i^\top w$ acumulados en FP32;
2. corrección selectiva en FP64;
3. reortogonalización si:

$$
|V^\\top w| \\text{ es demasiado grande}
$$

o si:

$$
|w\_{\\mathrm{post}}| < \\theta |w\_{\\mathrm{pre}}|.
$$

Una prueba práctica:

```text
norm_before = norm(w)
MGS(w, V)
norm_after = norm(w)

if norm_after < 0.5 * norm_before:
    MGS(w, V) again
```

En el segundo pase, usar acumulación FP64. Para bloques grandes, TSQR o Householder en FP32/FP64 mixto es preferible a MGS completamente FP16.

## 7. Residual verdadero y backward error

No detenerse con:

$$
\|r_{\mathrm{internal}}\| \leq \tau.
$$

Calcular:

$$
r=b-Ax
$$

en FP64, preferiblemente usando un operador de precisión alta.

El criterio recomendado es backward error escalado:

$$
\eta(x)
=
\frac{\|b-Ax\|_\infty}
{\|A\|_\infty\|x\|_\infty+\|b\|_\infty}.
$$

Parar si:

$$
\eta(x)\leq \tau_{\mathrm{backward}}.
$$

Para el problema de Cayley, añadir criterio geométrico:

$$
\|Y^\top Y-I\|_F
\leq
\tau_{\mathrm{orth}}.
$$

Esto es crucial: un residual lineal pequeño no garantiza que la actualización mantenga la restricción de Stiefel.

## 8. Escalado adaptativo

FP16 y BF16 exigen escalado. Definir por bloque:

$$
s_x = \frac{2^e}{\max_i |x_i|},
\qquad
\tilde{x}=s_x x.
$$

Elegir $e$ para mantener $\tilde{x}$ dentro del rango seguro.

Para GEMM bloqueado:

$$
\tilde{A}=D_r A D_c,
$$

con factores diagonales de escalado $D_r,D_c$. Después deshacer el escalado en la acumulación FP32.

Implementar:

- escalado por vector;
- escalado por bloque;
- detección de Inf/NaN;
- reintento con FP32;
- estadísticas de saturación.

No usar una única escala global si las columnas de $U,V$ tienen magnitudes muy distintas.

## 9. Precondicionador Woodbury mixto

Para:

$$
M^{-1}r
=
P^{-1}r
-
P^{-1}U
S^{-1}
V^\top P^{-1}r,
$$

usar:

- $P^{-1}$ aproximado en BF16/FP16 o FP32;
- $U,V$ comprimidas en FP16/BF16;
- productos grandes acumulados en FP32;
- $S$ y su factorización en FP64;
- salida $z$ en FP32;
- corrección final en FP64.

No almacenar el solve reducido en FP16 si $S$ está mal condicionado. Evaluar:

$$
\kappa(S).
$$

Si:

$$
\kappa(S)u_{\mathrm{low}}
\gtrsim 1,
$$

subir la precisión de $S$, aunque los bloques grandes continúen en baja precisión.

La compresión de rango debe considerar precisión:

$$
\sigma_{r+1}
\lesssim
u_{\mathrm{storage}}\sigma_1
$$

puede hacer que truncar más no tenga sentido numérico.

## 10. Precisión dinámica basada en síntomas

Una política SOTA debe cambiar precisión en runtime.

### Estado `FAST`

- `apply_A`: BF16/FP16;
- precondicionador: FP16/BF16;
- Arnoldi: FP32;
- residual verdadero cada varios ciclos;
- objetivo: máximo throughput.


### Estado `GUARDED`

Activar si:

- el residual no baja;
- $\|V^\top V-I\|$ crece;
- aparecen Inf/NaN;
- la condición estimada aumenta;
- la corrección externa empeora.

Cambios:

- matvec FP32;
- dot/reducción FP64;
- reortogonalización;
- residual externo cada iteración;
- reconstrucción de $S$.


### Estado `RECOVERY`

Activar si hay estancamiento:

- FGMRES completo en FP32/FP64;
- recomputar precondicionador;
- reiniciar base;
- reducir el tamaño de paso;
- usar solve directo reducido;
- fallback total FP64.

Pseudocódigo:

```text
if finite and decreasing:
    mode = FAST

if stagnation or loss_of_orthogonality:
    mode = GUARDED

if repeated_failure or NaN:
    mode = RECOVERY
```


## 11. Criterio de estancamiento

No usar solo una comparación entre dos residuos. Mantener una ventana:

$$
\rho_k =
\frac{\|r_{k-\ell}\|}{\|r_k\|}.
$$

Si durante $\ell$ iteraciones:

$$
\rho_k < 1+\delta,
$$

hay estancamiento.

También medir:

$$
\chi_k=
\frac{\|V^\top V-I\|_F}{u_{\mathrm{work}}}.
$$

Cambiar a mayor precisión si $\chi_k$ supera un umbral.

El refinamiento adaptable con precondicionadores de precisión variable ha mostrado que reducir el coste de almacenamiento y aplicación puede incrementar iteraciones; por tanto, la política debe optimizar coste total, no solo precisión local.[^7_7][^7_2]

## 12. Cinco precisiones para V911

Una asignación concreta:

$$
\begin{aligned}
u_r &= \mathrm{FP64}, \\
u_s &= \mathrm{FP64}, \\
u_g &= \mathrm{FP32}, \\
u_p &= \mathrm{BF16/FP16}, \\
u_f &= \mathrm{BF16/FP16}.
\end{aligned}
$$

Donde:

- $u_r$: residual verdadero;
- $u_s$: solución y actualización externa;
- $u_g$: Arnoldi y Hessenberg;
- $u_p$: aplicación del precondicionador;
- $u_f$: almacenamiento/factorización aproximada.

En hardware con Tensor Cores, una variante eficiente es:

```text
storage U,V,bases: BF16
GEMM: BF16 × BF16 → FP32
Arnoldi dot: FP32 + occasional FP64 correction
Hessenberg: FP64
Woodbury S: FP64
x and residual: FP64
```

Para CPU AVX2/AVX-512:

- FP32 vectorizado;
- BF16 si el ISA lo soporta;
- FP64 únicamente para residual/actualización;
- no asumir que FP16 CPU será eficiente.

En AMD GPU, verificar qué formatos y rutas Matrix Core soporta la arquitectura concreta; no trasladar automáticamente una política NVIDIA a ROCm.

## 13. Refinamiento externo con corrección fiable

El refinamiento puede fallar si el residual FP64 se calcula usando un operador que también perdió información. Para V911, implementar dos operadores:

```text
apply_A_low(x)   // Tensor Cores, aproximado
apply_A_high(x)  // FP64 o acumulación robusta
```

El residual usa siempre:

```text
r64 = b64 - apply_A_high(x64)
```

Si no es posible un `apply_A_high` completo por coste, usar:

- acumulación compensada;
- doble-single;
- split representation;
- evaluación periódica exacta;
- residual escalado.

La literatura de precisión mixta señala que la separación entre storage y compute ayuda a la robustez; no basta con convertir todos los datos a un formato bajo.[^7_8]

## 14. FP8: no como primera fase

FP8 puede ser interesante para precondicionadores o almacenamiento, pero no lo usaría inicialmente en FGMRES:

- rango y precisión dependen del formato;
- requiere escalas por tensor o bloque;
- los productos internos son más sensibles;
- el precondicionamiento Woodbury puede amplificar el error;
- la estabilidad del residual se vuelve más difícil.

Ruta evolutiva:

```text
FP64 baseline
→ FP32 inner
→ FP16/BF16 GEMM + FP32 accumulate
→ adaptive five-precision GMRES-IR
→ FP8 solo en storage/preconditioner experimental
```

La precisión más baja debe introducirse solo después de tener detectores de estancamiento y fallback fiables.

## 15. Tensor Core y memoria

La ganancia no es solo FLOP/s. BF16/FP16 reduce:

- ancho de banda;
- memoria de bases Krylov;
- presión sobre HBM;
- tráfico NVLink;
- coste de cache.

Si se almacenan $m$ vectores de longitud $n$:

$$
\text{memoria}_{16}
=
2nm,
\qquad
\text{memoria}_{32}
=
4nm,
\qquad
\text{memoria}_{64}
=
8nm.
$$

Pero no almacenar todo en baja precisión indiscriminadamente. Una política útil:

- bases históricas $V,Z$: FP32/BF16;
- vectores activos: FP32;
- residual externo: FP64;
- Hessenberg y coeficientes: FP64;
- subespacio reciclado: FP32 con reortogonalización FP64.


## 16. FGMRES y precondicionador variable

La precisión dinámica hace que el precondicionador cambie:

$$
M_j^{-1}
\in
\{
M_{\mathrm{BF16}}^{-1},
M_{\mathrm{FP32}}^{-1},
M_{\mathrm{FP64}}^{-1}
\}.
$$

Por eso debe usarse FGMRES, no GMRES estándar con una matriz precondicionada fija. Guardar:

$$
z_j=M_j^{-1}v_j
$$

en la precisión que permita reconstruir la solución de forma estable.

Cuando se cambia de precisión:

- conservar $v_j$ si sigue siendo ortonormal;
- descartar $z_j$ si fue generado con un precondicionador incompatible;
- reiniciar si el operador cambió significativamente;
- reciclar solo subespacios validados.


## 17. Solver reducido de Woodbury

El sistema reducido de Woodbury es una oportunidad para una política distinta:

$$
S=I+V^\top P^{-1}U.
$$

Aunque el operador grande use BF16, `S` debe permanecer en FP64 si:

- $r$ es pequeño;
- el solve se reutiliza;
- $\kappa(S)$ es elevada;
- la precisión geométrica de Cayley es estricta.

Usar:

```text
U,V storage: BF16
Vᵀ P⁻¹ U accumulation: FP64 block reduction
factor S: FP64 pivoted QR
apply S⁻¹: FP64
```

Esto produce una arquitectura asimétrica deliberada: baja precisión donde domina el tráfico, alta precisión donde domina la sensibilidad espectral.

## 18. Métricas de validación

El benchmark debe informar:

### Lineales

$$
\eta_{\mathrm{backward}},
\qquad
\frac{\|x_{\mathrm{mixed}}-x_{\mathrm{FP64}}\|}
{\|x_{\mathrm{FP64}}\|}.
$$

### Geométricas

$$
\|Y^\top Y-I\|_F,
\qquad
\|Y-Y_{\mathrm{reference}}\|_F.
$$

### Algorítmicas

- iteraciones internas;
- ciclos externos;
- restarts;
- reortogonalizaciones;
- escalados;
- cambios de precisión;
- fallbacks;
- condición estimada;
- ratio de progreso.


### Hardware

- Tensor Core utilization;
- FP64 utilization;
- bandwidth HBM;
- occupancy;
- synchronizations;
- energía;
- memoria pico.

La métrica objetivo es:

$$
\text{speedup útil}
=
\frac{T_{\mathrm{FP64}}}
{T_{\mathrm{mixed}}}
$$

sujeto a:

$$
\eta_{\mathrm{backward}}\leq\tau,
\qquad
\|Y^\top Y-I\|_F\leq\tau_{\mathrm{orth}}.
$$

## 19. Plan concreto de implementación

### Etapa 1: baseline

- conservar solver FP64;
- añadir residual verdadero;
- registrar backward error;
- registrar ortogonalidad;
- crear referencia reproducible.


### Etapa 2: FP32 inner

- `apply_A` FP32;
- FGMRES interno FP32;
- solución/residual FP64;
- validar convergencia.


### Etapa 3: Tensor Core

- convertir bloques a BF16/FP16;
- GEMM con acumulación FP32;
- escalado por bloque;
- precondicionador bajo precisión;
- Woodbury reducido FP64.


### Etapa 4: precisión adaptativa

- detector de estancamiento;
- reortogonalización;
- promotion BF16 → FP32 → FP64;
- fallback automático;
- recompilación/reconstrucción del precondicionador.


### Etapa 5: GPU-resident

- bases Krylov en device;
- residual sin copia host;
- reducciones fusionadas;
- CUDA Graphs/HIP equivalent;
- benchmark multi-stream.


## Recomendación final

Para V911, implementaría inicialmente:

$$
\boxed{
\text{GMRES-IR de cinco precisiones}
}
$$

con esta política:

```text
x, b, residual verdadero, Hessenberg reducido: FP64
bases y workspace: FP32
matvec/preconditionador: BF16 o FP16
GEMM: Tensor Core con acumulación FP32
Woodbury pequeño: FP64
ortogonalización: FP32 + corrección FP64
```

y promoción automática:

```text
BF16/FP16 → FP32 → FP64
```

cuando aparezcan pérdida de ortogonalidad, stagnation, overflow, NaN o empeoramiento del backward error.

La evidencia reciente respalda que GMRES basado en refinamiento puede recuperar precisión alta desde factorizaciones y kernels de baja precisión, incluso usando Tensor Cores; pero también muestra que la ortogonalización, el producto matriz-vector y la estabilidad del precondicionador no pueden degradarse sin control.[^7_5][^7_6][^7_2][^7_1]

La solución científica correcta no es “usar FP16 y corregir al final”, sino separar explícitamente **storage, cómputo interno, producto/precondicionamiento, residual y actualización**, con un controlador adaptativo que trate la precisión como parte del algoritmo Krylov.

<span style="display:none">[^7_10][^7_11][^7_12][^7_13][^7_14][^7_15][^7_16][^7_17][^7_18][^7_19][^7_20][^7_21][^7_22][^7_23][^7_24][^7_25][^7_26][^7_27][^7_9]</span>

<div align="center">⁂</div>

[^7_1]: https://onlinelibrary.wiley.com/doi/full/10.1002/nla.70117

[^7_2]: https://link.springer.com/article/10.1007/s00366-025-02187-z?error=cookies_not_supported\&code=19bf40e0-90bf-4df4-b9ab-80462289c10a

[^7_3]: https://www.irit.fr/en/departement/dep-hpc-simulation-optimization/

[^7_4]: https://developer.nvidia.com/blog/accelerating-tensorflow-on-a100-gpus/

[^7_5]: https://www.osti.gov/pages/biblio/1787013

[^7_6]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7302814/

[^7_7]: https://link.springer.com/content/pdf/10.1007/s00366-025-02187-z.pdf?error=cookies_not_supported\&code=da42e0c6-1703-4bd3-94ca-82feb934a32f

[^7_8]: https://raim2025.sciencesconf.org/data/program/slides_antoine_jego.pdf

[^7_9]: https://developer.download.nvidia.com/video/gputechconf/gtc/2020/presentations/s22082-training-neural-networks-with-tensor-core.pdf

[^7_10]: https://www.nvidia.cn/content/dam/en-zz/Solutions/Data-Center/nvidia-ampere-architecture-whitepaper.pdf

[^7_11]: https://link.springer.com/article/10.1007/s11227-026-08264-4?error=cookies_not_supported\&code=7c7f275e-1b9a-4671-89e3-2b7e0effc015

[^7_12]: https://onlinelibrary.wiley.com/doi/10.1002/nla.70117

[^7_13]: https://docs.nvidia.com/deeplearning/performance/mixed-precision-training/index.html

[^7_14]: https://arxiv.org/html/2602.14450v1

[^7_15]: https://arxiv.org/html/2604.18020v1

[^7_16]: https://ulopenaccess.com/papers/ULETE_V02I04/ULETE20250204_012.pdf

[^7_17]: https://www.emergentmind.com/topics/iterative-refinement-techniques

[^7_18]: https://www.irit.fr/en/departement/dep-hpc-simulation-optimization/apo-team/

[^7_19]: https://mumps-solver.org/index.php?page=doc

[^7_20]: https://www.theoj.org/joss-papers/joss.06698/10.21105.joss.06698.pdf

[^7_21]: https://centaur.reading.ac.uk/120344/8/s11075-025-02015-x.pdf

[^7_22]: https://ouci.dntb.gov.ua/en/works/45oGD1v9/

[^7_23]: https://perso.lip6.fr/Theo.Mary/publications.php

[^7_24]: https://www.connectedpapers.com/main/c810fcf6b622108076028359a13b491c0ce591a2

[^7_25]: https://www.scribd.com/document/828247572/A-Survey-of-Numerical-Linear-Algebra-Methods-Utilizing-Mixed-Precision-Arithmetic

[^7_26]: https://hal.science/hal-05071696v1/document

[^7_27]: https://bvieuble.me/publications/


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La mejora SOTA para V911 debe evolucionar desde un esquema fijo “FP16/FP32 interno + FP64 residual” hacia un **GMRES-IR adaptativo con precisión por componente, escalado por bloques, reinicios fiables y refinamiento del precondicionador**. La evidencia reciente indica que la precisión baja puede recuperar exactitud FP64, pero solo si el residual y la actualización permanecen en alta precisión, se controla la condición del sistema y se cambia de precisión ante estancamiento.[^8_1][^8_2]

## 1. Diseño recomendado

Para el sistema lineal de cada retracción:

$$
A_k \delta_k = r_k,
\qquad
r_k=b-A_kx_k,
$$

usar:

$$
\begin{aligned}
x_k,\;r_k &:\ \mathrm{FP64},\\
A_k\text{ aplicado} &:\ \mathrm{BF16/FP16}\to\mathrm{FP32},\\
\text{Arnoldi} &:\ \mathrm{FP32},\\
H_m,\;Givens,\;Woodbury\ reducido &:\ \mathrm{FP64},\\
\delta_k &:\ \mathrm{FP32}\to\mathrm{FP64}.
\end{aligned}
$$

El método exterior calcula:

$$
r_k^{(64)}=b^{(64)}-\operatorname{apply\_A}_{64}(x_k^{(64)}),
$$

y FGMRES resuelve aproximadamente:

$$
A_k\delta_k\approx r_k^{(64)}.
$$

Después:

$$
x_{k+1}^{(64)}
=
x_k^{(64)}
+
\operatorname{cast}_{64}(\delta_k).
$$

La corrección no debe acumularse en FP16 ni en FP32 si se busca precisión final FP64.

## 2. El punto crítico: condición espectral

El refinamiento no garantiza convergencia arbitraria. Una condición clásica es que el error introducido por la precisión interna sea suficientemente pequeño respecto a la inversa del condicionamiento. De forma cualitativa:

$$
\kappa(A)u_{\mathrm{low}}<1.
$$

Cuando $\kappa(A)u_{\mathrm{low}}$ es grande, el refinamiento puede:

- converger lentamente;
- estancarse;
- amplificar el ruido;
- oscilar;
- producir una solución con residual interno pequeño pero residual verdadero grande.

Los resultados publicados para Tensor Cores muestran recuperación de precisión FP64 mediante GMRES, factorización multiprecisión, escalado y redondeo adaptativo, no mediante una simple conversión de tipos.[^8_1]

Por eso V911 debe estimar durante la ejecución:

$$
\widehat{\kappa}(A),
\qquad
\|V^\top V-I\|,
\qquad
\eta_{\mathrm{backward}}.
$$

Una estimación barata puede obtenerse a partir de:

- crecimiento de $H_m$;
- cociente entre residuos;
- estimación de Ritz;
- norma de $S^{-1}$ en Woodbury;
- número de reortogonalizaciones.


## 3. Política adaptativa de precisión

Definir tres estados.

### Estado FAST

```text
matvec/preconditioner: BF16 o FP16
GEMM: Tensor Core, acumulación FP32
Arnoldi: FP32
Hessenberg: FP64
residual externo: FP64 cada ciclo
```


### Estado GUARDED

Activar si:

$$
\frac{\|r_{j+1}\|}{\|r_j\|}>0.95
$$

durante varias iteraciones, o si se pierde ortogonalidad.

Cambios:

```text
matvec: FP32
dot products: FP64
reorthogonalization: FP64
residual: FP64 cada iteración
Woodbury: refactorización FP64
```


### Estado RECOVERY

Activar ante NaN, overflow, pérdida fuerte de ortogonalidad o aumento sostenido del residual:

```text
reiniciar FGMRES
reconstruir preconditioner
subir todo el inner solve a FP32/FP64
reducir step size de Cayley
usar solve reducido directo
```

Después de una recuperación exitosa, volver a `GUARDED`, no directamente a `FAST`.

## 4. Precisión por bucket

Una mejora más avanzada que asignar una precisión única a todo el operador es separar los coeficientes por magnitud:

$$
A=A^{(16)}+A^{(32)}+A^{(64)},
$$

donde cada bucket contiene entradas cuya magnitud y sensibilidad justifican una precisión distinta.

Por ejemplo:

- entradas dominantes: FP32;
- entradas intermedias: BF16/FP16;
- correcciones pequeñas pero espectralmente importantes: FP64.

La literatura reciente describe precondicionadores aproximados sparse con buckets de precisión variable dentro de GMRES-IR.[^8_2]

Para el operador matrix-free de V911, adaptar esta idea:

```text
apply_A_low(x):
    y = A_majority_low(x)
    y += A_sensitive_high(x)
```

No asignar precisión solo por magnitud. Un coeficiente pequeño puede ser importante si está asociado a un modo casi nulo. Combinar:

$$
\text{score}_{ij}
=
|a_{ij}|
\cdot
\text{sensitivity}_{ij}.
$$

La sensibilidad puede aproximarse por:

- contribución a Ritz vectors;
- energía por columna;
- influencia en $S$ de Woodbury;
- error observado en el residual.


## 5. Tensor Cores: uso correcto

Usar Tensor Cores para productos de bloques:

$$
C_{\mathrm{FP32}}
=
A_{\mathrm{FP16/BF16}}
B_{\mathrm{FP16/BF16}}.
$$

El formato de almacenamiento no tiene que coincidir con el formato de acumulación. cuBLAS documenta modos mixtos que utilizan Tensor Cores cuando son compatibles con las precisiones solicitadas.[^8_3]

La ruta recomendada:

```text
load BF16/FP16
dequantize/scale
Tensor Core MMA
accumulate FP32
cast result FP32
correct selected entries in FP64
```

No usar Tensor Cores para:

- residual final;
- norma final;
- solución de $S$ mal condicionado;
- Givens si el ciclo está cerca de convergencia;
- actualización externa de $x$.


## 6. Escalado y redondeo adaptativo

FP16 tiene poco rango dinámico; BF16 tiene mayor rango pero menor significando. Implementar escalado por bloque:

$$
\tilde{x}_b=\frac{x_b}{s_b},
\qquad
s_b=2^{\left\lceil \log_2(\|x_b\|_\infty)\right\rceil}.
$$

Usar escalas potencia de dos para evitar errores adicionales de redondeo.

Mantener:

```text
scale_A
scale_x
scale_output
overflow_counter
underflow_counter
```

Si aparecen Inf/NaN:

1. reducir escala;
2. repetir el kernel;
3. promocionar a FP32;
4. marcar el ciclo como inestable.

La estrategia publicada para Tensor Cores utiliza scaling y auto-adaptive rounding precisamente para evitar overflow.[^8_1]

## 7. Stochastic rounding

El redondeo estocástico puede reducir sesgos acumulativos al almacenar bases o aplicar correcciones en baja precisión. Es una opción experimental útil cuando:

- se repiten miles de iteraciones;
- los valores están cerca del umbral de resolución;
- el estancamiento es por acumulación sistemática de error;
- el hardware o kernel permite stochastic rounding eficiente.

Pero no debe aplicarse a ciegas:

- dificulta reproducibilidad bit a bit;
- añade coste;
- puede complicar debugging;
- no arregla un mal condicionamiento;
- debe usar una semilla controlada en benchmarks.

Recomendación:

```text
producción determinista: round-to-nearest
modo investigación: stochastic rounding opcional
```


## 8. Arnoldi y reinicios fiables

GMRES mixto puede mantener precisión alta si se reinicia después de una mejora de precisión. Estudios recientes sobre GMRES mixto reportan que el residual y la actualización pueden mantenerse en doble precisión mientras el trabajo interno usa precisión menor, pero el reinicio es importante para evitar la acumulación de errores.[^8_4]

Para V911:

- usar FGMRES($m$) con $m=20$–$60$;
- cerrar cada ciclo con residual FP64;
- reiniciar si el backward error no mejora;
- no confiar únicamente en el residual estimado de Hessenberg;
- conservar el subespacio reciclado solo si se valida.

Un ciclo puede seguir:

```text
residual FP64
↓
FGMRES low/mixed precision
↓
least-squares FP64
↓
update x FP64
↓
residual true FP64
↓
accept/reject cycle
```


## 9. Acceptance test del ciclo

No aplicar toda corrección automáticamente. Calcular:

$$
\eta_{\mathrm{old}}
=
\frac{\|r_k\|}{\|A\|\|x_k\|+\|b\|},
$$

$$
\eta_{\mathrm{new}}
=
\frac{\|r_k-A\delta_k\|}
{\|A\|\|x_k+\delta_k\|+\|b\|}.
$$

Aceptar si:

$$
\eta_{\mathrm{new}}<\gamma \eta_{\mathrm{old}},
$$

con $\gamma$ configurable, por ejemplo $0.9$.

Si no se cumple:

- no descartar necesariamente la dirección;
- reintentar con mayor precisión;
- reprecisar el precondicionador;
- reducir el tamaño de la retracción;
- reiniciar la base Krylov.

Esta aceptación/rechazo es especialmente valiosa dentro de Newton-Krylov y Cayley, donde una corrección lineal inexacta puede ser adecuada, pero una corrección contaminada puede romper la geometría.

## 10. Refinamiento de la geometría Stiefel

La baja precisión no solo afecta el sistema lineal. También afecta:

$$
Y^\top Y-I.
$$

Después de obtener la actualización de Cayley:

$$
Y=
\operatorname{Cayley}(X,Z),
$$

calcular el Gram en FP64:

$$
G=Y^\top Y.
$$

Si:

$$
\|G-I\|_F>\tau_{\mathrm{orth}},
$$

aplicar una corrección:

- reortogonalización polar;
- Cholesky-QR;
- Newton–Schulz sobre $G^{-1/2}$;
- recomputar Cayley en precisión superior.

No realizar automáticamente QR FP64 tras cada paso, porque puede recuperar la estabilidad a costa de eliminar la ganancia. Usarlo como fallback adaptativo.

## 11. Woodbury y refinamiento interno

Para el sistema reducido:

$$
S=I+V^\top P^{-1}U,
$$

separar:

```text
formación de S: FP64 accumulation
factorización S: FP64 pivoted QR
aplicación S⁻¹: FP64 o FP32 corregida
```

Si $S$ tiene buena condición, puede usarse un solve FP32 con refinamiento:

$$
S\delta^{(32)}=r^{(32)},
$$

$$
r^{(64)}=b-S\delta^{(64)},
$$

$$
\delta^{(64)}\leftarrow\delta^{(64)}+\Delta\delta.
$$

Como $S$ es pequeño, la opción más segura es FP64 directo; la ganancia debe buscarse en el operador grande, no en este solve.

## 12. Precisión adaptativa del precondicionador

El precondicionador no tiene que usar la misma precisión que el matvec.

Un esquema útil:


| Componente | FAST | GUARDED | RECOVERY |
| :-- | :-- | :-- | :-- |
| $P^{-1}$ | BF16/FP16 | FP32 | FP64/solve directo |
| $U,V$ | BF16 | FP32 | FP64 |
| $S$ | FP64 | FP64 | FP64 + rebuild |
| $V^\top P^{-1}U$ | FP32 accum. | FP64 | FP64 |
| FGMRES | FP32 | FP32/64 | FP64 |
| residual | FP64 por ciclo | FP64 cada iteración | FP64 |

Esto es superior a cambiar toda la aplicación de precisión simultáneamente.

## 13. Cinco precisiones ampliadas con FP8

Una posible arquitectura futura:

$$
\begin{aligned}
u_{\mathrm{storage}}&=\mathrm{FP8/BF16},\\
u_p&=\mathrm{BF16/FP16},\\
u_g&=\mathrm{FP32},\\
u_H&=\mathrm{FP64},\\
u_r&=\mathrm{FP64}.
\end{aligned}
$$

Pero FP8 debe limitarse inicialmente a:

- almacenamiento de precondicionador;
- factores de bajo rango no críticos;
- activaciones o workspace con escalado;
- aproximaciones que sean fácilmente reconstruibles.

No usar FP8 para:

- residual;
- Hessenberg;
- bases ortogonales sin corrección;
- $S$ de Woodbury;
- actualización $x$.


## 14. CPU frente a GPU

### CPU AVX2/AVX-512

Priorizar:

- FP32 vectorizado;
- BF16 si el procesador soporta instrucciones nativas;
- blocking/cache;
- almacenamiento comprimido;
- residual FP64;
- OpenMP/SIMD.

No asumir que FP16 es más rápido: la conversión y falta de unidades nativas pueden anular la ganancia.

### GPU Tensor Cores/Matrix Cores

Priorizar:

- GEMM bloqueado;
- FGMRES por bloques;
- precondicionamiento batched;
- bases residentes;
- reducción de sincronizaciones;
- CUDA/HIP Graphs;
- FP16/BF16 con acumulación FP32.

cuBLAS y cuSOLVER ya proporcionan rutas de precisión mixta y refinamiento; conviene reutilizarlas en el solve reducido antes de escribir kernels manuales.[^8_5][^8_3]

## 15. Métrica científica correcta

No optimizar solo:

$$
\text{FLOP/s}.
$$

Optimizar:

$$
\text{tiempo hasta convergencia válida}
=
\text{tiempo/ciclo}
\times
\text{número de ciclos}
+
\text{fallbacks}.
$$

La métrica de aceptación debe combinar:

$$
\eta_{\mathrm{backward}}
\leq \tau_{\mathrm{lin}},
$$

$$
\|Y^\top Y-I\|_F
\leq \tau_{\mathrm{orth}},
$$

$$
\frac{\|x_{\mathrm{mixed}}-x_{\mathrm{ref}}\|}
{\|x_{\mathrm{ref}}\|}
\leq \tau_x.
$$

Un método que sea $3\times$ más rápido por iteración pero necesite $10\times$ más iteraciones no es una mejora.

## 16. Benchmark experimental

Usar matrices sintéticas con:

- $\kappa(A)$ conocida;
- espectro clusterizado;
- modos casi nulos;
- rango bajo controlado;
- no simetría;
- escala dinámica amplia.

Y casos reales:

- sistemas de la retracción Cayley;
- Woodbury con $r=8,32,128$;
- bloques Krylov;
- distintos $K$;
- distintas tolerancias geométricas.

Comparar:

1. FP64 completo.
2. FP32 completo.
3. FP16/FP32 fijo.
4. BF16/FP32 fijo.
5. GMRES-IR.
6. cinco precisiones.
7. cinco precisiones + precisión por bucket.
8. cinco precisiones + reinicio fiable.
9. cinco precisiones + stochastic rounding experimental.

Registrar:

- ciclos externos;
- iteraciones internas;
- promociones;
- reortogonalizaciones;
- fallbacks;
- overflow/underflow;
- $\kappa(S)$;
- backward error;
- ortogonalidad;
- uso de Tensor Cores;
- memoria;
- energía.


## 17. Implementación mínima

La API interna debería separar claramente las rutas:

```cpp
struct PrecisionPolicy {
    Precision storage;
    Precision matvec;
    Precision preconditioner;
    Precision arnoldi;
    Precision residual;
    Precision update;
};

struct RefinementState {
    int outer_iteration;
    int stagnation_count;
    double residual_norm;
    double backward_error;
    double orthogonality_error;
    double condition_estimate;
    PrecisionPolicy policy;
};
```

Bucle:

```cpp
while (!converged(state)) {
    compute_true_residual_fp64(x64, r64);

    auto policy = choose_policy(state);

    fgmres_correction(
        r64,
        delta,
        policy,
        preconditioner_cache
    );

    candidate = x64 + cast_fp64(delta);

    compute_true_residual_fp64(candidate, r_candidate);

    if (accept(candidate, r_candidate, state)) {
        x64 = candidate;
        update_state_success(state);
    } else {
        promote_policy(state);
        rebuild_if_needed(state);
    }
}
```


## Recomendación final

La implementación recomendada para V911 es:

$$
\boxed{
\text{FGMRES-IR de cinco precisiones}
+
\text{Tensor Cores}
+
\text{escalado adaptativo}
+
\text{reinicios fiables}
+
\text{Woodbury FP64 reducido}
}
$$

Orden de prioridad:

1. añadir residual verdadero y backward error FP64;
2. pasar el inner solve a FP32;
3. añadir FP16/BF16 con acumulación FP32;
4. mantener Hessenberg, Woodbury reducido y actualización en FP64;
5. implementar promoción automática;
6. añadir reortogonalización y reinicio fiable;
7. estudiar buckets de precisión para el precondicionador;
8. reservar FP8 y stochastic rounding para una fase experimental.

La idea central es que la precisión no sea un parámetro fijo de compilación, sino una variable de control del algoritmo. Los Tensor Cores aportan rendimiento; el refinamiento externo, la evaluación de backward error y la promoción adaptativa aportan confiabilidad científica.

<span style="display:none">[^8_10][^8_11][^8_12][^8_13][^8_14][^8_15][^8_6][^8_7][^8_8][^8_9]</span>

<div align="center">⁂</div>

[^8_1]: https://royalsocietypublishing.org/doi/10.1098/rspa.2020.0110

[^8_2]: https://arxiv.org/html/2307.03914v1

[^8_3]: https://docs.nvidia.com/cuda/cublas/

[^8_4]: https://www.alphaxiv.org/@jack-dongarra

[^8_5]: https://docs.nvidia.com/cuda/cusolver/index.html

[^8_6]: https://developer.nvidia.com/cublas

[^8_7]: https://developer.nvidia.com/blog/unlocking-tensor-core-performance-with-floating-point-emulation-in-cublas/

[^8_8]: https://www.olcf.ornl.gov/wp-content/uploads/2019/11/ORNL_Tensor_Core_Training_Aug2019.pdf

[^8_9]: https://www.exascaleproject.org/wp-content/uploads/2022/06/2022_ECP_BoF_1.pdf

[^8_10]: https://www.fz-juelich.de/en/jsc/news/events/seminars/msa-seminar/2020-06-30-tensor-cores-wagner-demouth/@@download/file

[^8_11]: https://arxiv.org/html/2506.18408

[^8_12]: https://docs.nvidia.com/cuda/pdf/CUBLAS_Library.pdf

[^8_13]: https://arxiv.org/pdf/1803.04014v1.pdf

[^8_14]: https://scispace.com/pdf/a-survey-of-numerical-methods-utilizing-mixed-precision-kto72ulj6e.pdf

[^8_15]: https://link.springer.com/content/pdf/10.1007/s00366-025-02187-z.pdf?error=cookies_not_supported\&code=da42e0c6-1703-4bd3-94ca-82feb934a32f


---

# 5. Martingalas Conformes en Detección (CliffordNet) evalua mejoras y soluciones cientificas SOTA

Brecha (V911): V910 implementó el detector estadístico CUSUM + EWMA. Sin embargo, los umbrales de alarma (1e−101e^{-10}1e−10) son heurísticos, vulnerables a falsos positivos en regímenes transitorios y fluctuaciones de gradiente de alto momentum.
Solución Asintótica Pendiente: Sustituir la heurística de CUSUM por Bayesian Online Change Point Detection (BOCPD) y acotarlo mediante Martingalas Conformes, estableciendo umbrales matemáticamente certificados por el teorema de probabilidad.

La sustitución correcta no es “BOCPD en lugar de CUSUM” de forma aislada. Para CliffordNet/V911 conviene construir un **detector híbrido BOCPD–conformal e-process**, donde:

- BOCPD estima el estado latente y la probabilidad de cambio;
- los residuos conformales convierten la evidencia en $p$-values calibrados;
- una martingala o e-process proporciona control anytime-valid de falsas alarmas;
- un filtro de régimen evita alarmas durante transitorios benignos;
- CUSUM/EWMA queda como capa de respuesta rápida, no como fuente del umbral estadístico.

Las martingalas conformes permiten usar el umbral $1/\alpha$ con una garantía de falsas alarmas mediante la desigualdad de Ville:

$$
\Pr_{H_0}\!\left(\sup_t M_t\geq\frac1\alpha\right)\leq\alpha.
$$

Esto es muy distinto de fijar heurísticamente $10^{-10}$.[^9_1][^9_2]

## 1. Qué debe detectar CliffordNet

Antes de elegir el detector, separar cuatro eventos:

1. cambio real de distribución;
2. transición normal entre regímenes;
3. fluctuación temporal por momentum;
4. inestabilidad o degradación del optimizador.

El detector no debería recibir directamente el gradiente crudo $g_t$, porque con momentum:

$$
v_t=\beta v_{t-1}+(1-\beta)g_t
$$

introduce autocorrelación y puede parecer un cambio persistente aunque solo sea una respuesta transitoria.

Usar un vector de observación más informativo:

$$
z_t=
\begin{bmatrix}
\log(1+\|g_t\|_2)\\
\log(1+\|v_t\|_2)\\
\cos(g_t,v_t)\\
\log(1+\|\Delta g_t\|_2)\\
\log(1+\|\Delta\theta_t\|_2)\\
\text{loss}_t\\
\text{residual}_t\\
\text{orthogonality error}_t
\end{bmatrix}.
$$

Luego reducir o proyectar:

$$
s_t=\phi(z_t),
$$

donde $s_t$ puede ser:

- residual normalizado;
- score de un modelo predictivo;
- distancia de Mahalanobis robusta;
- error de predicción;
- log-likelihood ratio;
- score neuronal de CliffordNet.

El detector debe operar sobre $s_t$, no sobre cada componente sin calibración.

## 2. BOCPD: capa de inferencia de régimen

BOCPD mantiene una distribución sobre la longitud del régimen actual:

$$
r_t\in\{0,1,\ldots,t\}.
$$

La actualización estándar es:

$$
p(r_t,x_{1:t})
=
\sum_{r_{t-1}}
p(r_t\mid r_{t-1})
p(x_t\mid r_{t-1},x_{1:t-1})
p(r_{t-1},x_{1:t-1}).
$$

Con hazard $H(r)$:

$$
p(r_t=0\mid r_{t-1}=r)=H(r),
$$

$$
p(r_t=r+1\mid r_{t-1}=r)=1-H(r).
$$

La probabilidad instantánea de cambio es:

$$
q_t=P(r_t=0\mid x_{1:t}).
$$

BOCPD es útil para responder:

- ¿en qué régimen estoy?
- ¿cuánto lleva el régimen actual?
- ¿el cambio es probable o solo una anomalía aislada?
- ¿debo reiniciar la calibración?

Pero $q_t$ no es, por sí solo, una garantía frecuentista de falsas alarmas. Depende del modelo predictivo y del hazard. BOCPD debe ser la capa de inferencia, no el certificado estadístico.

## 3. Martingala conforme: capa de garantía

Construir un score no conformal de cada observación:

$$
a_t=
\left|s_t-\widehat{\mu}_{t-1}\right|/
\widehat{\sigma}_{t-1},
$$

o una distancia multivariada robusta:

$$
a_t
=
\sqrt{
(z_t-\widehat\mu)^\top
(\widehat\Sigma+\lambda I)^{-1}
(z_t-\widehat\mu)
}.
$$

Obtener un $p$-value conformal prequential:

$$
p_t=
\frac{
1+\sum_{i\in\mathcal C_t}\mathbf 1\{a_i\geq a_t\}
}{
|\mathcal C_t|+1
}.
$$

Bajo exchangeability, estos $p_t$ son uniformes en el sentido requerido por la calibración conformal. Se puede construir una martingala de apuestas:

$$
M_t=M_{t-1}g_t(p_t),
$$

con:

$$
\int_0^1 g_t(p)\,dp\leq 1.
$$

Ejemplo de power martingale:

$$
g(p)=\varepsilon p^{\varepsilon-1},
\qquad 0<\varepsilon<1.
$$

Entonces:

$$
M_t=M_0\prod_{i=1}^{t} \varepsilon p_i^{\varepsilon-1}.
$$

Alarmar cuando:

$$
M_t\geq\frac1\alpha.
$$

Para $\alpha=10^{-4}$, el umbral es $10^4$, no $10^{-10}$. La probabilidad de cruzar ese umbral alguna vez bajo el nulo está acotada por $10^{-4}$, siempre que se cumplan las hipótesis de la martingala.[^9_3][^9_4]

## 4. Log-martingala para estabilidad numérica

Nunca multiplicar directamente miles de factores:

$$
M_t=\prod_i g(p_i).
$$

Trabajar con:

$$
\ell_t=\log M_t
=
\ell_{t-1}+\log g_t(p_t).
$$

El umbral se convierte en:

$$
\ell_t\geq\log(1/\alpha).
$$

Pseudocódigo:

```python
logM += log_betting_function(p_t)

if logM >= math.log(1 / alpha):
    alarm = True
```

Para evitar que la martingala caiga irreversiblemente durante largos periodos normales, usar una de estas estrategias:

- martingala reiniciada por bloques;
- mixture martingale;
- cautious betting;
- e-process con restart controlado;
- calibración por régimen.

El problema de que una martingala se aproxime a cero y tarde en recuperarse está documentado; las apuestas “cautious” evitan apostar fuertemente cuando no existe evidencia de cambio.[^9_5]

## 5. Combinación BOCPD–martingala

La combinación recomendada no debe multiplicar sin control dos fuentes de evidencia dependientes. Definir:

$$
E_t^{\mathrm{final}}
=
E_t^{\mathrm{conf}}
\cdot
w(q_t),
$$

donde $E_t^{\mathrm{conf}}$ es un e-process conforme y $w(q_t)$ es un peso de prioridad de BOCPD.

Pero si $w(q_t)$ modifica la martingala sin preservar la propiedad de supermartingala, se pierde la garantía. La opción segura es separar:

### Capa certificada

$$
E_t^{\mathrm{conf}}
$$

genera la alarma formal.

### Capa BOCPD

$$
q_t
$$

controla:

- severidad;
- clasificación de régimen;
- reinicio;
- adaptación;
- política de respuesta.

Regla:

```text
if E_conf >= 1/alpha and q_t >= q_min:
    confirmed_change

if E_conf >= 1/alpha and q_t < q_min:
    statistically unusual but regime-uncertain

if q_t high and E_conf low:
    candidate change, wait for confirmation
```

Así BOCPD reduce falsos positivos operativos sin alterar el certificado de la martingala.

## 6. Régimen transitorio y momentum

La principal fuente de falsos positivos descrita en V911 es el momentum alto. Hay que hacer la secuencia aproximadamente más intercambiable antes de conformalizarla.

### Residualizar momentum

Modelar:

$$
g_t=\rho_t g_{t-1}+\epsilon_t.
$$

Calibrar sobre:

$$
\epsilon_t=g_t-\widehat{\rho}_t g_{t-1}.
$$

Para vectores:

$$
\widehat{\rho}_t
=
\frac{\langle g_t,g_{t-1}\rangle}
{\|g_{t-1}\|_2^2+\lambda}.
$$

Usar el score de $\epsilon_t$, no de $g_t$.

### Score de innovación

Para el estado de momentum:

$$
v_t=\beta v_{t-1}+(1-\beta)g_t,
$$

definir:

$$
e_t=
\frac{
v_t-\widehat{\mathbb E}[v_t\mid v_{t-1}]
}{
\widehat{\operatorname{sd}}(v_t\mid v_{t-1})+\epsilon
}.
$$

Esto distingue una fluctuación esperada por inercia de una innovación anómala.

### Calibración por contexto

Condicionar la no conformidad en:

- magnitud de momentum;
- fase de entrenamiento;
- learning rate;
- norma del gradiente;
- régimen BOCPD;
- batch-size;
- pérdida.

Usar weighted conformal martingales si la distribución de contexto cambia suavemente. Los WCTM están diseñados para monitorizar shifts con control anytime-valid bajo hipótesis de cambio ponderado.[^9_6][^9_1]

## 7. Weighted conformal martingales

Cuando los datos no son perfectamente exchangeables, la martingala estándar puede dejar de ser válida. Para concept drift suave, usar pesos:

$$
w_i(x_t)
\approx
\frac{p_{\mathrm{test}}(x_t)}
{p_{\mathrm{cal}}(x_t)}.
$$

El $p$-value ponderado se construye con:

$$
p_t^{(w)}
=
\frac{
w_t+\sum_i w_i\mathbf 1\{a_i\geq a_t\}
}{
w_t+\sum_i w_i
}.
$$

Después aplicar la apuesta conforme.

Esto requiere:

- soporte común;
- pesos acotados;
- estimación estable de densidades;
- clipping:

$$
w_i\\leftarrow\\min(w_i,w\_{\\max});
$$
- monitorización de effective sample size:

$$
ESS=\\frac{(\\sum_i w_i)^2}{\\sum_i w_i^2}.
$$

Si $ESS$ cae demasiado, no confiar en el certificado; cambiar a una política conservadora o reiniciar calibración.

Los WCTM recientes están orientados precisamente a distinguir desplazamientos benignos de cambios perjudiciales y mantener control anytime-valid bajo hipótesis ponderadas.[^9_1][^9_6]

## 8. Recalibración sin destruir la garantía

Después de detectar un cambio, CliffordNet probablemente necesita adaptarse o recalibrarse. El problema es que introducir los datos post-cambio inmediatamente en el conjunto de calibración puede contaminar la prueba.

Usar tres buffers:

```text
reference_buffer
suspect_buffer
post_change_buffer
```

Flujo:

1. `reference_buffer`: datos aceptados como régimen normal;
2. `suspect_buffer`: observaciones después de evidencia inicial;
3. `post_change_buffer`: datos posteriores a confirmación;
4. recalibrar solo después de una ventana de estabilidad;
5. crear una nueva martingala desde el nuevo punto de reinicio.

Si se reinicia la martingala, el nivel $\alpha$ debe asignarse de forma explícita:

- alpha spending;
- reinicios con e-values;
- test martingale por episodios;
- presupuesto global:

$$
\\sum_j\\alpha_j\\leq\\alpha.
$$

No reiniciar un contador y reutilizar $\alpha$ infinitamente sin justificación. Eso destruiría el control global de falsas alarmas.

## 9. Detector híbrido en tres tiempos

Conviene separar tres escalas temporales:

### Rápida

CUSUM/EWMA sobre innovaciones:

$$
C_t=\max(0,C_{t-1}+s_t-\nu).
$$

Sirve para reaccionar pronto, pero no certifica.

### Intermedia

BOCPD con hazard adaptativo:

$$
q_t=P(r_t=0\mid x_{1:t}).
$$

Sirve para localizar el cambio y estimar duración.

### Lenta

Martingala/e-process conforme:

$$
\log E_t.
$$

Sirve para confirmar con error de tipo I controlado.

Regla operativa:

```text
candidate = fast_cusum or q_t high
confirmed = logE_t >= log(1/alpha)
action = confirmed and regime_policy(q_t, candidate)
```

Esto es mejor que eliminar por completo CUSUM: CUSUM aporta baja latencia; la martingala aporta validez; BOCPD aporta contexto.

## 10. Hazard adaptativo de BOCPD

Un hazard constante:

$$
H(r)=1/\lambda
$$

es fácil, pero poco realista para un optimizador. Usar:

$$
H_t(r)
=
\sigma\left(
a_0+a_1\log(1+r)+a_2\mathrm{momentum}_t
+a_3\mathrm{lr}_t+a_4\mathrm{phase}_t
\right).
$$

Pero no permitir que el hazard sea aprendido libremente con los mismos datos que certifican el cambio. Separar:

- hazard prior definido por validación;
- parámetros adaptativos restringidos;
- o hazard estimado en una ventana independiente.

Para evitar alarmas durante el calentamiento:

$$
H_t(r)=
\begin{cases}
H_{\mathrm{low}}, & t<t_{\mathrm{warmup}},\\
H_{\mathrm{adaptive}}, & t\geq t_{\mathrm{warmup}}.
\end{cases}
$$

También puede usar un hazard de renovación con duración esperada:

$$
\mathbb E[L]=\lambda.
$$

La elección de $\lambda$ debe basarse en la duración esperada de regímenes, no en el umbral de alarma.

## 11. Modelos predictivos dentro de BOCPD

Para scores aproximadamente gaussianos:

$$
s_t\mid r_t,\theta_{r_t}
\sim
\mathcal N(\mu_{r_t},\sigma_{r_t}^2)
$$

usar actualización conjugada Normal–Inverse-Gamma.

Para normas y pérdidas positivas, puede ser mejor:

- Student-$t$;
- Gamma;
- log-normal;
- distribución robusta Huberizada.

Student-$t$ es preferible a Gaussian si los gradientes tienen colas pesadas:

$$
s_t\sim t_\nu(\mu,\sigma).
$$

Para datos multivariados, evitar una covarianza densa en cada run length; usar:

- diagonal robusta;
- low-rank + diagonal;
- shrinkage:

$$
\\widehat\\Sigma\_\\lambda=(1-\\lambda)\\widehat\\Sigma+\\lambda I;
$$
- random projections;
- score escalar aprendido.


## 12. Conformalización de modelos neuronales

CliffordNet puede producir un score $s_t=f_\theta(z_t)$, pero el modelo no debe producir directamente una probabilidad de cambio no calibrada.

Usar:

$$
a_t=
\left|s_t-\widehat s_t\right|
$$

o un score de energía:

$$
a_t=-\log p_\theta(z_t).
$$

Después convertirlo a ranks conformes.

Separar:

```text
model training
calibration stream
monitoring stream
```

Si el detector aprende continuamente con las mismas muestras que usa para calcular p-values, la exchangeability requerida se rompe. Las opciones son:

- prequential split;
- cross-fitting temporal;
- delayed update;
- online calibration con ventana bloqueada;
- weighted conformal bajo drift.


## 13. Dependencia temporal

La garantía clásica de martingala conforme requiere exchangeability o una hipótesis equivalente. Los gradientes de una red son autocorrelacionados; por tanto, no debe anunciarse una garantía exacta sin corregir la dependencia.

Opciones científicas:

### Bloques

Construir scores por bloques:

$$
B_t=(z_{t-\ell+1},\ldots,z_t)
$$

y conformalizar bloques separados por un intervalo de mixing.

### Residuales prewhitened

Usar innovaciones de un AR/State Space Model:

$$
e_t=z_t-\widehat z_t.
$$

### Conformal martingale bajo dependencia débil

Usar garantías aproximadas bajo mixing, martingalas condicionadas o bloques intercambiables.

### e-process robusto

Construir un e-process para una clase nula más amplia que incluya autocorrelación permitida.

La afirmación correcta debe ser una de estas:

- control finito de falsas alarmas bajo exchangeability;
- control condicional bajo un modelo especificado;
- garantía aproximada bajo mixing;
- solo benchmark empírico si no se puede justificar ninguna hipótesis.

No llamar “certificado” a un umbral conformal si el pipeline adaptativo viola la hipótesis nula.

## 14. Control de falsos positivos por alarma y por tiempo

Si se monitorizan muchos canales:

- gradiente;
- pérdida;
- residual;
- ortogonalidad;
- memoria;
- varias capas;

no aplicar $\alpha$ completo a cada martingala.

Opciones:

### E-value combinado

$$
E_t=\sum_j w_j E_t^{(j)},
\qquad
\sum_jw_j=1.
$$

La combinación convexa de e-processes preserva la propiedad requerida si cada componente es válido bajo la misma nula.

### Unión de alarmas

Si se alarman $m$ tests independientes o no, usar Bonferroni:

$$
\alpha_j=\alpha/m.
$$

### FDR online

Si se aceptan múltiples detecciones y no una alarma crítica, aplicar procedimientos online FDR.

La opción práctica para CliffordNet es usar un e-process global con componentes:

```text
E_gradient
E_loss
E_residual
E_geometry
```

y combinarlo con pesos fijos o adaptados de forma predefinida.

## 15. No confundir detección con acción

Separar:

```text
statistical_alarm
regime_change
operational_action
```

Ejemplo:

```text
statistical_alarm:
    E >= 1/alpha

regime_change:
    q_BОCPD >= 0.8 durante k pasos

operational_action:
    E alarm
    and q_BОCPD high
    and loss degradation confirmed
```

Así una anomalía estadística aislada no provoca:

- reset del optimizador;
- reducción de learning rate;
- restauración de checkpoint;
- cambio de arquitectura;
- reinicio de calibración.

Las acciones deben tener histéresis:

$$
\text{enter alert if } E\geq 1/\alpha,
$$

$$
\text{exit alert only if } \log E_t<\ell_{\mathrm{exit}}
\text{ durante } h \text{ pasos}.
$$

## 16. Algoritmo propuesto

```text
initialize reference calibration C
initialize BOCPD run-length posterior R
initialize log_eprocess = 0
initialize CUSUM = 0

for each observation z_t:
    z_t = normalize_context(z_t)
    e_t = innovation_residual(z_t, momentum_state)

    a_t = nonconformity_score(e_t, calibration=C)
    p_t = weighted_prequential_pvalue(a_t, C)

    log_eprocess += log_bet(p_t)

    update BOCPD posterior R with predictive likelihood
    q_t = R[run_length=0]

    CUSUM = max(0, CUSUM + score(e_t) - drift_reference)

    candidate = (CUSUM > c_fast) or (q_t > q_candidate)
    certified = (log_eprocess >= log(1 / alpha))

    if certified:
        if q_t >= q_confirm:
            emit CONFIRMED_CHANGE
        else:
            emit CERTIFIED_ANOMALY

    if certified and q_t >= q_confirm:
        freeze calibration
        move samples to suspect buffer
        start post-change protocol

    if stable_after_change:
        spend alpha budget
        restart e-process
        recalibrate
```


## 17. Umbrales recomendados

En vez de $1e^{-10}$, definir explícitamente:

$$
\alpha_{\mathrm{global}}\in\{10^{-2},10^{-3},10^{-4}\}
$$

según el coste de una falsa alarma.

El umbral de riqueza es:

$$
B=\frac1{\alpha}.
$$

Ejemplos:


| $\alpha$ | Umbral martingala |
| --: | --: |
| $10^{-2}$ | $10^2$ |
| $10^{-3}$ | $10^3$ |
| $10^{-4}$ | $10^4$ |
| $10^{-5}$ | $10^5$ |

Para un sistema que toma acciones destructivas, usar una alarma de dos niveles:

```text
warning: E >= 1/alpha_warning
confirmed: E >= 1/alpha_confirmed
```

Por ejemplo:

$$
\alpha_{\mathrm{warning}}=10^{-2},
\qquad
\alpha_{\mathrm{confirmed}}=10^{-4}.
$$

La alarma warning no cambia el modelo; solo aumenta la vigilancia.

## 18. Evaluación científica

Construir datasets con:

- régimen estacionario;
- rampas de learning rate;
- warm-up;
- momentum alto;
- cambios abruptos;
- cambios graduales;
- drift covariable benigno;
- cambio perjudicial en pérdida;
- outliers aislados;
- autocorrelación;
- dependencia entre capas.

Métricas:

### Detección

- false alarm probability;
- average run length bajo $H_0$;
- detection delay;
- recall;
- precision;
- F1;
- tiempo hasta confirmación.


### Calibración

- cobertura de p-values;
- distribución bajo nulo;
- crossing probability de $E_t$;
- estabilidad por régimen;
- calibration drift.


### Utilidad

- pérdida evitada;
- número de resets;
- coste de recalibración;
- tiempo de recuperación;
- degradación por falsa intervención.

Comparar:

1. CUSUM actual.
2. EWMA actual.
3. BOCPD solo.
4. martingala conforme sola.
5. BOCPD + martingala.
6. weighted conformal martingale.
7. híbrido con residualización de momentum.
8. híbrido con e-value global.

## 19. Límites teóricos que deben documentarse

El sistema debe declarar sus hipótesis:

### Garantía fuerte

Válida si:

- observaciones exchangeables bajo $H_0$;
- calibración no contaminada;
- betting function no anticipa $p_t$;
- no se reusa $\alpha$ sin presupuesto;
- martingala no se modifica con información futura.


### Garantía condicionada

Si hay drift covariable:

- pesos correctamente especificados;
- soporte común;
- ESS suficiente;
- clipping controlado.


### Garantía empírica

Si existe autocorrelación fuerte, adaptación online y dependencia entre scores, reportar solo:

- benchmarks;
- intervalos de confianza;
- simulaciones;
- falsos positivos observados.

La desigualdad de Ville proporciona el control anytime-valid para e-processes/martingalas no negativas, pero solo bajo la condición de que el proceso sea realmente un supermartingale bajo la nula.[^9_7][^9_8]

## Recomendación final

Para CliffordNet/V911 implementaría:

$$
\boxed{
\text{innovaciones de gradiente}
+
\text{BOCPD}
+
\text{weighted conformal e-process}
+
\text{CUSUM rápido}
}
$$

con esta separación:

- **CUSUM/EWMA:** candidato de baja latencia;
- **BOCPD:** probabilidad y duración del nuevo régimen;
- **martingala/e-process:** certificación anytime-valid;
- **hazard:** prior de cambio, no umbral de error;
- **alpha spending:** control entre reinicios;
- **recalibración:** solo después de una fase de confirmación.

La sustitución de $10^{-10}$ por $1/\alpha$ es solo una parte. La mejora científica real consiste en residualizar el momentum, respetar la dependencia temporal, separar detección de acción, controlar los reinicios y no usar la garantía conformal fuera de sus hipótesis. Las martingalas conformes ofrecen un certificado matemático; BOCPD ofrece contexto probabilístico; juntas producen un detector mucho más sólido que cualquiera de las dos por separado.

<span style="display:none">[^9_10][^9_11][^9_12][^9_13][^9_14][^9_15][^9_16][^9_17][^9_18][^9_19][^9_20][^9_21][^9_22][^9_23][^9_24][^9_25][^9_26][^9_27][^9_28][^9_29][^9_9]</span>

<div align="center">⁂</div>

[^9_1]: https://arxiv.org/html/2505.04608v1

[^9_2]: https://www.emergentmind.com/topics/online-conformal-testing

[^9_3]: https://proceedings.mlr.press/v60/volkhonskiy17a/volkhonskiy17a.pdf

[^9_4]: https://www.isibang.ac.in/~statmath/pcm2020/lecture_4.pdf

[^9_5]: https://proceedings.mlr.press/v179/eliades22a/eliades22a.pdf

[^9_6]: https://icml.cc/virtual/2025/poster/45832

[^9_7]: https://www.sciencedirect.com/science/article/pii/S0031320325005011

[^9_8]: https://academic.oup.com/jrsssb/advance-article/doi/10.1093/jrsssb/qkag058/8627076?guestAccessKey=

[^9_9]: https://dspace.lib.cranfield.ac.uk/server/api/core/bitstreams/476b370c-0eae-45d1-9c54-b2ba311e1b1f/content

[^9_10]: https://link.springer.com/content/pdf/10.1007/s11280-023-01181-z.pdf?error=cookies_not_supported\&code=0f621f68-b18a-46c7-9a99-3283859bc448

[^9_11]: https://www.ijcai.org/proceedings/2019/0340.pdf

[^9_12]: https://proceedings.mlr.press/v119/alami20a/alami20a-supp.pdf

[^9_13]: https://proceedings.mlr.press/v124/agudelo-espana20a/agudelo-espana20a.pdf

[^9_14]: https://arxiv.org/html/2509.02844v4

[^9_15]: https://aclanthology.org/D15-1184.pdf

[^9_16]: https://lips.cs.princeton.edu/pdfs/adams2007changepoint.pdf

[^9_17]: https://www.alrw.net/articles/32.pdf

[^9_18]: https://raw.githubusercontent.com/mlresearch/v266/main/assets/nouretdinov25a/nouretdinov25a.pdf

[^9_19]: https://www.semanticscholar.org/paper/Inductive-Conformal-Martingales-for-Change-Point-Volkhonskiy-Burnaev/a479d6751705520305cff48c8467ca356ea80c53

[^9_20]: http://proceedings.mlr.press/v124/agudelo-espana20a/agudelo-espana20a-supp.pdf

[^9_21]: https://www.arxiv.org/pdf/1905.13168.pdf

[^9_22]: https://ubi29.informatik.uni-siegen.de/usi/pdf/ubi_indin2019.pdf

[^9_23]: https://mlg.eng.cam.ac.uk/pub/pdf/SaaTurRas10.pdf

[^9_24]: https://arxiv.org/pdf/2604.15740v1.pdf

[^9_25]: https://web3.arxiv.org/pdf/2512.04016

[^9_26]: https://docs.frankentui.com/intelligence/change-detection/bocpd

[^9_27]: https://docs.rs/changepoint/latest/src/changepoint/bocpd.rs.html

[^9_28]: https://raw.githubusercontent.com/mlresearch/v267/main/assets/prinster25a/prinster25a.pdf

[^9_29]: https://github.com/OliverHennhoefer/nonconform


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La mejora SOTA para CliffordNet ya no debería centrarse únicamente en BOCPD + martingala conforme estándar. La dirección más avanzada es un **detector conformal e-process/e-detector optimizado para latencia**, combinado con BOCPD para inferencia de régimen y con WCTM para drift covariable. Trabajos recientes muestran que algunas martingalas conformes convencionales pueden ser válidas pero subóptimas en retardo, mientras que construcciones nuevas alcanzan retardos de orden $\Theta(\log T)$ o $\Theta(\log \mathrm{ARL})$ bajo sus hipótesis.[^10_1]

## 1. Cambiar el objetivo estadístico

Hay que definir qué significa “cambio”:

$$
H_0:\mathcal D_t \text{ sigue siendo compatible con el régimen normal}
$$

frente a:

$$
H_1:\mathcal D_t \text{ contiene una modificación relevante}.
$$

Para CliffordNet, conviene dividir $H_1$ en tres alternativas:


| Hipótesis | Significado | Acción |
| :-- | :-- | :-- |
| $H_{1,\mathrm{cov}}$ | Cambió $X$, pero el modelo sigue funcionando | Adaptar calibración |
| $H_{1,\mathrm{concept}}$ | Cambió $Y\mid X$ o la dinámica del gradiente | Reducir confianza/reentrenar |
| $H_{1,\mathrm{out}}$ | Observación fuera del soporte | Congelar o activar fallback |

Esta separación es central en WCTM: permite distinguir un drift covariable benigno de un cambio conceptual perjudicial o de una entrada fuera de soporte.[^10_2][^10_3]

## 2. Arquitectura estadística recomendada

Usar cuatro capas:

```text
1. Residualización temporal y de momentum
2. BOCPD para run length y probabilidad de cambio
3. WCTM/e-process para evidencia anytime-valid
4. política operativa con confirmación e histéresis
```

La salida final no debe ser una única probabilidad, sino:

```text
p_change_bocpd
evidence_log
change_type
confidence
recommended_action
```

Ejemplo:

```json
{
  "bocpd_probability": 0.87,
  "log_evidence": 11.4,
  "change_type": "concept_shift",
  "statistical_status": "confirmed",
  "action": "reduce_step_and_recalibrate"
}
```


## 3. Por qué la martingala estándar puede ser insuficiente

Una martingala conforme clásica puede satisfacer:

$$
\Pr_{H_0}\left(\sup_t E_t\geq\frac1\alpha\right)\leq\alpha,
$$

pero tener mala potencia o gran delay. El trabajo más reciente sobre detección con martingalas conformes analiza precisamente esta brecha: algunos métodos existentes pueden sufrir retrasos de orden $\Omega(T)$ o $\Omega(\sqrt{\mathrm{ARL}})$, mientras que construcciones e-process/e-detector más nuevas alcanzan escalas logarítmicas bajo modelos no paramétricos.[^10_1]

Por ello, para V911 hay que optimizar dos objetivos distintos:

$$
\text{validez}
\neq
\text{potencia}
\neq
\text{baja latencia}.
$$

La evaluación debe reportar ambos:

- probabilidad de falsa alarma;
- retardo de detección.


## 4. E-process frente a p-value martingale

Una p-value martingale transforma:

$$
p_t\mapsto g(p_t).
$$

Un e-process construye directamente evidencia no negativa con esperanza condicional menor o igual a uno:

$$
\mathbb E_{H_0}[E_t\mid\mathcal F_{t-1}]
\leq E_{t-1}.
$$

Ventajas de e-process:

- se combinan más naturalmente entre tiempos;
- son compatibles con Ville;
- permiten mezclar distintas hipótesis;
- pueden adaptarse a familias alternativas;
- evitan parte del coste de corrección por multiplicidad.

La literatura reciente sobre e-values destaca que pueden combinarse a través del tiempo mediante álgebra de evidencia, mientras que los p-values suelen requerir ajustes por tests repetidos.[^10_4]

Para CliffordNet:

```text
E_gradient
E_loss
E_residual
E_geometry
E_support
```

pueden combinarse como:

$$
E_t=\sum_{j=1}^{m}w_jE_{t,j},
\qquad
w_j\geq0,\quad \sum_jw_j=1.
$$

Si cada $E_{t,j}$ es válido bajo $H_0$, la combinación convexa conserva la propiedad de e-process.

## 5. Detector de cambio óptimo por mixtures

Una alternativa más potente que una única power martingale es mezclar apuestas:

$$
E_t
=
\int_{\Theta}
E_t(\theta)\,\pi(d\theta),
$$

donde $\theta$ representa:

- magnitud del cambio;
- dirección;
- escala temporal;
- nivel de cola;
- tasa de drift.

En la práctica:

$$
E_t=\sum_{k=1}^{K}w_k E_t^{(\theta_k)}.
$$

Usar una rejilla:

```text
epsilon ∈ {0.01, 0.05, 0.1, 0.25, 0.5}
window ∈ {8, 32, 128, 512}
scale ∈ {small, medium, large}
```

Esto mejora la potencia frente a cambios de duración desconocida, aunque incrementa cálculo y exige combinar de forma válida.

## 6. WCTM para el drift del optimizador

CliffordNet tiene covariables que cambian intencionadamente:

- learning rate;
- batch size;
- momentum;
- warm-up;
- regularización;
- arquitectura activa;
- distribución de datos;
- norma del gradiente.

Aplicar una martingala estándar puede alarmar por cambios benignos. WCTM corrige los p-values conformes usando pesos de importancia:

$$
w(x)
\approx
\frac{p_{\mathrm{current}}(x)}
{p_{\mathrm{reference}}(x)}.
$$

El p-value ponderado:

$$
p_t^w=
\frac{
w_t+\sum_{i}w_i\,\mathbf 1\{a_i\geq a_t\}
}{
w_t+\sum_iw_i
}
$$

permite dar más peso a ejemplos de referencia parecidos al contexto actual.

Requisitos operativos:

- estimar o aproximar $w(x)$;
- recortar pesos:

$$
w\\leftarrow \\min(w,w\_{\\max});
$$
- vigilar:

$$
ESS=\\frac{(\\sum_iw_i)^2}{\\sum_iw_i^2};
$$
- congelar adaptación si $ESS$ cae bajo un umbral.

Si la distribución actual sale del soporte de referencia, no intentar adaptar indefinidamente: clasificar como `out_of_support`.

## 7. Dependencia temporal: no usar conformal IID directamente

Los gradientes tienen dependencia fuerte:

$$
g_t\not\perp g_{t-1}.
$$

Además, la actualización del detector puede depender de observaciones pasadas. El pipeline debe usar una de estas estrategias.

### Innovaciones

Predecir el score:

$$
\widehat s_t=f(s_{t-1:t-\ell},c_t)
$$

y conformalizar:

$$
a_t=|s_t-\widehat s_t|.
$$

### Bloques

Formar bloques:

$$
B_j=(z_{jL},\ldots,z_{jL+L-1})
$$

y aleatorizar o calibrar a nivel de bloque. Las técnicas de block conformal están diseñadas para series no intercambiables cuando bloques completos pueden aproximarse como intercambiables.[^10_5]

### Guard bands

Separar bloques de entrenamiento, calibración y vigilancia con una banda de exclusión:

```text
train | guard | calibration | guard | test
```

Esto evita que información temporalmente cercana contamine la calibración. Las variantes recientes de inferencia conformal temporal usan cross-fitting por bloques y guard bands precisamente para tratar dependencia.[^10_6]

### Garantía degradada explícita

Si solo se puede asumir $\beta$-mixing, reportar el margen de degradación teórico o empírico. No anunciar validez IID exacta.

## 8. Residualización avanzada de momentum

Usar un estado de innovación vectorial:

$$
h_t=
\begin{bmatrix}
g_t\\
v_t\\
\Delta g_t\\
\Delta v_t
\end{bmatrix}.
$$

Predecir:

$$
\widehat h_t=F_\theta(h_{t-1},\mathrm{lr}_t,\beta_t,\mathrm{phase}_t).
$$

El score:

$$
a_t=
\left\|
W_t(h_t-\widehat h_t)
\right\|_2.
$$

El peso $W_t$ puede ser:

$$
W_t=(\widehat\Sigma_t+\lambda I)^{-1/2}.
$$

Para evitar que una única magnitud domine:

- robust scaling;
- Huber loss;
- clipping por percentiles;
- whitening diagonal;
- low-rank covariance.

El detector debe usar cambios en la innovación, no el movimiento absoluto producido por el momentum esperado.

## 9. BOCPD con modelos robustos

BOCPD puede funcionar mal si el predictive model es gaussiano y los scores tienen colas pesadas. Usar:

- Student-$t$ predictivo;
- escala robusta;
- modelo log-normal para normas;
- hazard dependiente del contexto;
- truncamiento de run length.

La actualización con run-length completo cuesta $O(t)$. Para producción:

- truncar a $R_{\max}$;
- mantener top-$K$ hipótesis;
- podar masa posterior pequeña;
- usar particle BOCPD si el modelo es no conjugado;
- aproximar con variational filtering.

Si:

$$
P(r_t=r)\lt \epsilon_{\mathrm{prune}},
$$

eliminar ese estado y renormalizar.

## 10. BOCPD no debe certificar por sí solo

$q_t=P(r_t=0\mid x_{1:t})$ depende de:

- likelihood;
- prior;
- hazard;
- modelo de observación;
- truncamiento;
- adaptación.

Por tanto, usarlo como:

```text
context_score
```

no como garantía de falsa alarma.

Regla segura:

```text
BOCPD high + e-process low:
    candidate change, no certified alarm

BOCPD low + e-process high:
    certified anomaly, uncertain regime

BOCPD high + e-process high:
    confirmed change
```


## 11. Control de múltiples canales

Si se monitorizan muchos canales $j$, una alarma de cualquiera aumenta el error global. Usar una combinación de e-values:

$$
E_t^{\mathrm{global}}=\sum_j w_jE_{t,j}.
$$

Para canales estructurados, usar pesos aprendidos en una etapa separada, o pesos fijos basados en coste:

$$
w_j\propto \text{impacto}_j.
$$

No escoger $w_j$ mirando la misma secuencia de test sin corrección.

Para múltiples acciones independientes, puede ser preferible online FDR. Trabajos recientes muestran procedimientos como e-LOND capaces de controlar FDR bajo dependencia desconocida, incluso cuando la calibración compartida evoluciona.[^10_7]

## 12. Optimización del retardo

El detector debe elegir la evidencia según el cambio esperado.

Para cambio rápido y grande:

```text
ventanas cortas
power apuestas agresivas
CUSUM candidate
```

Para cambio pequeño y persistente:

```text
mixture e-process
ventanas largas
Student-t robusto
BOCPD con hazard bajo
```

Para cambios desconocidos:

```text
mezcla de escalas
mezcla de apuestas
```

La teoría reciente de e-detectors muestra que el umbral natural para controlar ARL es:

$$
\log(1/\alpha),
$$

y que los detectores bien construidos pueden acercarse a límites de retardo logarítmicos.[^10_8][^10_1]

## 13. Política de reinicio correcta

Nunca hacer:

```python
if alarm:
    logE = 0
    alpha = alpha_global
```

en cada alarma indefinidamente.

Usar presupuesto:

$$
\alpha_j=\frac{6\alpha}{\pi^2(j+1)^2},
$$

de modo que:

$$
\sum_{j=0}^{\infty}\alpha_j=\alpha.
$$

En el episodio $j$, el umbral es:

$$
\log(1/\alpha_j).
$$

Alternativamente:

- usar e-process continuo sin reinicio;
- usar un e-detector que se reinicia solo tras aceptación formal;
- reservar un presupuesto por fase de entrenamiento;
- separar `warmup`, `training`, `deployment`.


## 14. Clasificar el cambio

Para decidir la acción, mantener varios e-processes:

$$
E_X: \text{cambio en covariables},
$$

$$
E_Y: \text{cambio en residual/objetivo},
$$

$$
E_{\mathrm{support}}: \text{fuera de soporte},
$$

$$
E_{\mathrm{geometry}}: \text{degradación geométrica}.
$$

Clasificación:

```text
E_X high, E_Y low:
    covariate drift benigno

E_X high, E_Y high:
    posible concept/performance shift

E_support high:
    out-of-support

E_geometry high:
    inestabilidad numérica/optimización
```

Esto es más útil que una alarma binaria.

## 15. Implementación recomendada

```python
class OnlineDetector:
    def __init__(self, alpha, calibration, max_run_length):
        self.alpha = alpha
        self.log_e = 0.0
        self.run_length = init_bocpd(max_run_length)
        self.calibration = calibration
        self.episode = 0

    def update(self, observation, context):
        innovation = self.residualize(observation, context)

        score = self.nonconformity(innovation)
        weights = self.importance_weights(context)

        p = weighted_prequential_pvalue(
            score, self.calibration, weights
        )

        self.log_e += log_betting_mixture(p)

        self.run_length = bocpd_update(
            self.run_length,
            innovation,
            context
        )

        q_change = self.run_length[^10_0]
        certified = self.log_e >= math.log(1 / self.alpha)

        return {
            "p_value": p,
            "log_evidence": self.log_e,
            "bocpd_change_probability": q_change,
            "certified": certified,
        }
```

Para una versión production-grade añadir:

- buffers por régimen;
- `ESS`;
- detección de NaN;
- budgets de $\alpha$;
- cross-fitting temporal;
- métricas de delay;
- fallback de CUSUM;
- clasificación causal/operativa.


## 16. Plan experimental

Comparar las siguientes configuraciones:


| Método | Validez | Latencia | Adaptación |
| :-- | :-- | --: | :-- |
| CUSUM | Dependiente del modelo | Muy baja | Baja |
| EWMA | Heurística/model-based | Baja | Baja |
| BOCPD | Bayesiana/model-based | Media | Media |
| CTM estándar | Anytime bajo exchangeability | Variable | Baja |
| WCTM | Drift covariable | Media | Alta |
| e-detector optimizado | Anytime/model-free según hipótesis | Baja-media | Media |
| BOCPD + WCTM + e-detector | Híbrida | Media | Alta |

Escenarios:

- IID;
- AR(1);
- momentum $\beta\in\{0.9,0.99,0.999\}$;
- cambios abruptos;
- ramps;
- drift covariable;
- concept shift;
- out-of-support;
- varios canales;
- reinicios;
- calibración compartida.

Métricas:

$$
\mathrm{PFA},
\qquad
\mathrm{ARL}_0,
\qquad
\mathrm{EDD},
\qquad
\mathrm{WADD},
\qquad
\mathrm{FDR},
\qquad
\mathrm{ESS}.
$$

No basta con medir AUC offline: el problema es secuencial y la métrica clave es el retardo bajo una restricción de falsa alarma.

## 17. Recomendación final

La implementación SOTA para CliffordNet/V911 debería ser:

$$
\boxed{
\text{residualización de momentum}
+
\text{BOCPD robusto}
+
\text{WCTM}
+
\text{mixture e-detector}
+
\text{alpha spending}
}
$$

Orden recomendado:

1. reemplazar el umbral fijo por un e-process en logaritmos;
2. residualizar momentum y learning-rate schedule;
3. añadir BOCPD con likelihood Student-$t$;
4. usar WCTM para covariate drift;
5. separar `candidate`, `certified` y `action`;
6. controlar reinicios con alpha spending;
7. combinar canales mediante e-values;
8. migrar de martingala estándar a e-detectors optimizados para delay;
9. validar bajo dependencia temporal y reportar qué garantías se mantienen.

La mejora conceptual decisiva es separar **validez**, **detección rápida** y **diagnóstico**. BOCPD identifica el régimen; WCTM permite adaptarse a drift; los e-processes certifican evidencia secuencial; y CUSUM/EWMA conserva su utilidad como detector de baja latencia. Esta arquitectura es significativamente más rigurosa que sustituir un umbral $10^{-10}$ por otro número fijo.

<span style="display:none">[^10_10][^10_11][^10_12][^10_13][^10_14][^10_15][^10_16][^10_17][^10_18][^10_19][^10_20][^10_21][^10_22][^10_23][^10_24][^10_25][^10_26][^10_27][^10_28][^10_29][^10_30][^10_9]</span>

<div align="center">⁂</div>

[^10_1]: https://arxiv.org/abs/2609.27179

[^10_2]: https://arxiv.org/html/2505.04608v5

[^10_3]: https://www.alphaxiv.org/abs/2505.04608v4

[^10_4]: https://ar5iv.labs.arxiv.org/html/2602.04146

[^10_5]: https://arxiv.org/html/2511.13608v1

[^10_6]: https://www.alphaxiv.org/abs/2606.30500

[^10_7]: https://www.jmlr.org/papers/volume27/25-2123/25-2123.pdf

[^10_8]: https://arxiv.org/html/2203.03532v4

[^10_9]: https://icml.cc/virtual/2026/workshop/54092

[^10_10]: https://icml.cc/virtual/2025/session/50267

[^10_11]: https://papers.nips.cc/paper_files/paper/2025/file/12271b64c483ad8f6192eb6aaa102044-Paper-Conference.pdf

[^10_12]: https://link.springer.com/content/pdf/10.1007/s10845-024-02447-7.pdf?error=cookies_not_supported\&code=48530a05-f37c-40e4-89ac-5c7fecf7a326

[^10_13]: https://par.nsf.gov/servlets/purl/10577275

[^10_14]: http://bioconductor.statistik.tu-dortmund.de/cran/web/packages/RegimeChange/vignettes/bayesian-methods.html

[^10_15]: https://arxiv.org/pdf/2609.27179v1.pdf

[^10_16]: https://unire.unige.it/handle/123456789/12956

[^10_17]: https://arxiv.org/ftp/arxiv/papers/2201/2201.02325.pdf

[^10_18]: https://github.com/hildensia/bayesian_changepoint_detection

[^10_19]: https://wires.onlinelibrary.wiley.com/doi/am-pdf/10.1002/wics.1628

[^10_20]: https://arxiv.org/html/2410.13115v2

[^10_21]: https://arxiv.org/pdf/2604.15740.pdf

[^10_22]: https://arxiv.org/html/2605.30292

[^10_23]: https://www.alphaxiv.org/abs/2602.05272

[^10_24]: https://www.alrw.net/articles/29.pdf

[^10_25]: https://conformalprediction.net/literature.html

[^10_26]: https://www.mdpi.com/1099-4300/28/5/566

[^10_27]: https://openreview.net/pdf?id=EZLsxOgcDg

[^10_28]: https://arxiv.org/pdf/2604.15740v1.pdf

[^10_29]: https://raw.githubusercontent.com/mlresearch/v266/main/assets/nouretdinov25a/nouretdinov25a.pdf

[^10_30]: https://icml.cc/virtual/2025/poster/45832


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La mejora SOTA para CliffordNet debe orientarse a un **detector secuencial con garantía explícita y retardo optimizado**, no solo a combinar más heurísticas. La arquitectura recomendada es:

$$
\boxed{
\text{score de innovación}
+
\text{BOCPD robusto}
+
\text{e-detector conforme}
+
\text{WCTM bajo drift}
+
\text{control de reinicios}
}
$$

Los trabajos recientes sobre e-detectors conformes muestran que se pueden obtener cotas de detección cercanas a las minimax, con retardos de orden logarítmico bajo hipótesis adecuadas; en cambio, una martingala conforme convencional puede tener validez pero potencia o retardo deficientes.[^11_1][^11_2]

## 1. Redefinir la alarma

El umbral actual $10^{-10}$ mezcla tres conceptos:

- significancia estadística;
- severidad operativa;
- sensibilidad deseada.

Separarlos:

$$
H_0:\text{el régimen actual sigue siendo seguro},
$$

$$
H_1:\text{existe un cambio con impacto operativo}.
$$

El detector debe emitir cuatro salidas:

```text
candidate_change
statistically_confirmed
change_type
recommended_action
```

Por ejemplo:


| Estado | Evidencia | Acción |
| :-- | :-- | :-- |
| Normal | baja | continuar |
| Sospechoso | CUSUM/BOCPD alto | aumentar vigilancia |
| Confirmado | e-process $\geq 1/\alpha$ | aplicar política |
| Fuera de soporte | evidencia extrema | congelar/adaptar con cautela |

Esto evita que una fluctuación transitoria active directamente un reset del optimizador.

## 2. Score correcto para momentum

No usar directamente $g_t$, porque el momentum produce dependencia:

$$
v_t=\beta v_{t-1}+(1-\beta)g_t.
$$

Construir una innovación:

$$
e_t=v_t-\widehat{\mathbb E}(v_t\mid v_{t-1},c_t),
$$

donde $c_t$ incluye:

- learning rate;
- momentum;
- batch size;
- fase de entrenamiento;
- norma de parámetros;
- pérdida;
- batch statistics.

Un modelo simple:

$$
\widehat v_t=\beta_t v_{t-1}+(1-\beta_t)\widehat g_t,
$$

$$
e_t=v_t-\widehat v_t.
$$

Luego definir:

$$
a_t =
\sqrt{
e_t^\top
(\widehat\Sigma_t+\lambda I)^{-1}
e_t
}.
$$

Para alta dimensión, usar diagonal o low-rank covariance. La conformalización debe realizarse sobre $a_t$, no sobre cada coordenada de $g_t$.

## 3. WCTM y clasificación del drift

El detector debe distinguir:

$$
P_t(X)\neq P_0(X)
$$

de:

$$
P_t(Y\mid X)\neq P_0(Y\mid X).
$$

Una adaptación de bajo riesgo puede tolerar un cambio marginal en $X$, pero debe reaccionar a un cambio condicional o a observaciones fuera del soporte.

Mantener tres evidencias:

$$
E_X,\qquad E_{Y\mid X},\qquad E_{\mathrm{support}}.
$$

Clasificación:

```text
E_X alto, E_Y bajo:
    covariate shift probablemente benigno

E_X alto, E_Y alto:
    concept shift o degradación funcional

E_support alto:
    observaciones fuera del dominio de calibración
```

Los WCTM están diseñados para monitorizar shifts inesperados, adaptarse a covariate shift moderado y diagnosticar concept shift o covariate shift extremo.[^11_3]

## 4. Fixed-reference frente a calibración adaptativa

La calibración adaptativa introduce un peligro: si el conjunto de referencia absorbe gradualmente el cambio, el detector puede dejar de detectarlo.

Usar dos detectores en paralelo:

### Detector conservador

- referencia fija;
- no absorbe muestras post-alarma;
- proporciona garantía más limpia;
- sensible a drift persistente.


### Detector adaptativo

- ventana móvil;
- pesos WCTM;
- se adapta a cambios benignos;
- mejor potencia operativa bajo drift suave;
- menor garantía si la adaptación no está controlada.

Regla:

```text
fixed_reference: autoridad estadística
adaptive_reference: diagnóstico y recuperación
```

La literatura reciente sobre test martingales conformes con referencia fija destaca precisamente que evitar la contaminación de la referencia ayuda a preservar el control anytime-valid.[^11_4]

## 5. E-detector optimizado para detección

Una power martingale fija:

$$
E_t=\prod_{i=1}^{t}\varepsilon p_i^{\varepsilon-1}
$$

puede ser poco adecuada si se desconoce la magnitud del cambio. Sustituirla por una mezcla:

$$
E_t
=
\sum_{k=1}^{K}w_k E_t^{(k)},
$$

donde cada $E_t^{(k)}$ corresponde a:

- diferente $\varepsilon$;
- diferente ventana;
- diferente magnitud esperada;
- diferente escala temporal.

Una configuración inicial:

```text
epsilon = {0.02, 0.05, 0.1, 0.25, 0.5}
window  = {16, 64, 256}
```

y:

$$
\sum_k w_k=1.
$$

La mezcla mejora robustez frente a cambios pequeños, abruptos o persistentes. El umbral sigue siendo:

$$
\log E_t\geq\log(1/\alpha).
$$

Los e-detectors proporcionan una formulación no paramétrica con frontera explícita $\log(1/\alpha)$, y se han estudiado cotas de retardo cercanas a las óptimas.[^11_2][^11_5]

## 6. BOCPD con Student-$t$ y run-length truncado

Usar:

$$
s_t\mid r_t,\theta_{r_t}
\sim t_\nu(\mu_{r_t},\sigma_{r_t})
$$

en lugar de una likelihood gaussiana. Esto reduce falsas alarmas ante colas pesadas de gradientes.

Para eficiencia, mantener:

$$
r_t\in\{0,\dots,R_{\max}\}
$$

con $R_{\max}$ configurable. Podar estados con:

$$
P(r_t=r)<10^{-8}.
$$

Si se necesitan cambios con duración muy larga, usar una cola agregada:

```text
short run lengths: exact
long run lengths: logarithmic bins
```

Esto conserva detalle en cambios recientes y reduce memoria.

## 7. Dependencia temporal y validez

La validez conformal clásica no se transfiere automáticamente a gradientes autocorrelacionados. Las series temporales son no intercambiables; por eso se necesitan innovaciones, bloques o supuestos de dependencia.[^11_6][^11_7]

Para V911 recomiendo:

1. residualizar mediante modelo predictivo;
2. usar bloques de longitud $L$;
3. insertar una guard band;
4. calibrar en bloques;
5. reportar garantía bajo la hipótesis de bloques intercambiables o mixing.

Estructura:

```text
reference blocks
→ guard gap
→ calibration blocks
→ guard gap
→ monitoring block
```

Si $L$ es demasiado corto, queda autocorrelación residual; si es demasiado largo, aumenta el retardo. Elegir $L$ mediante:

$$
L\approx
\text{primer lag donde ACF residual cae bajo }\rho_0.
$$

## 8. Control de falsas alarmas con reinicios

Cada reinicio debe consumir presupuesto:

$$
\alpha_j
=
\frac{6\alpha}{\pi^2(j+1)^2},
$$

de modo que:

$$
\sum_{j=0}^{\infty}\alpha_j=\alpha.
$$

El umbral del episodio $j$ es:

$$
\log(1/\alpha_j).
$$

No reiniciar el e-process a cero conservando el mismo $\alpha$. Eso puede producir una cantidad ilimitada de oportunidades de falsa alarma.

Alternativas:

- no reiniciar y continuar el e-process;
- usar alpha spending;
- usar un e-detector por episodios;
- reiniciar solo después de una nueva referencia validada.


## 9. Control de múltiples señales

Si CliffordNet monitoriza $m$ señales, no emitir una alarma si cualquiera supera el umbral individual sin corrección.

Usar e-value global:

$$
E_t^{\mathrm{global}}
=
\sum_{j=1}^{m}w_j E_{t,j}.
$$

Ejemplo:

```text
0.35 gradient innovation
0.25 loss/residual
0.20 geometry
0.10 optimizer state
0.10 support score
```

Los pesos deben fijarse antes del test o aprenderse en validación separada.

Si el objetivo es controlar proporción de falsas alarmas en múltiples despliegues, usar online FDR/e-LOND, especialmente porque los e-values toleran mejor dependencia que correcciones basadas en p-values.[^11_8]

## 10. Política de acción con histéresis

Definir dos umbrales:

$$
h_{\mathrm{enter}}=\log(1/\alpha_{\mathrm{enter}}),
$$

$$
h_{\mathrm{exit}}<h_{\mathrm{enter}}.
$$

Entrar en alerta si:

```text
logE >= h_enter
and q_BOCPD >= q_enter
```

Salir solo si:

```text
logE <= h_exit
for H consecutive steps
```

Esto evita oscilaciones de estado.

Ejemplo:

```text
warning: q_BOCPD > 0.6
confirmed: logE > log(1e4)
critical: logE > log(1e6) or support evidence high
```

`warning` no modifica el entrenamiento; `confirmed` reduce learning rate o activa recalibración; `critical` congela o restaura checkpoint.

## 11. Detector multiescala

Los cambios pueden aparecer a diferentes velocidades. Usar ventanas:

$$
W\in\{8,32,128,512\}.
$$

Cada escala produce:

$$
E_t^{(W)}.
$$

Combinar:

$$
E_t=\sum_W\pi_W E_t^{(W)}.
$$

La escala corta detecta shocks; la larga detecta drift persistente. BOCPD puede utilizar la escala intermedia para estimar run length, mientras el e-detector cubre la evidencia global.

## 12. Garantía operacional

La documentación de CliffordNet debe declarar:

### Garantía exacta

Solo si:

- referencia fija;
- exchangeability o hipótesis válida;
- apuestas predefinidas;
- no hay contaminación;
- reinicios con presupuesto.


### Garantía ponderada

Si:

- WCTM con pesos válidos;
- soporte común;
- pesos acotados;
- ESS suficiente.


### Rendimiento empírico

Si:

- adaptación online agresiva;
- fuerte autocorrelación;
- detector entrenado sobre el mismo stream;
- dependencia entre múltiples canales.

No presentar la salida como “probabilidad bayesiana de cambio” y “p-value frecuentista” simultáneamente. BOCPD produce una posterior dependiente del modelo; el e-process produce evidencia secuencial bajo una nula. Son cantidades diferentes.

## 13. Benchmark mínimo

Evaluar:

$$
\mathrm{ARL}_0,
\quad
\mathrm{PFA},
\quad
\mathrm{EDD},
\quad
\mathrm{WADD},
\quad
\mathrm{FDR},
\quad
\mathrm{ESS}.
$$

Escenarios:

1. entrenamiento estable;
2. warm-up;
3. momentum $0.9,0.99,0.999$;
4. learning-rate schedule;
5. shock abrupto;
6. drift gradual;
7. concept shift;
8. out-of-support;
9. autocorrelación;
10. múltiples canales;
11. reinicios;
12. referencia fija frente a adaptativa.

Comparar:

```text
CUSUM
EWMA
BOCPD
CTM
WCTM
e-detector
BOCPD + e-detector
BOCPD + WCTM + e-detector
```

La comparación debe fijar el mismo $\mathrm{ARL}_0$ o la misma probabilidad de falsa alarma. Comparar métodos con umbrales arbitrarios produce conclusiones inválidas.

## 14. Implementación recomendada

```python
class CliffordMonitor:
    def __init__(self, alpha, fixed_calibration, adaptive_calibration):
        self.alpha = alpha
        self.fixed = fixed_calibration
        self.adaptive = adaptive_calibration
        self.bocpd = RobustBOCPD()
        self.log_e_fixed = 0.0
        self.log_e_adaptive = 0.0
        self.episode = 0

    def update(self, state):
        innovation = residualize_momentum(state)
        score = robust_score(innovation)

        p_fixed = conformal_pvalue(score, self.fixed)
        p_adapt = weighted_conformal_pvalue(
            score, self.adaptive, context=state.context
        )

        self.log_e_fixed += mixture_log_bet(p_fixed)
        self.log_e_adaptive += mixture_log_bet(p_adapt)

        self.bocpd.update(innovation, state.context)
        q = self.bocpd.change_probability()

        certified = self.log_e_fixed >= episode_threshold(
            self.alpha, self.episode
        )
        adaptive_alert = (
            self.log_e_adaptive >= math.log(1 / 1e-3)
        )

        return classify(
            q_bocpd=q,
            certified=certified,
            adaptive_alert=adaptive_alert,
            support_score=support_score(state)
        )
```

El detector fijo decide la certificación; el adaptativo mejora potencia y diagnóstico.

## Recomendación final

La solución científica SOTA para la brecha V911 es:

$$
\boxed{
\text{referencia fija para validez}
+
\text{WCTM para drift}
+
\text{BOCPD Student-}t
+
\text{mixture e-detector}
+
\text{bloques temporales}
+
\text{alpha spending}
}
$$

La prioridad de implementación es:

1. eliminar el umbral heurístico $10^{-10}$;
2. crear un score de innovación que neutralice momentum;
3. añadir un e-process de referencia fija;
4. añadir BOCPD solo como diagnóstico de régimen;
5. introducir WCTM para covariate drift;
6. controlar dependencia mediante bloques/innovaciones;
7. usar e-detectors multiescala para reducir retardo;
8. proteger reinicios con alpha spending;
9. combinar canales mediante e-values;
10. validar con ARL, falsa alarma y detection delay.

La ventaja clave es que el sistema deja de elegir un número arbitrario y pasa a optimizar explícitamente el compromiso:

$$
\text{falsas alarmas}
\longleftrightarrow
\text{retardo}
\longleftrightarrow
\text{adaptación}.
$$

BOCPD aporta inferencia sobre el régimen; WCTM aporta robustez frente a drift; los e-processes aportan evidencia secuencial; y la referencia fija preserva una autoridad estadística que no se contamina durante la adaptación.

<span style="display:none">[^11_10][^11_11][^11_12][^11_13][^11_14][^11_15][^11_16][^11_17][^11_18][^11_9]</span>

<div align="center">⁂</div>

[^11_1]: https://arxiv.deeppaper.ai/papers/2609.27179v1

[^11_2]: https://ar5iv.labs.arxiv.org/html/2203.03532

[^11_3]: https://toehanger.shop/?\_=/@anqi-angie-liu%23KGzYqmHwYljVlEKycpyPcW533r0=

[^11_4]: https://www.emergentmind.com/topics/distribution-shift-detection

[^11_5]: https://arxiv.org/html/2203.03532v4

[^11_6]: https://arxiv.org/html/2410.13115v2

[^11_7]: https://arxiv.org/html/2511.13608v1

[^11_8]: https://www.jmlr.org/papers/volume27/25-2123/25-2123.pdf

[^11_9]: https://proceedings.neurips.cc/paper_files/paper/2025/file/12271b64c483ad8f6192eb6aaa102044-Paper-Conference.pdf

[^11_10]: https://www.tandfonline.com/doi/full/10.1080/07474946.2023.2276170

[^11_11]: https://ar5iv.labs.arxiv.org/html/2504.09573

[^11_12]: https://www.emergentmind.com/topics/online-change-point-detection-ocpd

[^11_13]: https://www.pyxida.aueb.gr/files/392f63c2-8e60-4792-8dec-b68e86c9ab0a/download/Kokkinis_2025.pdf

[^11_14]: https://zenvanriel.com/ai-engineer-blog/concept-drift-in-ai-systems-a-2026-engineers-guide/

[^11_15]: https://arxiv.org/abs/2609.27179

[^11_16]: https://arxiv.org/html/2505.04608v1

[^11_17]: https://arxiv.org/pdf/2604.15740v1.pdf

[^11_18]: https://www.alphaxiv.org/abs/2505.04608v4

