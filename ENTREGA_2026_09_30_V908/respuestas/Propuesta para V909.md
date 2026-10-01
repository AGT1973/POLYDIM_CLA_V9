<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## Propuesta para V909

La corrección adecuada es reemplazar la eliminación de Gauss sobre $[A\mid B]$ por un operador Cayley–Stiefel aplicado *matrix-free* y resolver únicamente sus acciones sobre vectores mediante FGMRES. La identidad de Woodbury debe usarse como una reducción operatorial, no como una inversión explícita de una matriz $2K\times 2K$.

La transformación de Cayley en Stiefel admite precisamente una formulación de bajo rango. Para $X\in\mathrm{St}(n,K)$, un operador skew-simétrico de la forma

$$
W = U V^{T}-V U^{T}
$$

tiene rango como máximo $2K$, y el paso de Cayley se define por

$$
Y=
\left(I-\frac{\alpha}{2}W\right)^{-1}
\left(I+\frac{\alpha}{2}W\right)X.
$$

La literatura confirma que el Cayley cerrado requiere una inversión costosa, mientras que una iteración fija evita materializarla y utiliza únicamente multiplicaciones matriciales. En el caso Stiefel, la parametrización densa también se reduce a un núcleo $K\times K$, por ejemplo $I_K+X^*X+Y$, sin construir el operador grande completo.[^1_1][^1_2]

## Reducción Woodbury

Sea

$$
M = I-\frac{\alpha}{2}W
  = I + U C V^{T},
$$

donde $U,V\in\mathbb{R}^{n\times r}$, $r\leq 2K$, y $C$ contiene los factores de escala y signos. La aplicación requerida es

$$
z=M^{-1}b.
$$

No debe calcularse $M^{-1}$. La forma operatorial de Woodbury es

$$
M^{-1}b
=
b-U
\left(C^{-1}+V^{T}U\right)^{-1}
V^{T}b.
$$

Para evitar incluso la inversión formal del núcleo pequeño, defina la operación

$$
\mathcal{S}(q)
=
\operatorname{solve}
\left(C^{-1}+V^{T}U,\;q\right),
$$

mediante LU/Cholesky del núcleo $r\times r$, o mediante un FGMRES interno si ese núcleo también debe tratarse de forma iterativa. Entonces:

$$
\operatorname{apply\_cayley}(b)
=
b-U\,\mathcal{S}(V^{T}b).
$$

El paso completo queda:

$$
Y =
\operatorname{apply\_cayley}
\left[
X+\frac{\alpha}{2}WX
\right].
$$

En ningún punto aparece $[A\mid B]$, ni una matriz densa $2K\times 2K$ aumentada.

## Arquitectura recomendada

Implementar tres operadores independientes:

1. **Aplicación skew-Stiefel**

$$
Wq = U(V^{T}q)-V(U^{T}q).
$$

Esto requiere dos productos con $U,V$ y dos reducciones de dimensión $n\to r$.

2. **Aplicación Cayley**

$$
\mathcal{C}(q)
=
\left(I-\frac{\alpha}{2}W\right)^{-1}
\left(I+\frac{\alpha}{2}W\right)q.
$$

Primero se calcula

$$
t=q+\frac{\alpha}{2}Wq,
$$

y después se aplica la reducción Woodbury a $t$.

3. **Operador lineal del solver**

Si el sistema original es

$$
\mathcal{L}(x)=b,
$$

implementar únicamente:

```text
apply_L(x, y)
apply_preconditioner(x, z)
```

y suministrar esas acciones a FGMRES. Los métodos Krylov matrix-free sólo requieren productos operador-vector; FGMRES está diseñado además para precondicionadores variables.[^1_3][^1_4]

## Pseudocódigo

```text
function apply_W(q):
    a = Vᵀ q
    b = Uᵀ q
    return U a - V b

function apply_small_solve(rhs):
    # Factorización del núcleo r × r:
    # S = C⁻¹ + Vᵀ U
    return solve(S, rhs)

function apply_Minv(q):
    t = Vᵀ q
    c = apply_small_solve(t)
    return q - U c

function apply_cayley(q):
    rhs = q + (α / 2) * apply_W(q)
    return apply_Minv(rhs)

function apply_stiefel(X):
    return apply_cayley(X)
```

Si la dirección se representa como producto de bajo rango, no conviene aplicar las rutinas columna por columna. Para $X\in\mathbb{R}^{n\times K}$, usar operaciones bloque:

```text
function apply_W_block(X):
    return U * (Vᵀ * X) - V * (Uᵀ * X)

function apply_cayley_block(X):
    rhs = X + (α / 2) * apply_W_block(X)
    T = Vᵀ * rhs
    C = solve_small_block(S, T)
    return rhs - U * C
```

Esto reduce las transferencias GPU/RAM y permite fusionar los productos $U^T X$, $V^T X$, $U(\cdot)$ y $V(\cdot)$ en kernels de tipo GEMM.

## Complejidad

Con $r=2K$, el coste dominante pasa de la factorización densa

$$
O(K^3)
$$

sobre la matriz aumentada, más el almacenamiento de estructuras densas grandes, a:

$$
O(nr+r^3)
$$

para construir/factorizar el núcleo reducido, y aproximadamente

$$
O(nr)
$$

por aplicación del operador.

Si el núcleo se reutiliza durante varias iteraciones de FGMRES, su coste $O(r^3)$ se paga una sola vez por actualización del punto de Stiefel. Para $K\ll n$, esto es sustancialmente más barato que operar sobre la estructura densa original. La formulación coincide con la ventaja habitual de Woodbury: resolver una perturbación de bajo rango mediante un sistema reducido en lugar de refactorizar el operador completo.[^1_5][^1_6]

## FGMRES externo

El solver debería usar un esquema como:

```text
x = x0
r = b - apply_A(x)

for j = 1:maxiter:
    z[j] = flexible_preconditioner(r)
    w    = apply_A(z[j])

    # Arnoldi modificado
    for i = 1:j:
        H[i,j] = dot(Q[i], w)
        w      = w - H[i,j] * Q[i]

    H[j+1,j] = norm(w)
    Q[j+1]   = w / H[j+1,j]

    # Resolver el problema pequeño de mínimos cuadrados
    update_residual()

    if residual < tolerance:
        break
```

El precondicionador puede ser:

$$
P_j^{-1}
=
\mathcal{C}_j
\circ
\mathcal{S}_j^{-1}
\circ
\mathcal{C}_j^{*},
$$

con $U_j,V_j$ actualizados dinámicamente. Esa variabilidad es precisamente la razón para preferir FGMRES frente a GMRES estándar.

## Puntos críticos de estabilidad

- No formar nunca $C^{-1}$ si $C$ es singular o mal condicionado; almacenar directamente el núcleo equivalente y resolverlo.
- Usar factorización pivotada para el sistema reducido.
- Monitorizar

$$
\|X^{T}X-I\|_F
$$

después de cada paso.

- Recalcular el núcleo reducido sólo cuando cambien $U,V$, $\alpha$ o el punto Stiefel.
- Aplicar reortogonalización selectiva de Arnoldi en FGMRES.
- Si $V^{T}U$ pierde estabilidad numérica, usar una factorización QR de los factores de bajo rango, no de la matriz $n\times n$.
- Para GPU, mantener $U,V$ residentes y reducir únicamente los bloques $r\times r$ al host si el núcleo es pequeño.

La sustitución propuesta elimina el cuello de botella de V908: la memoria local `thread_local` puede conservarse, pero el solver ya no debe reservar ni ensamblar la matriz aumentada. El núcleo matemático de V909 debe ser `apply_W → apply_small_solve → apply_cayley`, conectado a FGMRES mediante productos operador-vector.

<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://web.engr.oregonstate.edu/~sinisa/research/publications/iclr20_Cayley.pdf

[^1_2]: https://ar5iv.labs.arxiv.org/html/1612.07142

[^1_3]: https://jso.dev/Krylov.jl/stable/matrix_free/

[^1_4]: http://documenta.ciemat.es/bitstream/123456789/1956/1/Manuscript_GMRES_and_SDC_October2021.pdf

[^1_5]: https://www.cs.cornell.edu/~bindel/class/cs6210-f09/lec12.pdf

[^1_6]: https://repository.tudelft.nl/file/File_288236e4-75ea-41d1-8265-9767025b4aee?preview=1

[^1_7]: https://www.sciencedirect.com/science/article/pii/S039304401730205X

[^1_8]: https://par.nsf.gov/servlets/purl/10426144

[^1_9]: https://arxiv.org/html/2305.17901v1

[^1_10]: https://www.eurasip.org/Proceedings/Eusipco/eusipco2019/Proceedings/papers/1570529270.pdf

[^1_11]: https://arxiv.org/html/2311.00907v2

[^1_12]: https://www.tandfonline.com/doi/full/10.1080/02331934.2022.2142471

[^1_13]: https://findresearcher.sdu.dk/ws/files/191222862/2108.12447v1.pdf

[^1_14]: https://ora.ox.ac.uk/objects/uuid:0332d0dd-cd45-4c0d-b477-85e9552d0871/files/sh989r470v

[^1_15]: https://dial.uclouvain.be/pr/boreal/object/boreal:249366/datastream/PDF_01/view

[^1_16]: https://ar5iv.labs.arxiv.org/html/2211.09481

[^1_17]: https://cseweb.ucsd.edu/classes/sp24/cse291-e/papers/StiefelManifold/StiefelNotes.pdf

[^1_18]: https://openreview.net/pdf?id=6w9qffvXkq

[^1_19]: https://onlinelibrary.wiley.com/doi/10.1002/nla.2528

[^1_20]: https://www.aanda.org/articles/aa/pdf/2021/11/aa41238-21.pdf

[^1_21]: https://arxiv.org/html/2607.22004v1

[^1_22]: https://arxiv.org/html/2406.15120v1

[^1_23]: https://www.cs.princeton.edu/courses/archive/fall11/cos323/notes/cos323_f11_lecture06_linsys2.pdf

[^1_24]: https://research.manchester.ac.uk/en/publications/a-sherman-morrison-woodbury-approach-to-solving-least-squares-pro/

[^1_25]: https://www.scielo.br/j/pope/a/wsdScHqHDCMZzfcGFtKZPfh/?lang=en

[^1_26]: https://arxiv.org/html/2205.00645v2

[^1_27]: https://en.wikipedia.org/wiki/Woodbury_matrix_identity

[^1_28]: https://jso.dev/Krylov.jl/v0.5/matrix-free/

[^1_29]: https://www.superfri.org/index.php/superfri/article/download/666/800

[^1_30]: https://scispace.com/pdf/cola-exploiting-compositional-structure-for-automatic-and-4qx4trvcdp.pdf


---

## Diagnóstico SOTA

La dirección correcta para V909 no es solamente “aplicar Woodbury”, sino combinar cuatro capas:

1. Cayley de bajo rango con rango efectivo $r\le 2K$.
2. Resolución *matrix-free* mediante productos operador-vector.
3. FGMRES externo con precondicionador Cayley variable.
4. Núcleo reducido adaptativo, factorizado sólo cuando sea numéricamente fiable.

Una formulación reciente de Newton–Krylov para Stiefel usa exactamente este patrón: Jacobiano-vector sin ensamblar, GMRES matrix-free y un precondicionador Cayley aplicado mediante Woodbury sobre un sistema $2p\times 2p$, con coste $O(np^2)$ por iteración. También existen implementaciones recientes de Cayley-SMW para Stiefel que explotan kernels *tall-skinny* y bloqueo de caché.[^2_1][^2_2]

La conclusión importante es que V909 debe evolucionar desde “eliminar la matriz aumentada” hacia un diseño completo de operador:

$$
\texttt{JVP}
\;\longrightarrow\;
\texttt{CayleyPreconditioner}
\;\longrightarrow\;
\texttt{FGMRES}
$$

sin crear matrices de dimensión $n\times n$, $2K\times 2K$ densas salvo el núcleo reducido inevitable, ni inversas explícitas.

## 1. Forma algebraica correcta

Sea $X\in\mathrm{St}(n,K)$ y $G=\nabla f(X)$. Para una dirección de descenso $Z$, la construcción estándar es

$$
W = G X^{T}-XG^{T},
\qquad W^{T}=-W.
$$

Como $W$ es diferencia de dos productos de rango $K$, su rango satisface

$$
\operatorname{rank}(W)\le 2K.
$$

Es preferible representar $W$ como

$$
W=UV^{T}-VU^{T},
$$

con

$$
U=G,\qquad V=X.
$$

La aplicación no requiere construir $W$:

$$
WQ
=
U(V^{T}Q)-V(U^{T}Q).
$$

Para una matriz bloque $Q\in\mathbb{R}^{n\times s}$, el coste es aproximadamente

$$
2\,O(nsK)+O(KsK),
$$

y el almacenamiento adicional es $O(nK)$.

La transformación de Cayley puede escribirse como

$$
Y=
\left(I-\tau W\right)^{-1}
\left(I+\tau W\right)X,
\qquad
\tau=\frac{\alpha}{2}.
$$

La parte difícil es resolver

$$
\left(I-\tau W\right)Z=B.
$$

Defina

$$
\widetilde U=\tau U,\qquad
\widetilde V=V,
$$

y agrupe el operador como

$$
I-\tau W
=
I+
\begin{bmatrix}
\widetilde U & -\tau V
\end{bmatrix}
\begin{bmatrix}
V^{T}\\
U^{T}
\end{bmatrix}.
$$

Así, con

$$
P=
\begin{bmatrix}
\tau U & -\tau V
\end{bmatrix},
\qquad
Q=
\begin{bmatrix}
V & U
\end{bmatrix},
$$

se obtiene

$$
I-\tau W=I+PQ^{T}.
$$

La aplicación de Woodbury es

$$
(I+PQ^{T})^{-1}B
=
B-P\,S^{-1}(Q^{T}B),
$$

donde

$$
S=I_{2K}+Q^{T}P.
$$

El punto crítico para V909 es que $S$ puede ensamblarse sin construir $W$:

$$
S=
\begin{bmatrix}
I+\tau V^{T}U & -\tau V^{T}V\\
\tau U^{T}U & I-\tau U^{T}V
\end{bmatrix}.
$$

No debe utilizarse `inverse(S)`. Hay que resolver

$$
S C=Q^{T}B
$$

con una factorización pivotada reutilizable o, si el núcleo es mal condicionado, con un solver iterativo pequeño.

## 2. Mejora fundamental: reducir el rango real

El rango algebraico $2K$ suele ser una cota pesimista. Si $G$ tiene componentes casi contenidas en $\operatorname{range}(X)$, la dirección efectiva puede tener un rango mucho menor.

Proyecte el gradiente:

$$
G_{\perp}=(I-XX^{T})G.
$$

La parte $X(X^{T}G)$ sólo modifica la rotación interna de las columnas y no siempre necesita tratarse como una actualización ambiental completa. Para muchos problemas, una representación más estable es

$$
W=
G_{\perp}X^{T}-XG_{\perp}^{T}
+
X\Omega X^{T},
$$

donde

$$
\Omega=X^{T}G-G^{T}X
$$

es skew-simétrica.

Si el término de rotación interna puede integrarse mediante un núcleo $K\times K$, el bloque grande se reduce a la interacción entre $G_{\perp}$ y $X$. En vez de un sistema $2K\times 2K$, puede aparecer una combinación de sistemas $K\times K$ y un bloque skew pequeño.

Una mejora adicional es comprimir $G_{\perp}$ mediante QR o SVD truncada:

$$
G_{\perp}\approx Q_r R_r,\qquad r\ll K.
$$

Entonces

$$
W\approx Q_r(R_rX^{T})-X(R_r^{T}Q_r^{T}),
$$

y el núcleo Woodbury pasa de tamaño $2K$ a $2r$. La compresión debe ser adaptativa, controlada por

$$
\frac{\|G_{\perp}-Q_rR_r\|_F}{\|G_{\perp}\|_F}
\le \varepsilon_{\mathrm{rank}}.
$$

No conviene comprimir automáticamente en todos los pasos: el coste de QR sólo compensa si el núcleo reducido se reutiliza varias veces o si $r\ll K$.

## 3. Precondicionador SOTA para FGMRES

El operador Newton o Hessiano puede escribirse abstractamente como

$$
\mathcal{J}_X[H]
=
\operatorname{JVP}_{F}(X)[H].
$$

No se debe formar $\mathcal{J}_X$. FGMRES recibe solamente:

```text
JVP(H) -> J_X[H]
```

Un precondicionador eficaz es

$$
M_X^{-1}
=
\left(I+\tau W_X\right)^{-1}
\mathcal{D}_X^{-1}
\left(I-\tau W_X\right),
$$

donde $\mathcal{D}_X$ aproxima la parte dominante del Hessiano o del Jacobiano.

La parte Cayley se aplica con Woodbury. La parte $\mathcal{D}_X^{-1}$ puede implementarse con:

- Jacobi por bloques para problemas de mínimos cuadrados.
- Aproximación Gauss–Newton.
- Precondicionador diagonal de Fisher o métrico canónico.
- AMG si la parte principal procede de un operador PDE.
- Factorización incompleta sólo de la parte dispersa, nunca del operador Cayley denso.
- *Inner Krylov* de pocas iteraciones cuando $\mathcal{D}_X$ no admite inversión barata.

FGMRES es preferible porque $\mathcal{D}_X$, la tolerancia interna y el rango comprimido pueden cambiar en cada iteración. Los métodos Krylov matrix-free requieren exclusivamente productos operador-vector, y la literatura de Newton–Krylov para Stiefel usa precisamente esta arquitectura. La precondición flexible también permite que el precondicionador interno sea inexacto o variable.[^2_1][^2_3]

## 4. Resolver el núcleo sin inversa formal

La recomendación inicial de usar LU para $S$ es correcta únicamente si $S$ es moderadamente bien condicionado. La versión robusta debe decidir entre tres modos.

### Modo A: LU pivotada

Usar cuando

$$
\kappa(S)\lesssim \kappa_{\mathrm{LU}}.
$$

Se factoriza una vez:

$$
P_S S=L U.
$$

Después, cada aplicación del precondicionador usa dos sustituciones triangulares. Es el modo más rápido cuando $U,V,\alpha$ permanecen constantes durante varios pasos.

### Modo B: QR del núcleo

Si $S$ es no simétrico o la LU presenta pivotes pequeños, emplear QR con pivotado de columnas. Es más caro, pero evita depender de una estructura SPD inexistente.

### Modo C: FGMRES interno

Si el núcleo está cerca de singularidad o cambia en cada iteración, resolver

$$
S C=R
$$

con GMRES/FGMRES interno y parada inexacta:

$$
\frac{\|SC-R\|}{\|R\|}
\le \eta_{\mathrm{inner}}.
$$

La tolerancia debe seguir una regla de forcing tipo Eisenstat–Walker:

$$
\eta_{\mathrm{inner},j}
=
\min\left(\eta_{\max},
c\left(
\frac{\|r_j\|}{\|r_{j-1}\|}
\right)^\gamma
\right),
$$

con $0<\gamma\le 1$. Cerca de la solución, el núcleo debe resolverse con mayor precisión; lejos de ella, una aproximación barata es suficiente.

## 5. Cayley implícito y Newton–Krylov

Para el paso explícito Cayley,

$$
Y(X)=\operatorname{cay}(\tau W(X))X,
$$

el cálculo es relativamente directo. Pero si V909 busca una forma implícita estable, $W$ depende de $Y$, y debe resolverse

$$
F(Y)=
\left(I+\tau W(Y)\right)Y
-
\left(I-\tau W(X)\right)X
=0.
$$

El Newton–Krylov correspondiente es

$$
\mathcal{J}_F(Y)[H]
=
H+\tau W(Y)H+\tau\,DW(Y)[H]\,Y.
$$

Si $W(Y)=G(Y)Y^{T}-YG(Y)^{T}$, entonces

$$
DW(Y)[H]
=
DG(Y)[H]\,Y^{T}
+
G(Y)H^{T}
-
H G(Y)^{T}
-
Y DG(Y)[H]^{T}.
$$

La implementación debe obtener $DG(Y)[H]$ mediante JVP automático o una rutina analítica. No debe calcular el Hessiano completo.

Un solver recomendado es:

```text
Y = cayley_explicit(X, G(X), alpha)

for nonlinear_iter in 1:max_newton:
    F = residual_cayley(Y, X)
    if norm(F) <= tol_nonlinear:
        break

    rhs = -F

    H = FGMRES(
        JVP = lambda Z: cayley_jvp(Y, Z),
        rhs = rhs,
        preconditioner = cayley_preconditioner(Y)
    )

    Y_trial = line_search_or_damping(Y, H)

    if orthogonality_residual(Y_trial) > tol_orth:
        Y_trial = stable_cayley_correction(Y, H)

    Y = Y_trial
```

La referencia de Newton–Krylov para restricciones Stiefel reporta que el paso implícito trapezoidal/Cayley puede resolverse con JVP matrix-free y que el precondicionador Cayley se aplica en bajo rango mediante Woodbury.[^2_1]

## 6. Mejoras de estabilidad numérica

La fórmula SMW puede ser inestable cuando los factores $U,V$ son casi linealmente dependientes. Este problema está documentado en métodos de gradiente Cayley: una estabilización mediante Gram–Schmidt puede ser necesaria.[^2_4]

La solución práctica es ortogonalizar los factores antes de formar el núcleo:

$$
U=Q_U R_U,\qquad V=Q_V R_V.
$$

En lugar de utilizar directamente $U,V$, trabajar con $Q_U,Q_V$ y absorber $R_U,R_V$ en los bloques pequeños. Para mayor robustez:

- Usar QR con pivotado si el rango es incierto.
- Eliminar columnas cuyo valor diagonal de $R$ sea menor que $\varepsilon_{\mathrm{rank}}$.
- Escalar $U,V$ para equilibrar sus normas.
- Usar factorización completa pivotada del núcleo.
- Comprobar el residuo de la identidad SMW con un vector de prueba aleatorio:

$$
\rho=
\frac{\|(I-\tau W)z_{\mathrm{SMW}}-b\|}
{\|b\|}.
$$

Si $\rho$ supera el umbral, degradar temporalmente al modo iterativo.

La conservación geométrica debe medirse después de cada actualización:

$$
e_{\mathrm{St}}=\|Y^{T}Y-I_K\|_F.
$$

Para problemas de precisión doble, un objetivo razonable es mantener

$$
e_{\mathrm{St}}
\lesssim
10^2\epsilon_{\mathrm{mach}}
\max(1,\|Y\|_F^2),
$$

salvo que se utilice una aproximación truncada deliberada.

## 7. Variante superior: Cayley racional aplicada por bloques

No hace falta aplicar una Cayley completa a toda la matriz $X$. Si sólo se necesita $Y$, calcular:

$$
B=
X+\tau WX,
$$

y resolver

$$
(I-\tau W)Y=B.
$$

Con la forma Woodbury:

$$
R=Q^{T}B,
\qquad
SC=R,
\qquad
Y=B-PC.
$$

La secuencia de kernels GPU es:

```text
R1 = Vᵀ @ B
R2 = Uᵀ @ B
R  = stack(R1, R2)

```

<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_20][^2_21][^2_22][^2_23][^2_24][^2_25][^2_26][^2_27][^2_28][^2_29][^2_30][^2_5][^2_6][^2_7][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://arxiv.org/html/2508.18764v1

[^2_2]: https://github.com/AGT1973/POLYDIM_CLA_V8/blob/main/src/stiefel_cayley_smw_avx512.cpp

[^2_3]: https://www.emergentmind.com/topics/krylov-solvers

[^2_4]: https://arxiv.org/html/2410.22068v2

[^2_5]: https://dl.acm.org/doi/abs/10.1007/s10107-014-0816-7

[^2_6]: https://onlinelibrary.wiley.com/doi/10.1002/nla.70077

[^2_7]: http://www.jmlr.org/papers/volume25/21-1022/21-1022.pdf

[^2_8]: https://epubs.siam.org/doi/10.1137/S1064827500366124

[^2_9]: https://epubs.siam.org/doi/10.1137/0719025

[^2_10]: https://aclanthology.org/2025.findings-emnlp.1143.pdf

[^2_11]: https://arxiv.org/pdf/2609.21039v1.pdf

[^2_12]: https://raw.githubusercontent.com/mlresearch/v235/main/assets/vary24a/vary24a.pdf

[^2_13]: https://github.com/JunLi-Galios/Optimization-on-Stiefel-Manifold-via-Cayley-Transform

[^2_14]: https://www.emergentmind.com/topics/matrix-manifold-optimization

[^2_15]: https://epubs.siam.org/doi/10.1137/S0895479895290954

[^2_16]: https://epubs.siam.org/doi/10.1137/110837711

[^2_17]: https://arxiv.org/html/2609.21039

[^2_18]: https://arxiv.org/html/2603.07133v2

[^2_19]: https://arxiv.org/html/2507.02839v2/

[^2_20]: https://www.arxiv.org/list/math/2024-06?skip=1500\&show=1000

[^2_21]: https://www.arxiv.org/list/math.NA/2024-06?skip=115\&show=500

[^2_22]: https://arxiv.org/html/2509.16113v1

[^2_23]: https://arxiv.org/html/2404.13301v1

[^2_24]: https://arxiv.org/pdf/2607.28036.pdf

[^2_25]: https://www.arxiv.org/pdf/2305.00091.pdf

[^2_26]: https://arxiv.org/pdf/2405.01702.pdf

[^2_27]: https://ar5iv.labs.arxiv.org/html/2406.14299

[^2_28]: https://arxiv.org/html/2311.00907v2

[^2_29]: https://ar5iv.labs.arxiv.org/html/1612.07142

[^2_30]: https://web.engr.oregonstate.edu/~sinisa/research/publications/iclr20_Cayley.pdf


---

# 2. Brecha de Riesgo FFI Nativo (ctypes vs Ownership)

Brecha (V909): CreateFileMappingW repara la recolección prematura UTF-8 (dangling pointers por GC), pero el puente Python sigue basándose en ctypes, lo cual hereda una arquitectura pasiva sin garantías semánticas en tiempo de compilación.
Requiere: Refactorización a una extensión CPython nativa o pybind11. ctypes es calificado como insostenible a escala asintótica por la evaluación; el ownership debe anclarse mediante Resource Acquisition Is Initialization (RAII) con la interfaz C++ directa, exponiendo memoryview o Buffer Protocol.Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La brecha V909 no es sólo una sustitución de `ctypes`: es un problema de **contrato de propiedad, vida útil, aliasing, concurrencia y ABI**. La solución SOTA consiste en separar estrictamente el núcleo C++ —que posee los recursos mediante RAII— de una capa de binding que expone únicamente objetos Python con propietarios explícitos y vistas buffer verificables.

## Diagnóstico técnico

`ctypes` puede invocar correctamente `CreateFileMappingW`, pero no expresa de forma robusta:

- quién libera el `HANDLE`;
- cuándo puede cerrarse el mapping;
- si un `memoryview` sigue apuntando a memoria válida;
- si una vista es sólo lectura o mutable;
- si el buffer es contiguo o tiene strides;
- qué ocurre al copiar, mover o destruir el objeto;
- cómo se sincronizan varias vistas o hilos.

El hecho de que la cadena UTF-8 ya no sea un puntero colgante sólo resuelve la vida útil del argumento. No resuelve la vida útil del recurso nativo ni de los consumidores posteriores.

El Buffer Protocol de CPython exige que el consumidor libere exactamente una vez cada `Py_buffer` obtenido mediante `PyObject_GetBuffer()`, y el campo `Py_buffer.obj` mantiene una referencia fuerte al exportador mientras la vista está activa. Esa semántica es mucho más adecuada que entregar punteros crudos desde `ctypes`.[^3_1]

## Arquitectura recomendada

### 1. Núcleo C++ RAII

El recurso debe estar encapsulado en una clase no copiable y movible:

```cpp
class mapped_region {
public:
    mapped_region(std::wstring name,
                  std::size_t bytes,
                  access_mode mode);

    mapped_region(const mapped_region&) = delete;
    mapped_region& operator=(const mapped_region&) = delete;

    mapped_region(mapped_region&&) noexcept;
    mapped_region& operator=(mapped_region&&) noexcept;

    ~mapped_region() noexcept;

    void* data() const noexcept;
    std::size_t size() const noexcept;
    bool readonly() const noexcept;

private:
    native_handle mapping_{};
    void* address_{nullptr};
    std::size_t size_{0};
    access_mode mode_{};
};
```

El destructor debe ser el único lugar normal donde se ejecuten:

```cpp
UnmapViewOfFile(address_);
CloseHandle(mapping_);
```

El orden es importante: primero se libera la vista, después el handle del mapping. La clase debe cumplir invariantes fuertes:

```text
mapping_ válido  <=>  address_ puede ser válido
address_ != null => size_ > 0
moved-from       => address_ == null y mapping_ inválido
```

Para errores parciales de construcción, conviene aplicar el patrón de guardas locales:

```cpp
auto mapping = make_mapping(...);
auto view = map_view(mapping.get(), ...);
return mapped_region(std::move(mapping), std::move(view));
```

Así, una excepción durante `MapViewOfFile` no deja el handle abierto.

### 2. Objeto Python propietario

Con pybind11, la clase puede exponerse usando `py::smart_holder`. Desde pybind11 3, `py::smart_holder` está recomendado para la mayoría de las clases porque soporta conversiones seguras entre `unique_ptr` y `shared_ptr`, transferencia de ownership y objetos derivados.[^3_2]

```cpp
namespace py = pybind11;

PYBIND11_MODULE(native_mapping, m) {
    py::class_<mapped_region, py::smart_holder>(m, "MappedRegion")
        .def(py::init<std::wstring, std::size_t, access_mode>())
        .def_property_readonly("size", &mapped_region::size)
        .def_property_readonly("readonly", &mapped_region::readonly);
}
```

La regla de ownership debe ser explícita:

- C++ crea y posee el recurso;
- Python posee el wrapper;
- el wrapper mantiene vivo el recurso;
- toda vista Python mantiene vivo el wrapper;
- ningún puntero expuesto puede sobrevivir al objeto propietario.

No se debe usar un `memoryview::from_buffer()` independiente sobre memoria que el objeto C++ podría liberar. La documentación de pybind11 advierte que esa forma no administra la vida útil del puntero y que usar la vista después de liberar el buffer produce comportamiento indefinido.[^3_3]

## Exposición mediante Buffer Protocol

La forma preferida es hacer que `MappedRegion` sea el exportador:

```cpp
py::class_<mapped_region, py::smart_holder>(
    m, "MappedRegion", py::buffer_protocol())
    .def(py::init<std::wstring, std::size_t, access_mode>())
    .def_buffer([](mapped_region& r) {
        return py::buffer_info(
            r.data(),
            1,
            "B",
            1,
            { static_cast<py::ssize_t>(r.size()) },
            { 1 }
        );
    });
```

Para una matriz tipada:

```cpp
.def_buffer([](mapped_region& r) {
    return py::buffer_info(
        r.data(),
        sizeof(double),
        py::format_descriptor<double>::format(),
        2,
        { static_cast<py::ssize_t>(r.rows()),
          static_cast<py::ssize_t>(r.cols()) },
        { static_cast<py::ssize_t>(r.cols() * sizeof(double)),
          static_cast<py::ssize_t>(sizeof(double)) }
    );
});
```

Este patrón permite que Python y NumPy consuman el buffer sin copia; la documentación de pybind11 muestra que `py::buffer_protocol()` y `def_buffer()` son la vía estándar para exponer almacenamiento C++ directamente.[^3_3]

La vista creada por Python debe conservar una referencia al objeto exportador. Esto es precisamente lo que hace el protocolo de buffers de CPython mediante `Py_buffer.obj`.[^3_1]

## Diseño recomendado para Windows

El wrapper debería separar claramente cuatro conceptos:

```cpp
struct mapping_descriptor {
    std::size_t bytes;
    std::size_t alignment;
    bool readonly;
    std::wstring name;
};

class mapped_region {
public:
    const std::byte* data() const noexcept;
    std::byte* writable_data();
    std::size_t size() const noexcept;
    bool readonly() const noexcept;

    void flush();
    void close();
};
```

`writable_data()` debe fallar si el mapping es de sólo lectura:

```cpp
std::byte* mapped_region::writable_data() {
    if (readonly_)
        throw std::logic_error("mapping is read-only");
    return static_cast<std::byte*>(address_);
}
```

No conviene exponer `HANDLE` directamente a Python. Si se requiere diagnóstico, exponer sólo un identificador no reutilizable o un objeto descriptor con semántica clara. El usuario Python no debería poder llamar `CloseHandle` manualmente mientras el buffer sigue vivo.

Para nombres Windows, la API pública C++ debe aceptar `std::wstring` o `std::u16string`. Si la interfaz Python recibe `str`, la conversión debe ocurrir dentro de pybind11 y terminar en una cadena C++ propietaria. No deben almacenarse punteros a `PyUnicode` ni a buffers temporales.

## CPython nativo frente a pybind11

| Criterio | Extensión CPython | pybind11 |
| :-- | --: | --: |
| Control ABI | Máximo | Bueno, pero depende de la versión de pybind11 |
| Verbosidad | Alta | Baja |
| RAII | Manual mediante `tp_dealloc` o C++ embebido | Natural |
| Buffer Protocol | Control total | Soporte directo |
| Smart pointers | Manual | `py::smart_holder` |
| Excepciones C++ | Conversión manual | Automática |
| Python 3.13 free-threaded | Más trabajo | Soporte específico disponible |
| Mantenibilidad | Baja-media | Alta |

La extensión CPython es preferible si se necesita Stable ABI o compatibilidad binaria amplia. El Limited API/Stable ABI de CPython está diseñado para conservar compatibilidad entre varias versiones menores de Python, evitando dependencias en estructuras internas.[^3_4]

Sin embargo, para este caso la recomendación práctica es:

- **pybind11** si el proyecto ya es C++ moderno y se controla la matriz de builds;
- **CPython Limited API** si el binario debe funcionar en varias versiones de Python sin recompilación;
- **nanobind** si la prioridad máxima es reducir overhead de binding y trabajar intensivamente con arrays.

Nanobind ofrece wrappers sin copia con ownership transferido a Python y tipos `ndarray` especializados. Es una alternativa SOTA razonable para una biblioteca numérica, pero pybind11 tiene una superficie más madura y documentación más amplia para el Buffer Protocol.[^3_5][^3_6]

## Memoria compartida y vistas seguras

La solución más robusta consiste en que la vista no sea un puntero desnudo, sino una vista vinculada al propietario:

```cpp
class mapped_view {
public:
    mapped_view(std::shared_ptr<mapped_region> owner,
                std::size_t offset,
                std::size_t length);

    const std::byte* data() const noexcept;
    std::size_t size() const noexcept;

private:
    std::shared_ptr<mapped_region> owner_;
    std::size_t offset_;
    std::size_t length_;
};
```

El binding puede retornar `mapped_view` como objeto Python con `def_buffer()`. De esta manera:

```text
MappedRegion
   └── mapped_view
         └── shared_ptr<MappedRegion>
```

Aunque el usuario elimine la referencia original a `MappedRegion`, la vista conserva el mapping activo. Esta solución es superior a almacenar sólo `void*`.

Para evitar invalidación por cierre explícito mientras existen vistas, `close()` debe tener una política definida:

1. **Cierre diferido:** marca el recurso como cerrado, pero libera físicamente cuando desaparecen las vistas.
2. **Prohibición:** lanza una excepción si existen exportaciones activas.
3. **Copia-on-close:** no recomendable para mappings grandes porque rompe el contrato zero-copy.

La primera opción suele ser la más segura para una API de alto rendimiento.

## Reglas de concurrencia

El Buffer Protocol resuelve ownership, pero no sincronización de datos. Deben definirse dos capas distintas:

### Vida útil

Garantizada por:

- `py::smart_holder`;
- `shared_ptr` en vistas;
- `Py_buffer.obj`;
- destructor RAII.


### Consistencia

Garantizada por:

- mutex o `SRWLOCK` para metadatos;
- eventos/señales para productores y consumidores;
- secuencias o versionado para detectar escrituras parciales;
- barreras de memoria;
- modo sólo lectura cuando sea posible.

Para un mapping compartido entre procesos, se recomienda un encabezado versionado:

```cpp
struct alignas(64) shared_header {
    std::uint64_t magic;
    std::uint32_t version;
    std::uint32_t state;
    std::uint64_t payload_bytes;
    std::uint64_t sequence;
};
```

El payload no debe considerarse válido sólo porque la dirección exista. El consumidor debe validar:

```text
magic
version
payload_bytes
sequence estable
checksum opcional
```

Si hay escritores concurrentes, una vista `memoryview` writable no basta para garantizar atomicidad. En particular, una operación vectorizada de NumPy puede observar un estado intermedio si el productor actualiza el mapping sin protocolo de publicación.

## Liberación del GIL

Las operaciones largas sobre el mapping pueden liberar el GIL:

```cpp
.def("flush", [](mapped_region& r) {
    py::gil_scoped_release release;
    r.flush();
});
```

No debe liberarse el GIL mientras se accede a objetos Python ni mientras se manipulan referencias Python. En pybind11, la regla general es que la API C de Python requiere el GIL; además, la biblioteca documenta soporte para builds free-threaded experimentales de Python 3.13+ mediante `py::mod_gil_not_used()`.[^3_7]

No conviene declarar `mod_gil_not_used()` simplemente para mejorar rendimiento. Sólo debe usarse después de verificar que:

- el núcleo C++ no toca objetos Python fuera del GIL;
- todos los estados compartidos están sincronizados;
- no hay cachés globales no protegidas;
- el manejo de excepciones es compatible con ejecución libre de GIL.


## Validaciones obligatorias

El binding debe rechazar explícitamente:

- tipos de elemento incompatibles;
- dimensiones inesperadas;
- strides negativos si el kernel no los soporta;
- buffers no contiguos cuando el backend exige contigüidad;
- tamaños que desborden `size_t`;
- offsets fuera del mapping;
- accesos write sobre regiones read-only;
- payloads cuyo tamaño exceda el mapping;
- versiones desconocidas del formato compartido.

Una función de validación centralizada evita que distintos métodos interpreten el mismo buffer de manera diferente:

```cpp
struct validated_buffer {
    void* ptr;
    std::size_t bytes;
    std::vector<std::size_t> shape;
    std::vector<std::ptrdiff_t> strides;
};

validated_buffer validate(py::buffer buffer,
                          scalar_type expected,
                          int ndim,
                          bool writable);
```

Para entradas externas, aceptar `py::buffer` es más general que aceptar sólo `py::array`. El consumidor debe inspeccionar `itemsize`, formato, dimensión, shape y strides antes de convertir el puntero. La documentación de pybind11 recalca que los arrays NumPy no necesariamente son densos ni contiguos.[^3_3]

## Código de referencia

Un esqueleto razonable sería:

```cpp
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <memory>
#include <stdexcept>

namespace py = pybind11;

class mapped_region {
public:
    mapped_region(std::wstring name, std::size_t bytes, bool readonly)
        : size_(bytes), readonly_(readonly) {
        if (bytes == 0)
            throw std::invalid_argument("mapping size must be positive");

        // Crear CreateFileMappingW y MapViewOfFile.
        // Todos los recursos parciales quedan protegidos por RAII.
    }

    ~mapped_region() noexcept {
        // UnmapViewOfFile y CloseHandle.
    }

    mapped_region(const mapped_region&) = delete;
    mapped_region& operator=(const mapped_region&) = delete;

    void* data() const noexcept { return address_; }
    std::size_t size() const noexcept { return size_; }
    bool readonly() const noexcept { return readonly_; }

private:
    void* address_{nullptr};
    std::size_t size_{0};
    bool readonly_{true};
};

PYBIND11_MODULE(native_mapping, m) {
    py::class_<mapped_region, py::smart_holder>(
        m, "MappedRegion", py::buffer_protocol())
        .def(py::init<std::wstring, std::size_t, bool>(),
             py::arg("name"),
             py::arg("bytes"),
             py::arg("readonly") = true)
        .def_property_readonly("size", &mapped_region::size)
        .def_property_readonly("readonly", &mapped_region::readonly)
        .def_buffer([](mapped_region& r) {
            return py::buffer_info(
                r.data(),
                1,
                "B",
                1,
                { static_cast<py::ssize_t>(r.size()) },
                { 1 }
            );
        });
}
```

Para producción faltan la implementación detallada de `CreateFileMappingW`, permisos, seguridad del nombre global, errores Win32, overflow checks, sincronización y pruebas de cierre. Pero la estructura de ownership ya es la correcta: el objeto Python contiene un propietario C++ RAII y el buffer se exporta desde ese propietario.

## Plan de migración V909

1. Extraer toda la lógica Win32 de `ctypes` a una clase C++ RAII testeable sin Python.
2. Definir una API C++ tipada con `std::wstring`, tamaños `std::size_t` y tipos de acceso explícitos.
3. Añadir move semantics y eliminar copia implícita.
4. Crear bindings pybind11 con `py::smart_holder`.
5. Exponer el recurso como Buffer Protocol, no como puntero ni `memoryview` independiente.
6. Implementar vistas con `shared_ptr` si se requieren subregiones o slices duraderos.
7. Añadir validación de formato, shape, strides y permisos.
8. Liberar el GIL sólo en operaciones largas que no toquen Python.
9. Ejecutar pruebas con AddressSanitizer, UndefinedBehaviorSanitizer y Application Verifier.
10. Añadir pruebas de vida útil: destruir el propietario antes que la vista, mover objetos, excepciones durante construcción, múltiples vistas y cierre concurrente.
11. Probar Python 3.11–3.14 y, si aplica, el build free-threaded.
12. Comparar pybind11 contra nanobind sólo después de fijar el contrato semántico; cambiar de framework no sustituye una política correcta de ownership.

La decisión recomendada para V909 es **C++ RAII + pybind11 3 + `py::smart_holder` + Buffer Protocol exportado por el objeto propietario**, reservando CPython Limited API para el caso en que la compatibilidad ABI entre versiones sea un requisito primario. Esta arquitectura elimina los dangling pointers de `ctypes`, permite zero-copy y hace que la vida útil de `CreateFileMappingW`, el mapping y las vistas Python estén gobernadas por un único contrato verificable.

<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_16][^3_17][^3_18][^3_19][^3_20][^3_21][^3_22][^3_23][^3_24][^3_25][^3_26][^3_27][^3_28][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://docs.python.org/3/c-api/buffer.html

[^3_2]: https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html

[^3_3]: https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html

[^3_4]: https://docs.python.org/3/c-api/stable.html

[^3_5]: https://nanobind.readthedocs.io/en/latest/ownership.html

[^3_6]: https://nanobind.readthedocs.io/en/latest/ndarray.html

[^3_7]: https://pybind11.readthedocs.io/en/stable/advanced/misc.html

[^3_8]: https://docs.python.org/fa/3.13/c-api/buffer.html

[^3_9]: https://pybind11.readthedocs.io/\_/downloads/en/stable/pdf/

[^3_10]: https://pybind11.readthedocs.io/\_/downloads/en/latest/pdf/

[^3_11]: https://pybind11.readthedocs.io/en/latest/advanced/smart_ptrs.html

[^3_12]: https://pybind11.readthedocs.io/en/latest/reference.html

[^3_13]: https://pybind11.readthedocs.io/en/stable/reference.html

[^3_14]: https://pybind11.readthedocs.io/en/stable/index.html

[^3_15]: https://jacobcoffee.github.io/cpython-shibuya/c-api/buffer.html

[^3_16]: https://agenda.infn.it/event/45177/contributions/275554/attachments/140917/212917/python_bindings.pdf

[^3_17]: https://wiki.python.org/jython/BufferProtocol.html

[^3_18]: http://cpython.llango.com/c-api/arg.html

[^3_19]: https://cpythonqiao.readthedocs.io/en/latest/c-api/buffer.html

[^3_20]: https://gem5.googlesource.com/public/gem5/+/2113b21996d086dab32b9fd388efe3df241bfbd2/ext/pybind11/docs/changelog.rst

[^3_21]: https://devguide.python.org/developer-workflow/c-api/index.html

[^3_22]: https://pybind11.readthedocs.io/en/latest/advanced/misc.html

[^3_23]: https://nanobind.readthedocs.io/\_/downloads/en/latest/pdf/

[^3_24]: https://nanobind.readthedocs.io/en/latest/api_core.html

[^3_25]: https://nanobind.readthedocs.io/en/latest/classes.html

[^3_26]: https://arxiv.org/html/2601.15311v2

[^3_27]: https://nanobind.readthedocs.io/en/latest/api_extra.html

[^3_28]: https://github.com/pybind/pybind11/releases


---

# 3. Deficiencia de Acumulación Estadística (CliffordNet Drift)

Brecha (V909): Se independizó raw_energy y metric_energy, e introduje constraint_residual como se solicitó, mitigando la mezcla de señales. Sin embargo, la telemetría se sigue emitiendo por epoch de forma aséptica y estática.
Requiere: Integrar algoritmos estadísticos explícitos para Series Temporales de Error (como EWMA / CUSUM) respaldados por un acumulador Neumaier temporal a través del ciclo de vida del Swarm. Medir la distancia topológica sin el acumulador compensado degrada el diagnóstico ante deriva numérica microscópica.

La mejora V909 debe convertir la telemetría de CliffordNet en un **stream estadístico persistente**, no en una colección de snapshots por epoch. La arquitectura recomendada es: separar las señales, normalizarlas contra una línea base, acumularlas con suma Neumaier y ejecutar EWMA y CUSUM sobre los residuos temporales; para señales autocorrelacionadas, primero debe monitorizarse el residuo de un modelo predictivo o un filtro de innovación, porque aplicar CUSUM directamente puede aumentar las falsas alarmas.[^5_1][^5_2]

## 1. Modelo de señales

Mantenga independientes al menos estas series:

$$
e_t^{\mathrm{raw}}=\mathrm{raw\_energy}_t,
$$

$$
e_t^{\mathrm{metric}}=\mathrm{metric\_energy}_t,
$$

$$
r_t^{\mathrm{constraint}}
=
\lVert C(X_t)\rVert,
$$

$$
d_t^{\mathrm{topo}}
=
\operatorname{dist}\bigl(\mathcal{T}(X_t),\mathcal{T}_{\mathrm{ref}}\bigr).
$$

No debe alimentarse un único detector con la suma cruda de las cuatro métricas. Cada señal tiene una semántica distinta:


| Señal | Qué mide | Riesgo estadístico |
| :-- | :-- | :-- |
| `raw_energy` | Magnitud física o algebraica sin transformar | Escala y outliers |
| `metric_energy` | Energía de la métrica elegida | Cambio de escala por estado |
| `constraint_residual` | Violación de la restricción | Sesgo por redondeo |
| `topological_distance` | Separación estructural o geométrica | Cancelación numérica y deriva lenta |

Para comparar señales, use residuos normalizados:

$$
z_t^{(j)}
=
\frac{x_t^{(j)}-\mu_0^{(j)}}{\max(\sigma_0^{(j)},\sigma_{\min}^{(j)})}.
$$

La referencia $\mu_0^{(j)}$ y la escala $\sigma_0^{(j)}$ deben congelarse durante una ventana de calibración o actualizarse muy lentamente. Si se actualizan demasiado rápido, el detector puede absorber la deriva que debería señalar.

## 2. Acumulador Neumaier persistente

La suma temporal no debe reiniciarse al terminar cada epoch. Mantenga un acumulador por serie durante toda la vida del Swarm:

```cpp
struct NeumaierAccumulator {
    double sum = 0.0;
    double correction = 0.0;
    std::uint64_t count = 0;

    void add(double x) noexcept {
        const double t = sum + x;

        if (std::abs(sum) >= std::abs(x))
            correction += (sum - t) + x;
        else
            correction += (x - t) + sum;

        sum = t;
        ++count;
    }

    double value() const noexcept {
        return sum + correction;
    }
};
```

La variante de Neumaier mejora la acumulación de Kahan-Babuška cuando los términos tienen magnitudes muy diferentes; los análisis de sumación compensada muestran un comportamiento comparable al de calcular con precisión aproximadamente doble y redondear al final. Esto resulta especialmente relevante para `constraint_residual` y distancia topológica, donde pueden coexistir términos grandes y correcciones microscópicas.[^5_3][^5_4]

Debe existir un acumulador por señal y, si hay múltiples nodos o workers, un acumulador por partición:

```cpp
struct TemporalTelemetry {
    NeumaierAccumulator raw_energy;
    NeumaierAccumulator metric_energy;
    NeumaierAccumulator constraint_residual;
    NeumaierAccumulator topological_distance;

    std::uint64_t epoch = 0;
};
```

Para reducción distribuida, no se deben sumar valores finales ya redondeados si se busca máxima reproducibilidad. Hay dos opciones:

1. fusionar pares `(sum, correction, count)` con una operación compensada;
2. almacenar bins superaccumulator/long accumulator para reproducibilidad bit a bit.

La segunda opción es más costosa, pero resulta preferible si la telemetría se usa como criterio de regresión científica.

## 3. EWMA para deriva gradual

Para cada señal normalizada $z_t$, mantenga:

$$
m_t=(1-\lambda)m_{t-1}+\lambda z_t,
\qquad 0<\lambda\leq 1.
$$

Un $\lambda$ pequeño conserva memoria larga y detecta desviaciones graduales; uno grande responde más rápido y se acerca al comportamiento de una medición instantánea. Una configuración inicial razonable es:[^5_5]

- $\lambda=0.05$: deriva muy lenta;
- $\lambda=0.1$: monitorización general;
- $\lambda=0.2$: respuesta rápida.

No conviene elegir $\lambda$ sólo por intuición. Debe calibrarse con el tiempo de respuesta deseado:

$$
N_{\mathrm{efectivo}}\approx \frac{2-\lambda}{\lambda}.
$$

La varianza transitoria del EWMA bajo observaciones independientes puede aproximarse mediante:

$$
\sigma_{m,t}^{2}
=
\sigma_0^2
\frac{\lambda}{2-\lambda}
\left[1-(1-\lambda)^{2t}\right].
$$

Por tanto, los límites pueden definirse como:

$$
U_t=\mu_0+L\sigma_{m,t},
\qquad
L_t=\mu_0-L\sigma_{m,t}.
$$

Esta forma de límites transitorios está documentada en los esquemas EWMA de control estadístico.[^5_6][^5_7]

Para telemetría multidimensional, no use únicamente cuatro alarmas independientes. Mantenga:

$$
M_t^{\mathrm{EWMA}}
=
\sum_j w_j
\left(
\frac{m_t^{(j)}-\mu_0^{(j)}}{\sigma_{m,t}^{(j)}}
\right)^2,
$$

pero conserve también las alarmas individuales. La métrica agregada detecta deriva coordinada; la individual identifica la causa.

## 4. CUSUM para cambios persistentes

Para detectar un desplazamiento pequeño pero sostenido, use dos CUSUM unilaterales sobre la señal estandarizada:

$$
G_t^+
=
\max\left(
0,\,
G_{t-1}^+ + z_t-k
\right),
$$

$$
G_t^-
=
\max\left(
0,\,
G_{t-1}^- -z_t-k
\right).
$$

Señale alarma si:

$$
G_t^+>h
\quad\text{o}\quad
G_t^->h.
$$

Aquí $k$ es el valor de referencia que filtra ruido y $h$ es el umbral de decisión. CUSUM acumula evidencia en una dirección, mientras que EWMA suaviza con memoria exponencial; ambos son adecuados para desplazamientos pequeños que un detector instantáneo puede ignorar.[^5_8][^5_5]

Una parametrización inicial en unidades de desviación estándar es:

$$
k=\frac{\delta}{2},
$$

donde $\delta$ es el cambio mínimo que se desea detectar, y $h$ se calibra mediante simulación para lograr el nivel de falsas alarmas requerido. No debe asumirse que los valores clásicos de $h$ funcionan igual en el Swarm: la autocorrelación, el tamaño de lote y el número de señales cambian el promedio de tiempo hasta la falsa alarma.

Después de una alarma, el reset puede ser:

```cpp
G_plus  = 0.0;
G_minus = 0.0;
```

Pero conviene guardar además:

```text
alarm_epoch
alarm_direction
peak_statistic
last_reset_epoch
```

El reset no debe borrar el historial compensado ni la línea base científica.

## 5. Autocorrelación y residuos

La telemetría por epoch normalmente no es independiente: el estado del Swarm en $t$ depende del estado en $t-1$. Aplicar EWMA o CUSUM directamente sobre $x_t$ puede producir falsas alarmas porque los puntos consecutivos contienen información repetida. La literatura de control estadístico advierte que la autocorrelación reduce el average run length bajo control y aumenta las falsas alarmas.[^5_2][^5_9]

La solución preferida es monitorizar innovaciones:

$$
\hat{x}_t = \phi_1 x_{t-1}+\cdots+\phi_p x_{t-p},
$$

$$
\varepsilon_t=x_t-\hat{x}_t.
$$

Entonces EWMA y CUSUM operan sobre:

$$
z_t=\frac{\varepsilon_t-\mu_\varepsilon}
{\max(\sigma_\varepsilon,\sigma_{\min})}.
$$

Para una implementación ligera, puede comenzar con AR(1):

$$
\hat{x}_t=\phi x_{t-1},
\qquad
\varepsilon_t=x_t-\phi x_{t-1}.
$$

Estime $\phi$ sólo durante la fase de calibración o con una adaptación lenta. No conviene estimar el modelo al mismo ritmo que el detector, porque el predictor podría seguir la deriva y reducir artificialmente la señal.

## 6. Estado persistente del Swarm

El estado estadístico debe pertenecer al ciclo de vida del Swarm, no al objeto temporal del epoch:

```cpp
struct SignalDetector {
    NeumaierAccumulator total;
    std::uint64_t n = 0;

    double mean0 = 0.0;
    double sigma0 = 1.0;

    double ewma = 0.0;
    double cusum_pos = 0.0;
    double cusum_neg = 0.0;

    double previous = 0.0;
    double ar_phi = 0.0;

    bool initialized = false;
    bool alarm = false;
    std::uint64_t alarm_epoch = 0;

    void update(double x, std::uint64_t epoch);
};
```

La actualización debería seguir esta secuencia:

```text
1. Validar finitud y rango.
2. Actualizar el acumulador Neumaier con el valor físico.
3. Calcular predicción temporal.
4. Formar innovación/residuo.
5. Normalizar con la línea base.
6. Actualizar EWMA.
7. Actualizar CUSUM superior e inferior.
8. Registrar alarmas y estadísticas.
9. Publicar telemetría.
```

La telemetría emitida por epoch debe ser sólo una instantánea de un estado persistente:

```json
{
  "epoch": 1204,
  "raw_energy": {
    "value": 0.000031,
    "ewma": 0.42,
    "cusum_pos": 0.08,
    "cusum_neg": 0.00,
    "z": 0.37
  },
  "constraint_residual": {
    "value": 2.1e-12,
    "compensated_total": 8.7e-9,
    "ewma": 1.84,
    "cusum_pos": 3.92,
    "alarm": false
  },
  "topological_distance": {
    "value": 6.4e-13,
    "ewma": 2.13,
    "cusum_pos": 4.71,
    "alarm": true
  }
}
```


## 7. Actualización numéricamente estable

No conviene acumular directamente una serie de cuadrados mediante:

$$
E[x^2]-E[x]^2,
$$

porque esa resta puede sufrir cancelación catastrófica. Para media y varianza online, use una actualización tipo Welford, combinada con compensación cuando el volumen sea alto. Welford evita restar dos cantidades grandes casi iguales y es reconocido como una alternativa estable para varianza de una pasada.[^5_10][^5_11]

Una versión simplificada:

```cpp
struct OnlineMoments {
    std::uint64_t n = 0;
    double mean = 0.0;
    double m2 = 0.0;

    void add(double x) noexcept {
        ++n;
        const double delta = x - mean;
        mean += delta / static_cast<double>(n);
        const double delta2 = x - mean;
        m2 += delta * delta2;
    }

    double variance() const noexcept {
        return n > 1 ? m2 / static_cast<double>(n - 1) : 0.0;
    }
};
```

Una configuración robusta para CliffordNet sería:

- `NeumaierAccumulator`: suma de energía, residuos y distancia;
- `OnlineMoments`: estimación de escala durante warm-up;
- EWMA: detección de deriva gradual;
- CUSUM bilateral: cambio persistente direccional;
- AR(1) o innovación: corrección de autocorrelación;
- Mahalanobis o suma de scores: alarma multivariada.


## 8. Calibración y alarmas

La fase inicial debe dividirse en dos etapas:

### Warm-up

Durante $T_0$ epochs:

- acumular estadísticas;
- estimar $\mu_0$, $\sigma_0$ y autocorrelación;
- no disparar alarmas definitivas;
- registrar valores extremos;
- verificar que la restricción sea físicamente válida.


### Operación

Después de $T_0$:

- congelar o ralentizar la línea base;
- activar EWMA y CUSUM;
- emitir alarmas sólo después de confirmación;
- registrar la trayectoria completa del estadístico.

Para reducir falsos positivos, use una regla de confirmación:

```text
alarma inmediata si constraint_residual excede un límite duro;
alarma estadística si EWMA y CUSUM coinciden;
alarma sistémica si dos señales independientes exceden sus límites.
```

No mezcle un error duro de seguridad con una alerta estadística blanda. Por ejemplo:

$$
r_t^{\mathrm{constraint}}>r_{\max}
$$

debe ser una condición determinista, mientras que una deriva microscópica puede requerir varios epochs de evidencia acumulada.

## 9. Pruebas científicas

La validación debe incluir streams sintéticos con ground truth:

1. Ruido estacionario sin deriva.
2. Cambio abrupto de media.
3. Deriva lineal lenta.
4. Deriva microscópica cercana a $10^{-12}$ o al epsilon efectivo.
5. Cambio de varianza.
6. Autocorrelación AR(1).
7. Outliers aislados.
8. Cambio simultáneo en `raw_energy` y `constraint_residual`.
9. Cancelación entre valores positivos y negativos.
10. Reinicio, checkpoint y restauración del Swarm.

Mida:

- detección verdadera;
- falsas alarmas;
- tiempo hasta detección;
- average run length bajo control;
- estabilidad frente al orden de reducción;
- diferencia entre suma ingenua y Neumaier;
- reproducibilidad CPU/GPU;
- memoria por entidad observada.

El criterio de aceptación no debe ser sólo “detecta la deriva”. Debe exigir que el detector mantenga una tasa de falsa alarma calibrada bajo el proceso nominal y que la señal compensada preserve diferencias que desaparecen con acumulación convencional.

## Implementación objetivo

La modificación V909 puede resumirse así:

```text
raw_energy              -> SignalDetector
metric_energy           -> SignalDetector
constraint_residual     -> SignalDetector
topological_distance    -> SignalDetector

cada epoch:
    medir valores físicos
    actualizar Neumaier persistentemente
    calcular innovación temporal
    normalizar
    actualizar EWMA y CUSUM
    evaluar reglas de alarma
    emitir snapshot estadístico
```

El cambio clave es que `constraint_residual` y `topological_distance` dejan de ser sólo valores puntuales. Pasan a tener memoria numérica y estadística durante todo el ciclo de vida del Swarm. Neumaier conserva la señal acumulada frente a cancelaciones microscópicas, EWMA detecta deriva gradual y CUSUM acumula evidencia direccional; juntos forman una telemetría científicamente más defendible que la emisión estática por epoch.[^5_12][^5_3][^5_6]

<span style="display:none">[^5_13][^5_14][^5_15][^5_16][^5_17][^5_18][^5_19][^5_20][^5_21][^5_22][^5_23][^5_24][^5_25][^5_26][^5_27][^5_28][^5_29][^5_30][^5_31][^5_32][^5_33][^5_34][^5_35][^5_36][^5_37][^5_38][^5_39][^5_40][^5_41][^5_42][^5_43][^5_44][^5_45]</span>

<div align="center">⁂</div>

[^5_1]: https://www.sfu.ca/sasdoc/sashtml/qc/chap49/sect4.htm

[^5_2]: https://www.ijmo.org/vol5/449-Q004.pdf

[^5_3]: https://www.tuhh.de/ti3/paper/rump/Ru05d.pdf

[^5_4]: https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf

[^5_5]: https://analyse-it.com/learn/cusum-and-ewma-charts

[^5_6]: https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm

[^5_7]: https://hightechjournal.org/index.php/HIJ/article/download/1162/332/3874

[^5_8]: http://www.stat.umn.edu/hawkins/5031/Hawkins_Wu_2014.pdf

[^5_9]: https://link.springer.com/article/10.1023/A:1007623715556?error=cookies_not_supported\&code=5def54ba-47bf-4e66-93d4-fc959b1a89c3

[^5_10]: https://metafunctor.com/latex/accumux/accumux_paper.pdf

[^5_11]: https://www.bitavox.com/chapters/5

[^5_12]: https://arxiv.org/html/2406.08030v3

[^5_13]: https://cran.r-project.org/web/packages/heimdall/heimdall.pdf

[^5_14]: https://www.mccormick.northwestern.edu/research/deep-learning/documents/publications/drift_detection.pdf

[^5_15]: https://pure.uva.nl/ws/files/1813477/110224_3.\_Mixed_EWMA_CUSUM_charts.pdf

[^5_16]: https://www.cambridge.org/core/services/aop-cambridge-core/content/view/D2C12700B525EDF651B00D11155723D4/S0033312326101409a.pdf/real-time-monitoring-of-item-parameter-drift-in-cd-cat-via-adaptive-cusum-charts.pdf

[^5_17]: https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2022.955314/full

[^5_18]: https://ar5iv.labs.arxiv.org/html/1212.6018

[^5_19]: https://en.wikipedia.org/wiki/Flaoting-point_summation

[^5_20]: https://jantsch.se/AxelJantsch/papers/2024/AlirezaEstaji-TII.pdf

[^5_21]: https://www.scribd.com/document/963557583/cusum-3

[^5_22]: https://openmoa.net/docs/tutorials/drift.html

[^5_23]: https://metricgate.com/blogs/cusum-vs-ewma-change-detection/

[^5_24]: https://www.ijbmi.org/papers/Vol(8)4/Series-5/K0804057783.pdf

[^5_25]: https://epubs.siam.org/doi/abs/10.1137/050645671

[^5_26]: https://dl.acm.org/doi/10.1137/07068816X

[^5_27]: https://www.tuhh.de/ti3/paper/rump/RuOgOi07II.pdf

[^5_28]: https://www.cambridge.org/core/journals/acta-numerica/article/abs/verification-methods-rigorous-results-using-floatingpoint-arithmetic/770FE58E5293985CCAB770AF09C4F3FF

[^5_29]: https://www.tuhh.de/ti3/paper/rump/OgRuOi04a.pdf

[^5_30]: https://www.tuhh.de/ti3/paper/rump/RuOgOi07I.pdf

[^5_31]: https://hal.science/hal-02265534v3/document

[^5_32]: https://arxiv.org/pdf/2107.01604.pdf

[^5_33]: https://www.cambridge.org/core/journals/acta-numerica/article/floatingpoint-arithmetic/287C4D5F6D4A43FBEEB1ABED2A405AAF

[^5_34]: https://hal.science/hal-01233879/file/cse13_sl.pdf

[^5_35]: https://hal.science/hal-02265534v1/document

[^5_36]: https://hal.science/hal-01963634v1/file/HAL.pdf

[^5_37]: https://docslib.org/doc/12947480/accurate-floating-point-summation-part-i-faithful-rounding

[^5_38]: https://taylorandfrancis.com/knowledge/Engineering_and_technology/Engineering_support_and_special_topics/CUSUM/

[^5_39]: http://eprints.utm.my/54897/1/AbbasUmarFaroukPFS2015.pdf

[^5_40]: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance

[^5_41]: https://scispace.com/pdf/real-time-statistical-process-control-for-autocorrelated-2a178y6n.pdf

[^5_42]: https://pdfs.semanticscholar.org/2491/af049bb5e4e324b82668bf7027f23b3b756e.pdf

[^5_43]: https://www.johndcook.com/blog/2026/05/29/online-one-pass-algorithms/

[^5_44]: https://www.research.unipd.it/retrieve/e14fb270-3211-3de1-e053-1705fe0ac030/2007_19_20071221140144.pdf

[^5_45]: https://krtffl.dev/posts/welford-online-variance-rust/


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La evolución SOTA para CliffordNet no debería limitarse a añadir EWMA y CUSUM. La solución científicamente más sólida es una arquitectura de **detección secuencial por capas**: acumulación numérica reproducible, modelado explícito de autocorrelación, detectores complementarios para deriva abrupta y gradual, y un contrato de telemetría que distinga estado acumulado de observaciones delta.

## Arquitectura SOTA propuesta

El pipeline recomendado es:

$$
\text{medición física}
\rightarrow
\text{validación}
\rightarrow
\text{acumulación compensada}
\rightarrow
\text{innovación temporal}
\rightarrow
\text{normalización robusta}
\rightarrow
\begin{cases}
\text{EWMA}\\
\text{CUSUM}\\
\text{BOCPD}\\
\text{conformal martingale}
\end{cases}
\rightarrow
\text{fusión de evidencias}
\rightarrow
\text{alarma y diagnóstico}.
$$

Esto evita mezclar tres fenómenos diferentes:

- error de redondeo;
- cambio estadístico del proceso;
- cambio semántico o topológico del estado.

La separación es esencial: un incremento de `topological_distance` no debe interpretarse igual que un incremento de `raw_energy`.

## 1. Sustituir la suma compensada por una jerarquía numérica

Neumaier debe seguir siendo el acumulador de bajo coste, pero no necesariamente el último nivel de precisión.

### Nivel operativo

Para cada métrica, mantener:

```cpp
struct StableAccumulator {
    double sum;
    double correction;
    std::uint64_t count;
};
```

Adecuado para:

- telemetría cotidiana;
- EWMA y CUSUM;
- ejecuciones donde la reproducibilidad bit a bit no sea obligatoria.


### Nivel reproducible

Para validación científica, regresiones y comparación CPU/GPU, añadir un modo `deterministic` basado en expansiones de punto flotante o superacumulador.

ExBLAS combina transformaciones libres de error, expansiones de punto flotante y acumuladores largos para lograr resultados reproducibles independientemente del árbol de reducción y del orden de los datos. Los superacumuladores pueden alcanzar suma exacta y reproducible para rangos dinámicos muy amplios, con implementaciones para CPU y GPU.[^6_1][^6_2][^6_3][^6_4]

La recomendación práctica es:

```text
fast mode:
    Neumaier por thread/block
    reducción compensada

audit mode:
    floating-point expansion
    superaccumulator para métricas críticas
    resultado reproducible bit a bit
```

Usaría `audit mode` para:

- `constraint_residual`;
- `topological_distance`;
- benchmarks de deriva;
- validación de kernels GPU;
- comparación de versiones del solver.

No conviene usar un superacumulador para toda la telemetría si el coste de ancho de banda domina. La solución SOTA es híbrida: filtro rápido y escalado al acumulador largo sólo cuando la expansión deja de ser suficiente.[^6_5]

## 2. Estadística robusta antes del detector

EWMA y CUSUM clásicos suponen que la escala del ruido es conocida o relativamente estable. CliffordNet puede generar outliers por:

- reinicios parciales;
- cambios de precisión;
- spikes de comunicación;
- iteraciones Krylov no convergentes;
- cambios de régimen del Swarm.

Por ello, la línea base debe usar estadística robusta:

$$
m_t = \operatorname{median}(x_{t-w+1:t}),
$$

$$
s_t = 1.4826\operatorname{median}
\left(\lvert x_i-m_t\rvert\right).
$$

Después:

$$
z_t =
\frac{x_t-m_t}
{\max(s_t,s_{\min})}.
$$

La mediana y MAD pueden implementarse con:

- ventana acotada y selección rápida;
- t-digest o KLL para distribución;
- cuantiles exponencialmente ponderados;
- estimación robusta por bloques.

No se debe actualizar la línea base robusta con la misma velocidad que EWMA si la línea base también participa en la decisión. Una configuración segura es:

```text
baseline: ventana larga o actualización lenta
detector: ventana corta o memoria intermedia
```

De lo contrario, el detector aprende la deriva y deja de verla.

## 3. Modelado de autocorrelación

Antes de ejecutar detectores secuenciales, modelar la dependencia temporal:

$$
x_t = \sum_{i=1}^{p}\phi_i x_{t-i}+\varepsilon_t.
$$

El detector recibe la innovación:

$$
\varepsilon_t=x_t-\hat{x}_t.
$$

Una versión eficiente para streaming es AR(1):

$$
\hat{x}_t=\phi x_{t-1}.
$$

Para mayor robustez:

- estimar $\phi$ durante warm-up;
- congelarlo durante una ventana de decisión;
- recalibrarlo sólo tras una alarma confirmada;
- no reajustarlo inmediatamente después de cada observación.

Cuando el proceso tiene cambios de varianza, usar una escala adaptativa:

$$
z_t =
\frac{\varepsilon_t}
{\sqrt{\widehat{\operatorname{Var}}(\varepsilon_t)}}.
$$

La autocorrelación ignorada reduce la longitud media hasta una falsa alarma; esto está documentado para CUSUM y otros gráficos de control aplicados a series dependientes.[^6_6][^6_7]

## 4. Detector multiescala

Un único $\lambda$ en EWMA no cubre todos los modos de deriva. Mantener una batería:

$$
m_t^{(s)}=(1-\lambda_s)m_{t-1}^{(s)}+\lambda_s z_t,
$$

con, por ejemplo:

```text
λ = 0.01  deriva muy lenta
λ = 0.05  deriva lenta
λ = 0.20  cambio moderadamente rápido
λ = 0.50  respuesta casi inmediata
```

Fusionar mediante:

$$
S_t^{\mathrm{EWMA}}
=
\max_s
\left|
\frac{m_t^{(s)}}{\sigma_s}
\right|.
$$

Esto funciona como un banco de filtros temporales: una deriva sostenida activa el EWMA lento; un cambio rápido activa el EWMA rápido.

Para CUSUM, mantener al menos dos escalas:

$$
G_{t,s}^{+}
=
\max(0,G_{t-1,s}^{+}+z_t-k_s),
$$

$$
G_{t,s}^{-}
=
\max(0,G_{t-1,s}^{-}-z_t-k_s).
$$

La combinación EWMA-CUSUM es especialmente adecuada porque ambos detectores acumulan evidencia de formas distintas: EWMA pondera temporalmente las observaciones y CUSUM acumula exceso respecto de un cambio de referencia.[^6_8][^6_9]

## 5. BOCPD como detector de cambio de régimen

Para distinguir una deriva continua de un cambio de régimen, añadir Bayesian Online Change-Point Detection.

El estado principal es la distribución del *run length*:

$$
r_t = \text{número de observaciones desde el último cambio}.
$$

El algoritmo actualiza:

$$
P(r_t\mid x_{1:t})
$$

en cada observación. La probabilidad de cambio es:

$$
P(r_t=0\mid x_{1:t}).
$$

Una implementación completa puede crecer con el tiempo, pero se puede imponer un `max_run_length = R`. Con ese límite, la memoria y el coste por observación se mantienen acotados; las implementaciones online descritas para streams no acotados usan precisamente esta truncación del posterior.[^6_10][^6_11]

BOCPD aporta información que EWMA/CUSUM no tienen directamente:

```text
probabilidad de cambio
régimen actual
duración del régimen
distribución predictiva
```

Debe usarse como detector de diagnóstico, no como único mecanismo de seguridad. El prior de hazard puede ser:

$$
H=\frac{1}{L},
$$

donde $L$ es la duración media esperada de un régimen. Para un Swarm que cambia con frecuencia, $L$ debe ser menor; para una simulación estacionaria, mayor.

## 6. Conformal martingales para control de falsas alarmas

Si CliffordNet posee un predictor razonable de la próxima observación, puede construirse un score no conformista:

$$
a_t = \lvert x_t-\hat{x}_t\rvert.
$$

Comparando $a_t$ con una ventana de scores históricos, obtener un p-value conformal $p_t$. Luego acumular evidencia mediante una martingala:

$$
M_t=M_{t-1}g(p_t),
$$

donde $g$ asigna mayor peso a p-values pequeños.

La idea es diferente de CUSUM: no presupone una distribución paramétrica concreta de los residuos, y permite convertir anomalías secuenciales en evidencia acumulada. Bajo exchangeability, las martingalas conformales proporcionan una interpretación de control de error de primer tipo. Para series dependientes, la exchangeability no es automática; deben usarse residuos preblanqueados, bloques o una calibración temporal apropiada.[^6_12]

Aplicación recomendada:

```text
EWMA/CUSUM:
    baja latencia y control operativo

BOCPD:
    inferencia de cambio de régimen

conformal martingale:
    evidencia estadística y validación de falsas alarmas
```

No conviene fusionar sus números sin calibración. Cada detector debe conservar su semántica y la fusión debe realizarse por política.

## 7. Fusión de evidencias

Definir estados de alarma en vez de un único booleano:

```text
NORMAL
WATCH
DRIFT_SUSPECTED
DRIFT_CONFIRMED
HARD_VIOLATION
RECOVERY
```

Una política posible:

$$
\text{DRIFT\_SUSPECTED}
\iff
S_{\mathrm{EWMA}}>u_1
$$

$$
\text{DRIFT\_CONFIRMED}
\iff
S_{\mathrm{CUSUM}}>u_2
\land
P_{\mathrm{BOCPD}} > u_3
$$

$$
\text{HARD\_VIOLATION}
\iff
r_t^{\mathrm{constraint}}>r_{\max}
$$

La distancia topológica puede elevar una alerta de `DRIFT_SUSPECTED` a `DRIFT_CONFIRMED`, pero no debería por sí sola invalidar el proceso a menos que tenga un límite físico o geométrico certificado.

También se puede usar una fusión logarítmica:

$$
S_t =
w_E S_t^{\mathrm{EWMA}}
+
w_C S_t^{\mathrm{CUSUM}}
+
w_B \log\frac{P_{\mathrm{BOCPD}}}
{1-P_{\mathrm{BOCPD}}}
+
w_M\log M_t.
$$

Los pesos deben calibrarse sobre streams nominales y con derivas inyectadas. No deben fijarse sólo por conveniencia.

## 8. Tratamiento específico de la distancia topológica

La métrica topológica requiere especial cuidado. Si se calcula como diferencia entre cantidades próximas, el resultado puede perder precisión:

$$
d = f(X_t)-f(X_{\mathrm{ref}}).
$$

Mejor usar, cuando sea posible, una formulación estable directamente sobre la diferencia:

$$
d = \|g(X_t,X_{\mathrm{ref}})\|,
$$

evitando restar dos energías grandes. Si la distancia deriva de subespacios, considerar:

- ángulos principales;
- distancia geodésica;
- norma de proyección;
- residual de una descomposición QR/SVD;
- métrica logarítmica si la geometría lo requiere.

La acumulación debe ejecutarse sobre la métrica final físicamente interpretada, no sobre términos intermedios que pueden cancelarse.

Registrar además dos valores:

```text
topological_distance_raw
topological_distance_compensated
```

y, opcionalmente:

```text
topological_distance_error_bound
```

El último puede estimarse con una expansión compensada o con un bound derivado de las operaciones elementales. Esto permite distinguir:

```text
distancia observada > error numérico estimado
```

de:

```text
distancia observada compatible con redondeo
```


## 9. Telemetría con semántica temporal correcta

La telemetría debe distinguir tres clases:

### Gauge

Estado instantáneo:

```text
constraint_residual
topological_distance
ewma_score
cusum_score
```


### Sum acumulativa

Cantidad acumulada desde el inicio:

```text
raw_energy_integral
compensated_error_sum
number_of_samples
```


### Delta

Contribución desde la última exportación:

```text
epoch_energy_delta
new_alarm_count
new_constraint_violations
```

OpenTelemetry define explícitamente la diferencia entre temporalidad acumulativa y delta: la acumulativa cubre desde un instante inicial fijo, mientras que la delta cubre intervalos sucesivos sin solapamiento. Si se emite un acumulador Neumaier como si fuera una medición instantánea, el consumidor puede interpretar erróneamente la telemetría.[^6_13][^6_14]

Para CliffordNet, recomiendo:

```text
gauges:
    current residuals and detector scores

cumulative:
    compensated totals and sample count

delta:
    epoch contribution and event counts
```

Cada stream debe tener:

```text
start_time
timestamp
epoch
swarm_id
run_id
detector_version
baseline_version
numeric_mode
```

La `baseline_version` es importante: sin ella no se puede saber si dos alarmas fueron calculadas contra la misma referencia.

## 10. Estado de detector persistente

Una estructura de producción puede ser:

```cpp
struct DetectorState {
    std::uint64_t epoch = 0;
    std::uint64_t baseline_version = 0;

    NeumaierAccumulator total;
    OnlineMoments moments;

    double baseline_mean = 0.0;
    double baseline_scale = 1.0;
    double ar_phi = 0.0;
    double previous = 0.0;

    std::array<double, 4> ewma{};
    std::array<double, 4> cusum_pos{};
    std::array<double, 4> cusum_neg{};

    double bocpd_change_probability = 0.0;
    double conformal_martingale = 1.0;

    DetectorStatus status = DetectorStatus::Warmup;
};
```

La actualización debe ser transaccional desde el punto de vista de la telemetría. No se debe publicar `ewma` nuevo junto con `cusum` viejo. Usar:

```text
measure local
update all detector state
commit snapshot
publish immutable snapshot
```

En GPU, acumular localmente por warp o block y reducir al host sólo el estado pequeño. No transferir la serie completa. Para auditoría, conservar muestras escasas de los epochs que causaron cambios de estado.

## 11. Checkpoint y recuperación

El estado estadístico es parte del estado científico del Swarm. Debe serializarse en checkpoints:

```text
accumulator.sum
accumulator.correction
accumulator.count
baseline_mean
baseline_scale
EWMA states
CUSUM states
AR parameters
BOCPD run-length posterior
martingale value
alarm state
baseline version
numeric mode
```

Si sólo se restaura el estado físico y se reinicia EWMA/CUSUM, se produce una discontinuidad estadística que puede ocultar una deriva real o crear una falsa alarma.

Al restaurar:

1. verificar versión de esquema;
2. comprobar finitud;
3. comprobar que `count` y `epoch` sean monotónicos;
4. invalidar el checkpoint si la baseline version no coincide;
5. registrar un evento de recuperación.

## 12. Diseño experimental para validar SOTA

Construir un benchmark sintético con cinco familias:


| Escenario | Objetivo |
| :-- | :-- |
| Gaussiano estacionario | Falsas alarmas |
| AR(1) estacionario | Robustez ante autocorrelación |
| Drift lineal | Detección gradual |
| Cambio abrupto | Latencia de detección |
| Cancelación numérica | Sensibilidad del acumulador |

Comparar:

```text
suma ingenua
Kahan
Neumaier
floating-point expansion
superaccumulator
```

y:

```text
Shewhart
EWMA
CUSUM
EWMA multiescala
BOCPD
conformal martingale
fusión híbrida
```

Las métricas principales son:

- false alarm rate;
- average run length bajo control;
- detection delay;
- precisión de localización del cambio;
- memoria por señal;
- coste por epoch;
- divergencia CPU/GPU;
- sensibilidad al orden de reducción;
- estabilidad al reiniciar desde checkpoint.

El benchmark debe incluir un modo “truth injection”, donde se conozca exactamente:

```text
epoch de inicio de deriva
magnitud
dirección
duración
señal afectada
```

Sin ese ground truth, un detector que dispara más alarmas puede parecer mejor aunque sólo sea más ruidoso.

## Recomendación final para V910/V909

La implementación priorizada sería:

### Fase 1: corrección numérica

- Neumaier persistente por métrica.
- Welford para escala.
- AR(1) para innovaciones.
- EWMA multiescala y CUSUM bilateral.
- estado persistente y checkpoint.


### Fase 2: robustez científica

- MAD o cuantiles para baseline robusta.
- BOCPD truncado para cambios de régimen.
- fusión explícita de evidencia.
- modo de auditoría con expansión de punto flotante.


### Fase 3: reproducibilidad y distribución

- superacumulador tipo ExBLAS para `constraint_residual` y distancia topológica;
- reducción determinista CPU/GPU;
- telemetría OpenTelemetry con gauge, cumulative y delta correctamente separados;
- pruebas de falsos positivos y detección en streams autocorrelacionados.

La combinación más equilibrada para producción es:

$$
\boxed{
\text{Neumaier}
+
\text{AR residual}
+
\text{EWMA multiescala}
+
\text{CUSUM}
+
\text{BOCPD diagnóstico}
+
\text{superacumulador en modo auditoría}
}
$$

Esto transforma CliffordNet de una telemetría descriptiva en un sistema de monitorización secuencial, numéricamente reproducible y capaz de diferenciar ruido de máquina, deriva microscópica, cambio de régimen y violación real de las restricciones.

<span style="display:none">[^6_15][^6_16][^6_17][^6_18][^6_19][^6_20][^6_21][^6_22][^6_23][^6_24][^6_25][^6_26][^6_27][^6_28][^6_29][^6_30][^6_31][^6_32][^6_33][^6_34][^6_35][^6_36][^6_37][^6_38][^6_39][^6_40][^6_41][^6_42][^6_43][^6_44][^6_45][^6_46][^6_47][^6_48]</span>

<div align="center">⁂</div>

[^6_1]: https://www.nist.gov/system/files/documents/itl/ssd/is/NRE-2015-04-iakymchuk.pdf

[^6_2]: https://backend.orbit.dtu.dk/ws/portalfiles/portal/254095184/JCAM_R3_Reproducible_PCG_12.pdf

[^6_3]: https://hal.science/hal-01202396v3/document

[^6_4]: https://hal.science/hal-00949355v2/file/superaccumulator.pdf

[^6_5]: https://theses.hal.science/tel-02025855/file/These Finale.pdf

[^6_6]: https://link.springer.com/article/10.1023/A:1007623715556?error=cookies_not_supported\&code=5def54ba-47bf-4e66-93d4-fc959b1a89c3

[^6_7]: https://www.ijmo.org/vol5/449-Q004.pdf

[^6_8]: http://www.stat.umn.edu/hawkins/5031/Hawkins_Wu_2014.pdf

[^6_9]: https://pure.uva.nl/ws/files/1813477/110224_3.\_Mixed_EWMA_CUSUM_charts.pdf

[^6_10]: https://ar5iv.labs.arxiv.org/html/2201.03710

[^6_11]: https://github.com/hildensia/bayesian_changepoint_detection

[^6_12]: https://arxiv.org/html/2605.13642v3

[^6_13]: https://opentelemetry.io/docs/specs/otel/metrics/data-model/

[^6_14]: https://opentelemetry.io/docs/specs/otel/metrics/data-model/index.md

[^6_15]: https://www2.eecs.berkeley.edu/Pubs/TechRpts/2015/EECS-2015-229.pdf

[^6_16]: https://link.springer.com/article/10.1007/s41060-024-00620-y?error=cookies_not_supported\&code=4083ed9a-78e8-43f0-96a6-f68f1cb69e7a

[^6_17]: https://hal.science/hal-00949355v1/preview/superaccumulator.pdf

[^6_18]: https://hal.science/hal-00949355v1/document

[^6_19]: https://arxiv.org/html/2005.07282v1

[^6_20]: https://arxiv.org/html/2512.12289v1

[^6_21]: https://arxiv.org/html/2201.03710v1

[^6_22]: https://arxiv.org/pdf/2606.07789.pdf

[^6_23]: https://www.pdc.kth.se/~riakymch/pubs/reprobllu.pdf

[^6_24]: https://www.emergentmind.com/topics/change-point-detection-techniques

[^6_25]: https://arxiv.org/pdf/2207.03932v2.pdf

[^6_26]: https://arxiv.org/html/2509.02844v3

[^6_27]: https://arxiv.org/pdf/2209.12398.pdf

[^6_28]: https://arxiv.org/html/2103.14224v2

[^6_29]: https://ar5iv.labs.arxiv.org/html/2309.09878

[^6_30]: https://ar5iv.labs.arxiv.org/html/2010.09398

[^6_31]: https://deepwiki.com/hildensia/bayesian_changepoint_detection

[^6_32]: https://metricgate.com/docs/bocpd-online-changepoint/

[^6_33]: https://github.com/chenhaotian/Changepoints

[^6_34]: https://github.com/epfl-lasa/changepoint-detection

[^6_35]: https://lips.cs.princeton.edu/pdfs/adams2007changepoint.pdf

[^6_36]: https://opentelemetry.io/docs/specs/otel/metrics/supplementary-guidelines/

[^6_37]: https://docs.datadoghq.com/opentelemetry/reference/otlp_metric_types.md

[^6_38]: https://docs.datadoghq.com/metrics/open_telemetry/otlp_metric_types/

[^6_39]: https://opentelemetry.io/docs/compatibility/prometheus/client-libraries/

[^6_40]: https://www.elastic.co/search-labs/blog/otel-metrics-cumulative-delta-elasticsearch

[^6_41]: https://docs.datadoghq.com/opentelemetry/guide/otlp_delta_temporality/

[^6_42]: https://signoz.io/docs/glossary/

[^6_43]: https://www.dash0.com/knowledge/opentelemetry-metrics

[^6_44]: https://www.tigerdata.com/blog/a-deep-dive-into-open-telemetry-metrics

[^6_45]: https://neubird.ai/blog/prometheus-grafana-best-practices-agentic-ai

[^6_46]: https://deepwiki.com/open-telemetry/opentelemetry-specification/10.3-metrics-data-model

[^6_47]: https://docs.rs/opentelemetry_sdk/latest/opentelemetry_sdk/metrics/enum.Temporality.html

[^6_48]: https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/metrics/v1/metrics.proto


---

# 4. Fragmentación HBM en Aceleradores (Ausencia de Pool)

Brecha (V909): El Triton Kernel optimizado de ROCm/TPU no orquesta una arena preasignada por Iteración. La gestión de Workspace en V909 sigue incurriendo indirectamente en llamadas al allocator de la GPU ante tensores intermedios grandes.
Requiere: Implementar Preasignación por Lote (Memory Arena Pattern). La evaluación exige 3 niveles (Cache Worker -> Arena por Iteración -> Pool Global) para silenciar el false sharing y latencia del kernel CUDA/ROCm.

La solución V909 debe convertir el workspace en una **jerarquía explícita de memoria**, no en una sucesión de `malloc/free` asíncronos. La arquitectura requerida es:

$$
\boxed{
\text{Cache Worker}
\rightarrow
\text{Arena por Iteración}
\rightarrow
\text{Pool Global}
}
$$

El kernel debe recibir punteros ya resueltos. No debe decidir ni provocar asignaciones durante la ruta crítica.

## Diagnóstico

`hipMallocAsync` y `cudaMallocAsync` reducen mucho el coste de asignación porque reutilizan pools y respetan el orden de streams, pero siguen siendo asignadores dinámicos. Si el patrón de tamaños cambia mucho, puede haber:

- crecimiento inesperado del pool;
- fragmentación lógica;
- sincronizaciones para satisfacer dependencias;
- presión sobre HBM;
- pérdida de localidad;
- contención entre workers;
- false sharing en metadatos o líneas de control;
- llamadas al runtime durante la iteración.

En HIP, las asignaciones stream-ordered deben usarse entre una operación de asignación y otra de liberación ordenadas por stream; acceder fuera de esa relación produce comportamiento indefinido. En CUDA, los pools pueden reutilizar memoria y desfragmentar mediante remapeo virtual, pero una configuración con `release threshold = 0` puede devolver memoria al sistema en cada sincronización.[^7_1][^7_2][^7_3]

Por eso, el pool del runtime debe ser sólo el **nivel de reserva**, no el allocator usado por cada tensor intermedio.

## Jerarquía de tres niveles

### Nivel 1: Cache Worker

Cada worker, stream o grupo de ejecución posee un cache local de bloques ya disponibles:

```text
WorkerCache[worker_id][size_class]
```

Características:

- sin mutex en la ruta normal;
- libre-list local;
- bloques alineados;
- clases de tamaño;
- acceso sólo por el worker propietario;
- devolución diferida al pool global.

El worker no debería liberar directamente al pool global en cada tensor. Debe conservar bloques reutilizables hasta superar un límite de presión.

Una estructura conceptual:

```cpp
struct Block {
    void* ptr;
    std::size_t bytes;
    std::size_t alignment;
    std::uint64_t ready_epoch;
};

struct WorkerCache {
    std::array<LockFreeStack<Block>, NUM_SIZE_CLASSES> free_lists;
    std::size_t cached_bytes = 0;
    std::size_t cache_limit = 0;
};
```

Para evitar false sharing, cada `WorkerCache` debe estar separado por una línea de cache del host:

```cpp
struct alignas(128) WorkerCache {
    ...
};
```

El tamaño debe parametrizarse según la arquitectura de CPU; `alignas(64)` puede ser insuficiente en sistemas con líneas mayores o estructuras de control adyacentes. El relleno debe impedir que contadores de workers distintos compartan la misma línea.

### Nivel 2: Arena por iteración

Al comienzo de una iteración, reservar una arena monolítica o un conjunto pequeño de segmentos:

```text
iteration_begin
    acquire arena
    bump allocations
    run all kernels
    record completion events
iteration_end
    recycle arena
```

La arena se gestiona con un bump pointer:

```cpp
struct DeviceArena {
    std::byte* base = nullptr;
    std::size_t capacity = 0;
    std::size_t offset = 0;

    void reset() noexcept {
        offset = 0;
    }

    void* allocate(std::size_t bytes, std::size_t alignment) {
        std::size_t p =
            (reinterpret_cast<std::uintptr_t>(base + offset)
             + alignment - 1) & ~(alignment - 1);

        std::size_t new_offset =
            p - reinterpret_cast<std::uintptr_t>(base) + bytes;

        if (new_offset > capacity)
            return nullptr;

        offset = new_offset;
        return reinterpret_cast<void*>(p);
    }
};
```

No se realiza `free` por tensor. Todos los temporales de la iteración se invalidan al avanzar el bump pointer. Esto elimina:

- fragmentación interna entre asignaciones intermedias;
- locks del allocator;
- metadatos por tensor;
- liberaciones fuera de orden;
- llamadas frecuentes al runtime.

El tamaño de la arena debe basarse en el pico de live ranges, no en la suma de todos los tensores. La planificación óptima requiere análisis de vida:

$$
\mathrm{arena\_bytes}
\approx
\max_t
\sum_{b\in\mathrm{live}(t)}
\mathrm{aligned\_size}(b).
$$

Los buffers cuyos intervalos de vida no se solapan pueden compartir offset. Este tipo de análisis es coherente con el planificador moderno de Triton, que reutiliza buffers cuando sus live ranges no se superponen. Triton también expone operaciones de scratch global y descriptores locales que pueden representar buffers privados y vistas de almacenamiento.[^7_4][^7_5]

### Nivel 3: Pool global

El pool global reserva grandes segmentos de HBM y los entrega a las arenas:

```text
GlobalPool
    ├── segment 0
    ├── segment 1
    ├── segment 2
    └── segment N
```

El pool no debe operar sobre cientos de miles de bloques pequeños. Debe trabajar con segmentos grandes, por ejemplo:

```text
segment size = 64 MiB, 256 MiB, 1 GiB
```

según el patrón de memoria y la capacidad de HBM.

El pool global puede estar respaldado por:

- `hipMemPool_t` en ROCm;
- `cudaMemPool_t` en CUDA;
- `hipMM::PoolMemoryResource`;
- VMM/cuMemMap cuando se requiera control fino de páginas;
- un allocator específico del backend TPU;
- una reserva preasignada en el runtime del framework.

En ROCm, `hipMemPoolCreate()` y `hipMallocFromPoolAsync()` permiten trabajar con pools explícitos, mientras que `hipMemPoolTrimTo()` y los atributos de uso permiten controlar presión y liberar exceso. `hipMM` ofrece además un `PoolMemoryResource` que reserva un pool grande y atiende desde él asignaciones posteriores.[^7_6][^7_1]

## Flujo correcto

```text
PoolGlobal:
    reserva segmentos grandes una sola vez

ArenaIteration:
    obtiene un segmento o varios del pool

CacheWorker:
    obtiene subbloques reutilizables de su cache

Kernel:
    recibe ptr + size + stride
    jamás llama allocator

Fin de iteración:
    registrar evento por stream
    arena pasa a estado RETIRED

Evento completado:
    arena vuelve a AVAILABLE
    sus bloques no se liberan individualmente
```

Estados recomendados:

```text
AVAILABLE
ACTIVE
RETIRED
REUSABLE
EVICTABLE
```

No reutilizar una arena `RETIRED` hasta que todos los streams que la utilizaron hayan completado sus eventos. Para varios streams:

$$
\mathrm{reusable}(A)
\iff
\forall s\in\mathrm{users}(A):
\operatorname{event\_complete}(e_s).
$$

## Planificación de tamaños

La arena debe evitar tamaños arbitrarios. Usar clases alineadas:

```text
4 KiB
8 KiB
16 KiB
...
2 MiB
4 MiB
8 MiB
large extents
```

Para buffers muy grandes, reservar extensiones directamente desde el pool global. Para pequeños temporales, usar la arena.

Una política práctica:

```text
small:   <= 64 KiB       bump arena
medium:  <= 16 MiB       size-class suballocation
large:   > 16 MiB        dedicated extent
huge:    > 25% HBM       admission control
```

Los límites deben medirse, no fijarse arbitrariamente. Si se redondea cada solicitud a potencia de dos, se simplifica la reutilización pero aumenta la fragmentación interna. El tamaño de clase debe optimizarse según el histograma real de solicitudes.

## Eliminación de false sharing

El false sharing relevante puede aparecer en dos niveles:

### Host

Evitar que varios workers actualicen en la misma línea:

```cpp
struct alignas(128) WorkerStats {
    std::uint64_t allocations;
    std::uint64_t cache_hits;
    std::uint64_t cache_misses;
    std::uint64_t bytes_reserved;
};
```

Separar también:

- bump pointers;
- contadores de presión;
- estados de eventos;
- flags de disponibilidad.


### GPU

El allocator no debe usar un contador global atómico por cada hilo o programa Triton. Si se necesita subasignación desde kernel:

- reservar una región por program instance;
- usar offsets estáticos;
- atomizar por bloque, no por hilo;
- separar headers de datos;
- alinear a 128 o 256 bytes según transacción;
- evitar que dos tiles escriban en la misma línea HBM;
- usar una tabla de offsets generada por host.

En la mayoría de los casos, la mejor opción es **subasignar en host y pasar los offsets al kernel**, no ejecutar un bump allocator global dentro de Triton.

## Integración con Triton

Triton debe recibir el workspace como argumento:

```python
@triton.jit
def kernel(
    x_ptr,
    y_ptr,
    workspace_ptr,
    offsets_ptr,
    n_elements,
    BLOCK: tl.constexpr,
):
    pid = tl.program_id(0)
    offset = tl.load(offsets_ptr + pid)

    scratch = workspace_ptr + offset
    ...
```

El host calcula los offsets:

```text
workspace:
    [offset_0, bytes_0, alignment_0]
    [offset_1, bytes_1, alignment_1]
    ...
```

Si todos los programas usan el mismo layout, los offsets pueden ser constantes especializados por configuración. Si dependen del `program_id`, la tabla debe residir en GPU, pero su tamaño debe ser pequeño.

Para kernels fusionados, usar live-range analysis y aliasing controlado. Los temporales no deben tener buffers distintos si sus usos no se solapan. El compilador Triton ya emplea análisis de vida para decidir reutilización de buffers locales y compartidos.[^7_7][^7_4]

No usar `ttg.global_scratch_alloc` como sustituto de la arena por iteración si el objetivo es evitar asignaciones dinámicas globales. Esa operación expresa un scratch global privado al programa, pero la política de reserva y su interacción con el runtime deben verificarse en el backend específico.[^7_5]

## Integración con ROCm

La configuración de ROCm debe tener dos capas:

### Pool global HIP

```cpp
hipMemPool_t pool;
hipDeviceGetDefaultMemPool(&pool, device);

std::uint64_t threshold = target_pool_bytes;
hipMemPoolSetAttribute(
    pool,
    hipMemPoolAttrReleaseThreshold,
    &threshold);
```

Las asignaciones ocasionales de segmentos pueden utilizar:

```cpp
hipMallocFromPoolAsync(&segment, bytes, pool, stream);
```

y los retiros:

```cpp
hipFreeAsync(segment, stream);
```

Pero esto no debe aparecer por tensor. Sólo debe ocurrir al crecer o reducir el pool de segmentos.

### Arena propia

Dentro del segmento HIP:

```cpp
arena.offset = 0;
ptr = arena.allocate(bytes, alignment);
```

La arena no realiza llamadas HIP. La sincronización se expresa con eventos:

```cpp
hipEventRecord(done_event, iteration_stream);
hipEventSynchronize(done_event);
arena.reset();
```

Para ejecución concurrente, no usar `hipEventSynchronize()` en el host por iteración si eso detiene el pipeline. En su lugar:

```text
stream A:
    work arena A
    record event A

host:
    poll/query event A

stream B:
    work arena B

cuando event A completa:
    arena A -> reusable
```

La documentación de HIP confirma que la semántica stream-ordered permite reutilización eficiente, pero exige respetar estrictamente el orden de accesos y liberación.[^7_1]

## Integración con CUDA

En CUDA, configurar un pool explícito o el pool por defecto:

```cpp
cudaMemPool_t pool;
cudaDeviceGetDefaultMemPool(&pool, device);

std::uint64_t threshold = target_pool_bytes;
cudaMemPoolSetAttribute(
    pool,
    cudaMemPoolAttrReleaseThreshold,
    &threshold);
```

El `release threshold` debe aproximarse al working set estable, no necesariamente a `UINT64_MAX`. NVIDIA documenta que un umbral alto evita devolver memoria en cada sincronización, pero un valor ilimitado puede monopolizar HBM si comparten el dispositivo varios procesos.[^7_2][^7_3][^7_8]

Para una aplicación dedicada:

```text
threshold ≈ working_set + crecimiento esperado
```

Para un entorno compartido:

```text
threshold ≈ working_set medido
trim periódico fuera de la ruta crítica
```

No depender exclusivamente de la reutilización oportunista entre streams. Crear dependencias explícitas con eventos cuando la arena se reutiliza entre streams; el runtime puede seguir dependencias de eventos y, según la configuración, reutilizar memoria entre streams.[^7_2]

## Arena doble o triple

Si la iteración $t+1$ puede comenzar mientras $t$ todavía termina, se necesita un ring de arenas:

$$
A_0\rightarrow A_1\rightarrow A_2\rightarrow A_0.
$$

El número mínimo es:

$$
N_{\mathrm{arenas}}
\geq
1+\text{máximo número de iteraciones simultáneas}.
$$

Ejemplo:

```text
arena 0: ACTIVE en stream 0
arena 1: ACTIVE en stream 1
arena 2: RETIRED esperando evento
arena 3: AVAILABLE
```

Una arena no debe reciclarse por tiempo estimado. Debe reciclarse por evento completado. Esto evita use-after-free cuando el kernel sigue leyendo un temporal.

## Predicción de capacidad

En warm-up, registrar el pico real:

```text
peak_requested_bytes
peak_live_bytes
fragmentation_bytes
arena_growth_count
pool_reserved_bytes
pool_used_bytes
```

Dimensionar:

$$
C_{\mathrm{arena}}
=
\operatorname{ceil}_{a}
\left(
P_{q}
+
M_{\mathrm{headroom}}
\right),
$$

donde:

- $P_q$ es un percentil alto del pico observado;
- $a$ es la granularidad de segmento;
- $M_{\mathrm{headroom}}$ cubre variación;
- no se usa sólo el máximo aislado si éste es un outlier.

Una política adaptativa:

```text
si overflow:
    crecer arena por factor 1.25–1.5
si tres ventanas estables:
    mantener capacidad
si presión HBM:
    devolver arenas excedentes al pool
```

El crecimiento debe ocurrir en un punto seguro, no en medio del conjunto de kernels de una iteración crítica.

## Presupuesto y admisión

Definir un presupuesto:

$$
B_{\mathrm{HBM}}
=
B_{\mathrm{persistent}}
+
B_{\mathrm{weights}}
+
B_{\mathrm{activations}}
+
B_{\mathrm{arenas}}
+
B_{\mathrm{runtime}}.
$$

El pool global no puede asumir que toda HBM está disponible. Reservar margen para:

- bibliotecas externas;
- comunicación;
- kernels concurrentes;
- páginas remapeadas;
- cachés del runtime;
- recuperación ante picos.

Si una nueva arena excede el presupuesto:

1. intentar recuperar una arena `AVAILABLE`;
2. compactar sólo metadatos, no payloads activos;
3. reducir concurrencia;
4. ejecutar en modo tiled;
5. degradar temporalmente a un algoritmo con menor workspace;
6. fallar explícitamente antes de lanzar kernels parciales.

No usar OOM tardío como mecanismo de control.

## Instrumentación de fragmentación

Medir al menos:

$$
F_{\mathrm{external}}
=
1-
\frac{\text{largest free extent}}
{\text{total free bytes}},
$$

$$
F_{\mathrm{internal}}
=
1-
\frac{\text{requested bytes}}
{\text{reserved bytes}}.
$$

Además:

```text
arena_utilization = live_bytes / arena_capacity
pool_utilization   = used_bytes / reserved_bytes
cache_hit_rate
allocation_calls_per_iteration
bytes_reclaimed
event_wait_time
kernel_stall_time
```

En HIP, el pool proporciona atributos como memoria reservada actual, memoria usada actual y máximos históricos. Exponerlos en la telemetría permite verificar que V909 realmente eliminó las llamadas al allocator, en vez de ocultarlas detrás de `hipMallocAsync`.[^7_1]

## Política de fallback

Debe existir un fallback controlado:

```text
normal:
    WorkerCache -> IterationArena -> GlobalPool

pressure:
    WorkerCache -> compact/reclaim -> GlobalPool

emergency:
    direct stream-ordered allocation

failure:
    structured OOM with required/free/reserved bytes
```

El fallback directo a HIP/CUDA no debe activarse silenciosamente. Emitir:

```json
{
  "allocator_fallback": true,
  "requested_bytes": 268435456,
  "arena_capacity": 2147483648,
  "pool_reserved": 8589934592,
  "pool_used": 8053063680,
  "reason": "arena_overflow"
}
```

Si el fallback ocurre repetidamente, es un fallo de dimensionamiento o de planificación, no una solución permanente.

## Pseudocódigo del runtime

```cpp
class IterationMemory {
public:
    void begin(std::uint64_t iteration, hipStream_t stream) {
        collect_completed_arenas();
        current_ = acquire_arena(required_capacity_);
        current_->reset();
        current_->stream = stream;
        current_->iteration = iteration;
    }

    void* alloc(std::size_t bytes, std::size_t alignment) {
        if (void* p = current_->allocate(bytes, alignment))
            return p;

        grow_or_acquire_larger_arena(bytes);
        return current_->allocate(bytes, alignment);
    }

    void end() {
        HIP_CHECK(hipEventRecord(current_->done, current_->stream));
        retire(current_);
        current_ = nullptr;
    }

private:
    std::vector<Arena> arenas_;
    Arena* current_{nullptr};
    GlobalPool pool_;
    WorkerCache* worker_cache_{nullptr};
};
```

La API del kernel debe recibir únicamente los resultados:

```cpp
Workspace ws = iteration_memory.alloc_workspace(plan);
launch_kernel(
    input,
    output,
    ws.ptr,
    ws.bytes,
    stream);
```

El `WorkspacePlan` se calcula antes:

```cpp
struct WorkspacePlan {
    std::size_t bytes;
    std::size_t alignment;
    std::span<const BufferOffset> offsets;
};
```


## Validación experimental

Comparar cuatro configuraciones:


| Configuración | Propósito |
| :-- | :-- |
| allocator por tensor | baseline V909 |
| `hipMallocAsync`/`cudaMallocAsync` por tensor | baseline stream-ordered |
| arena por iteración | medir eliminación de fragmentación |
| tres niveles completos | configuración objetivo |

Medir:

- tiempo de asignación por iteración;
- número de llamadas al runtime;
- latencia p50/p95/p99;
- HBM reservada y usada;
- fragmentación interna y externa;
- ocupación;
- throughput;
- stalls por dependencia;
- porcentaje de fallback;
- variación entre workers;
- rendimiento bajo dos streams y bajo saturación.

La hipótesis que debe verificarse es:

$$
T_{\mathrm{allocator}}^{\mathrm{arena}}
\ll
T_{\mathrm{allocator}}^{\mathrm{dynamic}},
$$

y, especialmente:

$$
\#\mathrm{runtime\ allocations\ per\ iteration}\approx 0.
$$

El objetivo no es sólo reducir el promedio. La arena debe reducir la cola de latencia; la métrica crítica será el p99 de la iteración.

## Plan de implementación

### Etapa 1

- Introducir `GlobalPool`.
- Crear segmentos grandes.
- Configurar release threshold y estadísticas.
- Eliminar asignaciones directas en kernels críticos.


### Etapa 2

- Implementar `IterationArena` bump-pointer.
- Construir plan de live ranges.
- Pasar offsets al Triton kernel.
- Añadir eventos de finalización.


### Etapa 3

- Añadir `WorkerCache` aislado por cache line.
- Implementar size classes.
- Reciclaje por ownership y eventos.
- Evitar locks en la ruta normal.


### Etapa 4

- Ring de arenas para concurrencia.
- Política de presión HBM.
- fallback explícito.
- telemetría de fragmentación.


### Etapa 5

- benchmark CUDA/ROCm;
- validación de use-after-free;
- stress con tamaños variables;
- prueba de múltiples streams;
- prueba de OOM;
- comprobación de equivalencia numérica.

La solución V909 recomendada es, por tanto:

$$
\boxed{
\text{Pool global HBM}
\rightarrow
\text{segmentos persistentes}
\rightarrow
\text{arenas bump por iteración}
\rightarrow
\text{cache privado por worker}
\rightarrow
\text{kernels sin alloc/free}
}
$$

HIP y CUDA ofrecen pools stream-ordered útiles como infraestructura de bajo nivel, pero la garantía de que no haya asignaciones indirectas durante la iteración sólo se obtiene al imponer una arena explícita y pasar sus offsets a Triton. La combinación de live-range planning, arenas persistentes, eventos de reutilización y métricas de presión HBM elimina la fragmentación operacional y silencia tanto la latencia del allocator como el false sharing de la gestión de workspace.[^7_2][^7_1]

<span style="display:none">[^7_10][^7_11][^7_12][^7_13][^7_14][^7_15][^7_16][^7_17][^7_18][^7_19][^7_20][^7_21][^7_22][^7_23][^7_24][^7_25][^7_26][^7_27][^7_28][^7_29][^7_30][^7_31][^7_32][^7_33][^7_34][^7_35][^7_36][^7_37][^7_38][^7_39][^7_40][^7_41][^7_42][^7_9]</span>

<div align="center">⁂</div>

[^7_1]: https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/memory_management/stream_ordered_allocator.html

[^7_2]: https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/

[^7_3]: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^7_4]: https://pytorch.org/blog/warp-specialization-in-triton-design-and-roadmap/

[^7_5]: https://triton-lang.org/main/dialects/TritonGPUOps.html

[^7_6]: https://github.com/ROCm/hipMM

[^7_7]: https://openai.com/index/triton/

[^7_8]: https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-2/

[^7_9]: https://rocmdocs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/device_management.html

[^7_10]: https://rocmdocs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/memory_management.html

[^7_11]: https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/memory_management/stream_ordered_memory_allocator.html

[^7_12]: https://rocm.docs.amd.com/projects/HIP/en/docs-develop/how-to/hip_runtime_api/memory_management/stream_ordered_allocator.html

[^7_13]: https://rocm.docs.amd.com/projects/HIP/en/7.13.0-preview/how-to/hip_runtime_api/memory_management/stream_ordered_allocator.html

[^7_14]: https://rocm.docs.amd.com/projects/HIP/en/docs-5.4.4/doxygen/html/group\_\_\_stream_o.html

[^7_15]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.3.2/reference/hip_runtime_api/modules/memory_management/stream_ordered_memory_allocator.html

[^7_16]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.3.3/reference/hip_runtime_api/modules/memory_management/stream_ordered_memory_allocator.html

[^7_17]: https://triton-lang.org/main/getting-started/tutorials/gluon/persistence.html

[^7_18]: https://deepwiki.com/ROCm/hip/2.2-memory-management

[^7_19]: https://github.com/csc-training/hip-programming/blob/main/docs/04-memory.md

[^7_20]: https://github.com/ROCm/hipMM/blob/branch-23.12/README.md

[^7_21]: https://deepwiki.com/ROCm/rocm-systems/2.2-hip-memory-management

[^7_22]: https://rocm.docs.amd.com/projects/hipMM/en/latest/reference/hipmm/python_api.html

[^7_23]: https://docs.nvidia.com/cuda/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_24]: https://rocm.docs.amd.com/projects/hipMM/en/docs-25.10/reference/hipmm/python_api.html

[^7_25]: https://docs.nvidia.com/cuda/archive/13.4.1/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_26]: https://docs.nvidia.com/cuda/developer-preview/13.4/cuda-runtime-api/cuda_runtime_api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_27]: https://docs.nvidia.com/cuda/archive/13.0.3/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_28]: https://docs.nvidia.com/cuda/archive/13.0.0/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_29]: https://docs.nvidia.com/cuda/archive/13.4.1/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^7_30]: https://docs.nvidia.com/cuda/archive/13.0.2/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_31]: https://docs.nvidia.com/cuda/archive/12.6.0/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^7_32]: https://arxiv.org/pdf/2608.00325.pdf

[^7_33]: https://arxiv.org/pdf/2609.36800.pdf

[^7_34]: https://www.eecs.harvard.edu/~htk/publication/2019-mapl-tillet-kung-cox.pdf

[^7_35]: https://rocm.docs.amd.com/en/docs-6.1.0/how-to/llm-fine-tuning-optimization/optimizing-triton-kernel.html

[^7_36]: https://arxiv.org/html/2605.23911v1

[^7_37]: https://exla.hexdocs.pm/

[^7_38]: https://exla.hexdocs.pm/0.12.0/EXLA.html

[^7_39]: https://gomlx.github.io/docs/backends/

[^7_40]: https://deepwiki.com/openxla/triton/9.1-memory-management

[^7_41]: https://exla.hexdocs.pm/0.10.0/EXLA.html

[^7_42]: https://deepwiki.com/pytorch/pytorch/2.5.4-code-generation:-triton-cutlass-pallas-c++


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La mejora SOTA para V909 no es sólo añadir una arena por iteración: es combinar **planificación espacio-temporal**, asignación por extensiones, memoria virtual remapeable y una política explícita de presión HBM. La jerarquía recomendada queda:

$$
\boxed{
\text{plan offline}
\rightarrow
\text{pool HBM global}
\rightarrow
\text{extensiones VMM}
\rightarrow
\text{arena por iteración}
\rightarrow
\text{cache privado de worker}
}
$$

La arena elimina la mayoría de las llamadas dinámicas, pero la VMM y la planificación de live ranges resuelven el problema residual: la fragmentación de los segmentos grandes y los cambios de patrón entre iteraciones.

## 1. Evolución de la arquitectura

### Nivel A: planificador espacio-temporal

Antes de ejecutar el Swarm, generar un `WorkspacePlan` a partir de los intervalos de vida de cada buffer:

```text
buffer_id
size
alignment
first_use
last_use
stream
dtype
reuse_class
```

Dos buffers pueden compartir región si:

$$
[\mathrm{first}_i,\mathrm{last}_i]
\cap
[\mathrm{first}_j,\mathrm{last}_j]
=
\varnothing.
$$

El problema se convierte en una asignación de intervalos. Para tamaños estáticos, un algoritmo de coloración de intervalos o un planner lineal puede producir un layout casi óptimo. Para patrones dinámicos, usar:

```text
offline plan:
    buffers previsibles

online allocator:
    requests dinámicas
```

Este modelo híbrido es el enfoque de trabajos recientes como STWeaver, que combina planificación offline con asignación online para explotar regularidad espacial y temporal. Sus resultados publicados reportan reducciones importantes de fragmentación en workloads densos y dispersos, aunque las cifras deben validarse en el hardware y patrón de CliffordNet concretos.[^8_1][^8_2]

### Nivel B: arena de extensiones

No reservar una arena monolítica gigantesca si el pico es incierto. Dividirla en extensiones:

```text
Arena
 ├── extent 0: 256 MiB
 ├── extent 1: 256 MiB
 ├── extent 2: 512 MiB
 └── extent 3: 1 GiB
```

El bump allocator mantiene offsets lógicos, mientras que el pool puede sustituir una extensión agotada sin invalidar las restantes.

Ventajas:

- crecimiento gradual;
- recuperación por extensión;
- menor desperdicio si el workload cambia;
- mejor coexistencia con otros procesos;
- posibilidad de remapear extensiones físicas.


## 2. Pool con memoria virtual

CUDA y HIP permiten separar dirección virtual de memoria física. En CUDA, `cuMemAddressReserve()` reserva un rango virtual y `cuMemMap()` asigna handles físicos a ese rango. En HIP, el flujo equivalente usa `hipMemCreate()`, `hipMemAddressReserve()`, `hipMemMap()` y `hipMemSetAccess()`.[^8_3][^8_4][^8_5][^8_6]

Esto permite que la arena vea una región virtual contigua aunque sus páginas físicas estén fragmentadas:

```text
VA contiguous:
[0 ................. 4 GiB]

physical:
[page A][page C][page F][page B]...
       mapped into contiguous VA
```


### Uso recomendado

- reservar una ventana virtual estable por `Arena`;
- asignar páginas físicas sólo cuando se necesitan;
- mapear extensiones libres dentro de la ventana;
- desmapear extensiones retiradas;
- preservar los offsets virtuales entregados a Triton.

La principal ventaja es que los kernels reciben siempre la misma geometría virtual. El pool puede reorganizar páginas físicas sin modificar los offsets lógicos.

GMLake aplica precisamente *virtual memory stitching* para unir bloques físicos no contiguos en un rango virtual continuo y reducir fragmentación en entrenamiento GPU. La idea es especialmente relevante para V909 cuando una arena lógica debe crecer, pero no existe un bloque físico contiguo suficientemente grande.[^8_7][^8_8]

### Precaución

La VMM no es gratis. Mapear, desmapear y cambiar accesos puede introducir latencia y restricciones de granularidad. La documentación CUDA exige respetar la granularidad mínima de asignación y mapeo; además, mapear no garantiza por sí mismo que el rango sea accesible hasta ejecutar la configuración de acceso correspondiente.[^8_4][^8_9]

Por ello:

```text
no remapear por tensor
no remapear por epoch
remapear por extensión
remapear fuera de la ruta crítica
```


## 3. Diseño de allocator recomendado

### Estructura lógica

```cpp
struct VirtualExtent {
    CUdeviceptr va;
    std::size_t virtual_bytes;
    std::size_t physical_bytes;
    std::size_t mapped_bytes;
    std::uint64_t generation;
    ExtentState state;
};

struct IterationArena {
    CUdeviceptr base;
    std::size_t virtual_capacity;
    std::atomic<std::size_t> offset;
    std::vector<VirtualExtent> extents;
    StreamUseSet users;
    Event completion;
};
```


### Política

```text
1. reservar VA estable al crear el pool;
2. mapear una extensión inicial;
3. asignar por bump pointer;
4. si falta espacio, mapear extensión adicional;
5. al terminar, registrar eventos;
6. reciclar cuando todos los eventos concluyan;
7. desmapear sólo bajo presión HBM.
```

El puntero que recibe Triton es virtual y estable. El allocator interno manipula extensiones, no objetos tensoriales.

## 4. Tres niveles refinados

La jerarquía solicitada puede ampliarse así:

### Cache Worker

Responsabilidad:

- reutilizar pequeños bloques;
- evitar atomics globales;
- atender solicitudes repetitivas;
- devolver excedentes por lotes.

No debe tener bloques activos de una iteración anterior sin una prueba de finalización.

### Arena por iteración

Responsabilidad:

- servir todos los temporales de una iteración;
- resolver asignaciones mediante bump pointer;
- reutilizar offsets del plan;
- operar con cero `malloc/free` por tensor.


### Pool global

Responsabilidad:

- reservar HBM;
- administrar extensiones;
- aplicar política de presión;
- integrar HIP/CUDA pool o VMM;
- recoger métricas de fragmentación.


### Director de presión

Añadir una cuarta entidad lógica, sin convertirla en una capa de asignación:

```text
PressureController
```

Monitorea:

$$
P_{\mathrm{HBM}}
=
\frac{\mathrm{reserved\_bytes}}
{\mathrm{budget\_bytes}},
$$

y decide:

```text
P < 0.70: crecer preventivamente
0.70 <= P < 0.85: mantener
0.85 <= P < 0.95: reciclar y limitar concurrencia
P >= 0.95: evict/reclaim/fallback
```

Los umbrales deben calibrarse con el runtime y con memoria reservada por bibliotecas externas.

## 5. Planificación de memoria dinámica

Para tamaños conocidos, generar un layout determinista:

```text
workspace:
    offset_A = 0
    offset_B = 64 MiB
    offset_C = 128 MiB
```

Para tamaños variables, usar clases de patrón:

```text
shape_signature =
    (batch, K, dtype, nr_streams, algorithm_mode)
```

Mantener un plan cacheado por firma:

```cpp
PlanCache[shape_signature] -> WorkspacePlan;
```

La primera ejecución de una firma realiza planificación; las siguientes usan offsets precomputados.

Esto evita recalcular y evita al allocator dinámico. Si aparece una firma nueva:

```text
compile plan
allocate/grow arena
publish immutable plan
```

No modificar un plan mientras existe una ejecución que lo usa.

## 6. Compaction sin mover punteros

La compactación clásica mueve payloads y obliga a actualizar punteros. Con VMM, es preferible:

```text
logical VA stays fixed
physical pages are remapped
```

La compactación puede actuar en extensiones que estén:

```text
AVAILABLE
RETIRED and completed
```

Nunca remapear páginas de una arena `ACTIVE`.

Una secuencia segura:

```text
1. seleccionar extensión candidata;
2. esperar eventos de todos sus usuarios;
3. reservar páginas destino;
4. copiar si el contenido debe preservarse;
5. actualizar mappings;
6. verificar accesibilidad;
7. devolver páginas físicas antiguas;
8. incrementar generation;
```

Si no se necesita preservar contenido porque la extensión pertenece al scratch de una iteración ya finalizada, basta desmapear y devolver las páginas.

## 7. Integración con Triton

El kernel no debe conocer el allocator. Debe recibir:

```python
workspace_base
workspace_offsets
workspace_sizes
workspace_generation
```

Ejemplo conceptual:

```python
@triton.jit
def clifford_kernel(
    x_ptr,
    y_ptr,
    workspace_base,
    offsets_ptr,
    sizes_ptr,
    n,
    BLOCK: tl.constexpr,
):
    pid = tl.program_id(0)

    off = tl.load(offsets_ptr + pid)
    size = tl.load(sizes_ptr + pid)

    scratch = workspace_base + off
    # uso acotado a size
```

La generación puede usarse para detectar errores del host:

```text
kernel plan generation != arena generation
    -> abortar lanzamiento
```

En producción, la comprobación puede ser host-side para no añadir ramas al kernel.

Triton dispone de operaciones relacionadas con scratch global privado por programa, pero eso no debe confundirse con la arena de iteración gestionada por el host. El scratch local de Triton resuelve necesidades del programa; la arena V909 resuelve ownership, reutilización y presión HBM de toda la iteración.[^8_10]

## 8. Manejo de varias streams

Una arena debe registrar todas las streams que la utilizan:

```cpp
struct StreamUse {
    hipStream_t stream;
    hipEvent_t completion;
};
```

Una arena sólo vuelve a `AVAILABLE` cuando:

$$
\forall e_i,\quad \mathrm{query}(e_i)=\mathrm{complete}.
$$

No basta con esperar la stream principal si los kernels auxiliares corren en streams secundarios.

Para pipeline doble:

```text
arena A -> stream 0
arena B -> stream 1
arena C -> communication stream
```

Para pipeline triple, el número de arenas debe cubrir el máximo de trabajos simultáneos más una reserva. Si no se cubre, el runtime puede bloquearse esperando una arena libre, lo que aparecerá como una caída de throughput aunque no haya OOM.

## 9. Política de caché y liberación

El cache Worker debe tener dos límites:

$$
B_{\mathrm{worker}}\leq B_{\max},
$$

$$
B_{\mathrm{global}}\leq B_{\mathrm{budget}}.
$$

Si un worker supera su límite:

```text
1. conservar bloques calientes;
2. devolver bloques fríos al pool global;
3. fusionar extensiones completas;
4. desmapear bajo presión.
```

La política LRU simple puede ser suficiente, pero una política por distancia de reutilización es mejor:

```text
hot:
    reuse predicted within next iterations

warm:
    reuse likely within window

cold:
    return to global pool
```

La predicción puede obtenerse del historial de `shape_signature` y del intervalo entre reutilizaciones.

## 10. Integración con pools nativos

Los pools CUDA/HIP siguen siendo útiles como backend.

### CUDA

Usar `cudaMemPool_t` para las reservas de extensiones y configurar:

- `cudaMemPoolAttrReleaseThreshold`;
- acceso entre dispositivos;
- granularidad;
- estadísticas de memoria;
- callbacks de presión si la infraestructura lo permite.

La asignación asíncrona garantiza ordenamiento por stream, pero todos los accesos deben situarse entre la operación de asignación y la operación de liberación correspondientes.[^8_11][^8_12]

### ROCm

Usar `hipMemPool_t` o `hipMM::PoolMemoryResource` como backend del `GlobalPool`. El pool debe reservar segmentos grandes y mantenerlos mientras el working set sea estable. `hipMM` está diseñado precisamente para reservas anticipadas y subasignación posterior desde un pool.[^8_13][^8_14]

### Abstracción común

```cpp
class DeviceMemoryBackend {
public:
    virtual Extent allocate_extent(std::size_t bytes) = 0;
    virtual void release_extent(Extent&) = 0;
    virtual void map(Extent&, VirtualAddress) = 0;
    virtual void unmap(Extent&) = 0;
    virtual MemoryStats stats() const = 0;
};
```

Implementaciones:

```text
CudaPoolBackend
HipPoolBackend
CudaVmmBackend
HipVmmBackend
TestHostBackend
```

La arena no debe depender directamente de `cudaMallocAsync` o `hipMallocAsync`; debe depender de esta abstracción.

## 11. Qué técnicas SOTA conviene adoptar

| Técnica | Beneficio | Adecuación |
| :-- | :-- | :-- |
| Arena bump por iteración | Cero free por tensor | Obligatoria |
| Pool global | Reutilización HBM | Obligatoria |
| Live-range planning | Menor capacidad necesaria | Muy alta |
| Extensiones | Crecimiento controlado | Muy alta |
| VMM stitching | Defragmentación física | Alta en workloads variables |
| Buddy allocator | Tamaños dinámicos | Media, como fallback |
| Superpages | Menor presión TLB | Alta si los buffers son grandes |
| Paged allocation | Menor fragmentación | Alta para patrones muy dinámicos |
| STWeaver-like planning | Uso de regularidad histórica | Alta si las firmas se repiten |
| GMLake-like remapping | Compactación sin cambiar VA | Alta en CUDA/HIP con VMM |
| Allocator dentro del kernel | Subasignación device-side | Baja para V909 |

La investigación reciente apunta a dos direcciones complementarias: planificación espacio-temporal para reducir fragmentación antes de ejecutar y VMM para recomponer memoria física fragmentada detrás de direcciones virtuales estables.[^8_1][^8_7]

## 12. Métricas científicas

No medir sólo “memoria usada”. Registrar por iteración:

```text
requested_bytes
live_bytes_peak
arena_reserved_bytes
pool_reserved_bytes
physical_mapped_bytes
virtual_reserved_bytes
internal_fragmentation
external_fragmentation
allocator_calls
vmm_map_calls
vmm_unmap_calls
event_wait_ns
arena_reuse_latency_ns
kernel_duration_ns
fallback_count
```

Indicadores:

$$
U_{\mathrm{arena}}
=
\frac{\mathrm{peak\ live\ bytes}}
{\mathrm{arena\ reserved\ bytes}},
$$

$$
F_{\mathrm{internal}}
=
1-
\frac{\mathrm{requested\ bytes}}
{\mathrm{reserved\ bytes}},
$$

$$
F_{\mathrm{external}}
=
1-
\frac{\mathrm{largest\ usable\ extent}}
{\mathrm{total\ free\ bytes}}.
$$

También medir:

- p50, p95 y p99 de latencia;
- throughput;
- ocupación;
- ancho de banda HBM;
- número de stalls;
- variación entre ejecuciones;
- memoria desperdiciada por granularidad de páginas.

Para VMM, separar:

```text
virtual fragmentation
physical fragmentation
mapping overhead
```

Un rango virtual contiguo no significa que la memoria física esté libre de fragmentación; sólo cambia dónde se manifiesta el problema.

## 13. Plan de pruebas

### Prueba de patrón estable

Esperar:

```text
una reserva inicial
cero crecimiento posterior
cero allocator calls por iteración
```


### Prueba de burst

Alternar:

```text
small -> huge -> small -> huge
```

Verificar que el pool no conserve indefinidamente la capacidad máxima si el presupuesto exige liberación.

### Prueba de adversario

Generar tamaños que dejen huecos:

```text
A, B, C, free(B), D, free(A), E...
```

Comparar buddy, arena por extensión y VMM stitching.

### Prueba de concurrencia

Ejecutar varias streams y workers, verificando:

- ausencia de use-after-free;
- ausencia de doble reciclaje;
- ausencia de deadlocks;
- ausencia de false sharing observable;
- equivalencia de resultados.


### Prueba de presión HBM

Reducir artificialmente el presupuesto y verificar que el sistema:

1. recicle arenas completas;
2. reduzca concurrencia;
3. active fallback;
4. produzca un error estructurado, no un crash tardío.

## Recomendación de implementación

Para V909, la configuración óptima es:

```text
1. planificador de live ranges por shape signature;
2. arena bump por iteración;
3. ring de 2–4 arenas por pipeline;
4. cache privado por worker con alineación de cache line;
5. pool global de extensiones de 256 MiB–1 GiB;
6. VMM para reservar VA estable y remapear extensiones;
7. CUDA/HIP pool como backend de páginas/extensiones;
8. offsets precomputados entregados a Triton;
9. eventos por stream para reciclaje;
10. pressure controller con métricas p99 y HBM.
```

La decisión clave es no intentar que un solo allocator resuelva todos los casos. La arena maneja el camino caliente; el pool gestiona capacidad; VMM resuelve fragmentación física; el planner reduce el working set; y el fallback absorbe patrones impredecibles.

En términos de complejidad operacional:

$$
\text{ruta caliente}
=
O(1)
$$

por subasignación de arena, mientras que las operaciones costosas:

$$
\text{map/unmap},\ \text{crecimiento},\ \text{trim}
$$

se desplazan fuera de la iteración crítica y se realizan por extensiones completas. Esto satisface la exigencia V909 de eliminar llamadas indirectas al allocator de GPU durante el procesamiento normal y, al mismo tiempo, proporciona una ruta SOTA para combatir fragmentación HBM cuando el patrón de trabajo deja de ser estático.

<span style="display:none">[^8_15][^8_16][^8_17][^8_18][^8_19][^8_20][^8_21][^8_22][^8_23][^8_24][^8_25][^8_26][^8_27][^8_28][^8_29][^8_30][^8_31][^8_32][^8_33][^8_34][^8_35][^8_36][^8_37][^8_38][^8_39][^8_40][^8_41][^8_42][^8_43][^8_44][^8_45][^8_46][^8_47][^8_48][^8_49]</span>

<div align="center">⁂</div>

[^8_1]: https://arxiv.org/html/2507.16274v1

[^8_2]: https://www.scholarfeed.org/author/A5049910854/shengen-yan

[^8_3]: https://developer.nvidia.com/blog/introducing-low-level-gpu-virtual-memory-management/

[^8_4]: https://docs.nvidia.com/cuda/cuda-driver-api/cuda_driver_api/group\_\_CUDA\_\_VA.html

[^8_5]: https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_6]: https://rocm-handbook.amd.com/\_/downloads/amd-rocm-programming-guide/en/docs-7.2.2/pdf/

[^8_7]: https://dl.acm.org/doi/pdf/10.1145/3652024.3665508

[^8_8]: https://arxiv.org/pdf/2401.08156.pdf

[^8_9]: https://docs.nvidia.com/cuda/archive/12.3.0/cuda-driver-api/group\_\_CUDA\_\_VA.html

[^8_10]: https://triton-lang.org/main/dialects/TritonGPUOps.html

[^8_11]: https://docs.nvidia.com/cuda/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^8_12]: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^8_13]: https://github.com/ROCm/hipMM

[^8_14]: https://github.com/ROCm/hipMM/blob/branch-23.12/README.md

[^8_15]: https://www.usenix.org/system/files/osdi26-zhang-yangyu.pdf

[^8_16]: https://research.nvidia.com/sites/default/files/pubs/2019-02_Throughput-oriented-GPU-memory/paper.pdf

[^8_17]: https://llvm.org/devmtg/2025-03/slides/polyhedral_gpu_rescheduling.pdf

[^8_18]: https://hazyresearch.stanford.edu/blog/2025-09-22-pgl

[^8_19]: https://arxiv.org/html/2504.07004v1

[^8_20]: https://arxiv.org/html/2408.11556v2

[^8_21]: https://docs.nvidia.com/deeplearning/tensorrt/latest/architecture/how-trt-works.html

[^8_22]: https://arxiv.org/html/2609.24270v1

[^8_23]: https://arxiv.org/html/2609.13592v1

[^8_24]: https://arxiv.org/html/2605.04450v1

[^8_25]: http://reports-archive.adm.cs.cmu.edu/anon/2025/CMU-CS-25-130.pdf

[^8_26]: https://ar5iv.labs.arxiv.org/html/2405.04437

[^8_27]: https://www.emergentmind.com/topics/gpu-allocator

[^8_28]: https://www.openproceedings.org/2025/conf/edbt/paper-82.pdf

[^8_29]: https://ui.adsabs.harvard.edu/abs/2024arXiv240108156G/abstract

[^8_30]: https://www.arxiv.org/list/cs/2024-01?skip=3200\&show=50

[^8_31]: https://arxiv.org/list/cs/2024-01?skip=3200\&show=250

[^8_32]: https://arxiv.org/pdf/2609.25451.pdf

[^8_33]: https://arxiv.org/pdf/2405.04437v3.pdf

[^8_34]: https://ai.updf.cn/en/paper-detail/reducing-gpu-memory-fragmentation-via-spatio-temporal-planning-for-efficient-huang-hu-c0958f6ceca66b7b21439456dd984d9839db1465

[^8_35]: https://www.papercache.org/deepnotes-temp/papers/mlsys/gpu/2024-01-GMLake-Efficient-and-Transparent-GPU-Memory-Defragmentation-for-Large-scale-DNN-Training-with-Virtual-Memory-Stitching

[^8_36]: https://github.com/antgroup/glake

[^8_37]: https://orcid.org/0000-0002-5660-5493

[^8_38]: https://chatpaper.com/chatpaper/paper/169157

[^8_39]: https://developer.nvidia.com/zh-cn/blog/cuda-virtual-address-management-cn/

[^8_40]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.4.1/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_41]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.1.2/how-to/virtual_memory.html

[^8_42]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.2.1/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_43]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.3.2/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_44]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.2.2/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_45]: https://rocm.docs.amd.com/projects/HIP/en/docs-6.2.4/how-to/hip_runtime_api/memory_management/virtual_memory.html

[^8_46]: https://rocm.docs.amd.com/projects/HIP/en/docs-7.1.1/reference/hip_runtime_api/modules/memory_management/virtual_memory_reference.html

[^8_47]: https://docs.nvidia.com/cuda/archive/10.2/cuda-driver-api/group\_\_CUDA\_\_VA.html

[^8_48]: https://deepwiki.com/NVIDIA/cuda-samples/5.4-memory-mapping-and-virtual-memory-management

[^8_49]: https://openai.com/index/triton/


---

# ¡es cierto que se requiere autorización para abandonar el paradigma matricial denso solve_linear_system_2k y la librería ctypes, abordando la refactorización a un solver FGMRES / Woodbury-Explícito mediante pybind11.?

Sí, pero conviene precisar el alcance: **no suele requerirse una “autorización” matemática externa para cambiar el algoritmo**, pero sí una autorización formal de ingeniería, arquitectura o control de cambios si `solve_linear_system_2k` y `ctypes` forman parte de una interfaz aprobada, un contrato ABI, un componente regulado o una rama protegida del proyecto.

La migración propuesta es suficientemente profunda como para requerir revisión y aprobación técnica antes de fusionarse:

$$
\texttt{solve\_linear\_system\_2k}
\longrightarrow
\text{operador matrix-free}
+
\text{FGMRES}
+
\text{Woodbury explícito}
$$

y:

$$
\texttt{ctypes}
\longrightarrow
\text{extensión C++}
+
\text{pybind11}
+
\text{RAII}
+
\text{Buffer Protocol}.
$$

## Qué cambia realmente

### Solver

El solver actual materializa una estructura densa $2K\times 2K$ y aplica eliminación de Gauss. La alternativa no forma la matriz aumentada; expone solamente acciones:

$$
v\mapsto Av,
\qquad
v\mapsto Uv,
\qquad
v\mapsto V^Tv.
$$

FGMRES es apropiado cuando el precondicionador cambia entre iteraciones; ésa es precisamente su diferencia principal respecto de GMRES estándar. Los métodos Krylov matrix-free requieren únicamente productos operador-vector, sin construir ni factorizar la matriz completa.[^9_1][^9_2][^9_3]

Para una corrección de bajo rango:

$$
M=A+UV^T,
$$

Woodbury se usa como:

$$
M^{-1}b
=
A^{-1}b
-
A^{-1}U
\left(I+V^TA^{-1}U\right)^{-1}
V^TA^{-1}b.
$$

La implementación correcta no calcula $A^{-1}$. Define operadores de aplicación:

```text
solve_base(rhs)       ≈ A⁻¹ rhs
apply_low_rank(x)     = U(Vᵀx)
solve_reduced(rhs)    = solve(I + Vᵀ solve_base(U), rhs)
```

El único sistema reducido que puede factorizarse explícitamente tiene dimensión $r$, el rango de la actualización, no $2K$ ni el tamaño global del problema.

### Binding nativo

`ctypes` permite llamar funciones compatibles con C, pero deja al programador la declaración manual de tipos, ownership y vida útil. La documentación de Python advierte que un uso incorrecto puede corromper memoria y objetos.[^9_4][^9_5]

pybind11 permite expresar:

- clases C++;
- constructores y destructores;
- excepciones;
- smart pointers;
- Buffer Protocol;
- liberación controlada del GIL;
- conversiones de tipos.

Pero pybind11 no elimina automáticamente los errores de ownership. Una política de retorno incorrecta puede producir doble liberación o referencias a objetos destruidos. Por ello, el cambio debe incluir un contrato explícito de propiedad.[^9_6]

## Cuándo sí hace falta autorización

La autorización formal es recomendable u obligatoria si se cumple cualquiera de estas condiciones:

- cambia la firma pública usada por otros módulos;
- cambia el ABI o el formato binario;
- se sustituye una dependencia permitida por otra;
- se altera la reproducibilidad numérica;
- se cambia el backend CUDA/ROCm o el modelo de memoria;
- se modifican requisitos de Python soportados;
- se eliminan pruebas de compatibilidad existentes;
- el solver participa en resultados científicos certificados;
- el mapping nativo maneja memoria compartida o recursos del sistema;
- el proyecto usa control de cambios, revisión de seguridad o validación regulatoria.

La autorización no debería ser una aprobación genérica del tipo “migrar a pybind11”. Debe aprobarse una propuesta técnica concreta con:

```text
alcance
interfaces afectadas
riesgos
plan de migración
criterios de equivalencia
benchmarks
rollback
compatibilidad
```


## Qué debe aprobarse

### 1. Contrato matemático

Definir:

$$
\mathcal{L}(x)=b
$$

como operador público y especificar:

- tolerancia relativa y absoluta;
- máximo de iteraciones;
- criterio de convergencia;
- política de restart;
- comportamiento ante estancamiento;
- precondicionador;
- precisión interna;
- tratamiento de singularidad del sistema reducido.

El nuevo solver no debe aceptarse sólo porque devuelve un vector. Debe demostrar:

$$
\frac{\|b-\mathcal{L}(x)\|}
{\|b\|}
\leq \tau.
$$

También debe compararse contra el solver denso en tamaños pequeños, donde ambos puedan ejecutarse con precisión suficiente.

### 2. Contrato de ownership

Definir por escrito:

```text
C++ posee el recurso nativo mediante RAII.
Python posee el wrapper.
memoryview/NumPy mantiene vivo al exportador.
No se expone HANDLE liberable desde Python.
No se permite cerrar mientras existan vistas activas.
```

El Buffer Protocol de CPython está diseñado para que una vista mantenga la referencia al objeto exportador durante su uso. pybind11 requiere marcar la clase con `py::buffer_protocol()` cuando se implementa esa interfaz.[^9_7][^9_8]

### 3. Compatibilidad de API

Una migración segura puede mantener una fachada temporal:

```python
def solve_linear_system_2k(...):
    return _native_solver.solve_matrix_free(...)
```

Así, los consumidores Python no cambian inmediatamente. La fachada debe emitir una advertencia de deprecación y registrar qué rutas aún dependen del solver anterior.

La compatibilidad debe probar:

- shapes;
- dtype;
- contigüidad;
- strides;
- excepciones;
- códigos de error;
- propiedad de buffers;
- comportamiento al destruir objetos;
- soporte Windows/Linux;
- CPU/GPU.


## Estrategia de migración aprobable

### Fase 0: autorización y especificación

Crear un RFC interno con:

```text
V909-FGMRES-WOODBURY
V909-PYBIND11-RAII
```

Incluir una tabla:


| Área | Actual | Objetivo | Riesgo |
| :-- | :-- | :-- | :-- |
| Álgebra | Gauss sobre $2K\times2K$ | FGMRES matrix-free | Convergencia |
| Corrección | matriz densa | Woodbury reducido | Condicionamiento |
| Python | ctypes | pybind11 | ABI y ownership |
| Memoria | punteros/manual | RAII + buffer | Vistas colgantes |
| Validación | equivalencia puntual | residual + benchmarks | Cambios numéricos |

### Fase 1: dual-run

Ejecutar ambos solvers sobre los mismos inputs:

```text
x_dense = solve_linear_system_2k(...)
x_krylov = solve_fgmres_woodbury(...)
```

Comparar:

$$
\frac{\|x_{\mathrm{dense}}-x_{\mathrm{krylov}}\|}
{\max(1,\|x_{\mathrm{dense}}\|)}
$$

y, sobre todo, el residual de cada solución.

No exigir igualdad bit a bit: un solver iterativo y uno denso pueden producir soluciones distintas pero igualmente válidas. La condición primaria es la corrección del residual y la estabilidad ante perturbaciones.

### Fase 2: binding paralelo

Mantener dos módulos:

```text
legacy_ctypes
native_pybind11
```

Usar una bandera:

```python
backend="legacy"
backend="native"
```

La selección debe poder hacerse por proceso, no sólo globalmente, para facilitar canary testing.

### Fase 3: activación gradual

Orden recomendado:

```text
tests pequeños
benchmarks internos
datasets de validación
canary GPU
producción parcial
producción completa
```

Mantener telemetría de:

```text
solver_backend
iterations
restarts
residual
small_system_condition
fallback_dense
binding_backend
buffer_export_count
```


### Fase 4: deprecación

Sólo retirar `solve_linear_system_2k` y `ctypes` cuando:

- todas las rutas usen el binding nativo;
- el solver nuevo cumpla los criterios de convergencia;
- no existan fallos de ownership;
- los benchmarks cumplan el presupuesto;
- exista rollback probado;
- se haya congelado el nuevo contrato.


## Riesgos que requieren revisión

### Convergencia de FGMRES

FGMRES puede consumir más memoria que GMRES porque debe conservar los vectores precondicionados $z_j$, y su convergencia depende mucho del precondicionador. La literatura señala que permite variar el precondicionador en cada paso, pero no garantiza automáticamente menor número de iteraciones.[^9_9][^9_10]

Aprobar el cambio sólo con:

- límite de memoria para la base de Krylov;
- restart configurable;
- criterio de estancamiento;
- fallback controlado;
- medición p95/p99 de iteraciones.


### Condicionamiento de Woodbury

El núcleo:

$$
S=I+V^TA^{-1}U
$$

puede estar mal condicionado aunque $A$ sea resoluble. Debe registrarse:

$$
\kappa(S)
$$

o un proxy obtenido de la factorización. Si el núcleo es inestable:

```text
reortogonalizar U/V
usar QR o SVD reducida
aumentar precisión
reducir rango efectivo
fallback a solver denso pequeño
```

El fallback denso puede ser aceptable para el **núcleo reducido**. Lo que se debe abandonar es la matriz aumentada grande, no toda factorización pequeña.

### Ownership del binding

El riesgo principal no es que pybind11 sea inseguro, sino usar una política equivocada. `reference`, `take_ownership`, `move` y `copy` tienen semánticas distintas; la documentación advierte que devolver una referencia a un objeto que C++ destruye mientras Python aún lo utiliza produce comportamiento indefinido.[^9_6]

La revisión debe comprobar cada retorno:

```text
valor:
    return por valor o move

objeto compartido:
    shared_ptr/smart_holder

vista:
    owner explícito + Buffer Protocol

memoria externa:
    capsule o propietario RAII
```


## Respuesta concreta

Sí: **para un proyecto serio, la sustitución debe tratarse como un cambio autorizado y revisado**, aunque no exista una autorización legal externa. La autorización debe cubrir simultáneamente:

1. abandonar la matriz densa $2K\times2K$;
2. introducir FGMRES y Woodbury operatorial;
3. cambiar el contrato numérico de solución;
4. sustituir `ctypes` por pybind11;
5. imponer ownership RAII;
6. exponer buffers sin copia de manera segura;
7. definir compatibilidad, rollback y criterios de aceptación.

No es necesario pedir permiso para experimentar en una rama aislada. Sí es necesario aprobar formalmente la integración cuando el cambio vaya a modificar la ruta oficial del solver o la interfaz Python.

La recomendación es **no realizar el cambio como un commit monolítico**. Aprobar y fusionar en dos líneas coordinadas:

```text
A. solver:
   matrix-free operator
   Woodbury explícito
   FGMRES
   dual-run y validación

B. binding:
   C++ RAII
   pybind11
   Buffer Protocol
   ownership tests
   compatibilidad Python
```

Después, unir ambas ramas mediante una fachada estable. Así se puede distinguir un fallo algebraico de un fallo FFI y mantener un rollback limpio durante la transición.

<span style="display:none">[^9_11][^9_12][^9_13][^9_14][^9_15][^9_16][^9_17][^9_18][^9_19][^9_20][^9_21][^9_22][^9_23][^9_24][^9_25][^9_26][^9_27][^9_28][^9_29][^9_30][^9_31]</span>

<div align="center">⁂</div>

[^9_1]: https://proceedings.iclr.cc/paper_files/paper/2025/file/3bb7e33e4da1fd19ebc6f0899e45a9dc-Paper-Conference.pdf

[^9_2]: https://arxiv.org/html/1303.5692v1

[^9_3]: https://github.com/JuliaSmoothOptimizers/Krylov.jl/blob/main/docs/src/matrix_free.md

[^9_4]: https://docs.python.org/3/library/ctypes.html

[^9_5]: https://docs.python.org/3.15/library/ctypes.html

[^9_6]: https://pybind11.readthedocs.io/en/latest/advanced/functions.html

[^9_7]: https://docs.python.org/3/c-api/buffer.html

[^9_8]: https://pybind11.readthedocs.io/en/stable/upgrade.html

[^9_9]: https://journals.ametsoc.org/view/journals/mwre/131/10/1520-0493_2003_131_2464_spfnam_2.0.co_2.xml

[^9_10]: https://arxiv.org/html/1511.07226v2

[^9_11]: https://pybind11.readthedocs.io/en/stable/limitations.html

[^9_12]: https://pybind11.readthedocs.io/en/latest/changelog.html

[^9_13]: https://algomaster.io/learn/python/ctypes

[^9_14]: https://shan-weiqiang.github.io/2026/06/21/python-c-extension-pybind11.html

[^9_15]: https://deepwiki.com/pybind/pybind11/2.3-function-binding

[^9_16]: https://gitlab.oca.eu/DISC/gh/pybind11/-/blob/smart_holder/README_smart_holder.rst

[^9_17]: https://wiki.python.org/python/ctypes.html

[^9_18]: https://www.mindat.org/reference.php?id=9226416

[^9_19]: https://arxiv.org/pdf/2604.27971v1.pdf

[^9_20]: https://www.cerfacs.fr/algor/reports/2006/TR_PA_06_09.pdf

[^9_21]: http://www.wias-berlin.de/preprint/2408/wias_preprints_2408.pdf

[^9_22]: http://stanford.edu/class/msande318/refs/DQGMRES.pdf

[^9_23]: https://www.nii.ac.jp/TechReports/public_html/12-001E.pdf

[^9_24]: https://diamhomes.ewi.tudelft.nl/~kvuik/papers/Vui95.pdf

[^9_25]: https://ar5iv.labs.arxiv.org/html/2110.04017

[^9_26]: https://jso.dev/Krylov.jl/previews/PR609/factorization-free/

[^9_27]: https://homepage.tudelft.nl/d2b4e/papers/Vui95.pdf

[^9_28]: https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html

[^9_29]: https://pybind11.readthedocs.io/en/stable/advanced/misc.html

[^9_30]: https://pybind11.readthedocs.io/\_/downloads/en/stable/pdf/

[^9_31]: https://pybind11.readthedocs.io/\_/downloads/en/latest/pdf/


---

# Produndiza el tema buscando mejoras y soluciones cientificas SOTA

La solución SOTA no es únicamente “cambiar Gauss por FGMRES y `ctypes` por pybind11”. La opción más sólida es una **migración verificable en dos planos**:

$$
\boxed{
\text{solver matrix-free}
+
\text{Woodbury reducido}
+
\text{FGMRES/FGMRES-DR}
+
\text{precisión mixta controlada}
}
$$

y:

$$
\boxed{
\text{C++ RAII}
+
\text{pybind11 o nanobind}
+
\text{Buffer Protocol/DLPack}
+
\text{ownership verificable}
}
$$

La innovación importante es mantener la ruta caliente sin estructuras densas, pero añadir recuperación ante mala convergencia, deflación espectral, auditoría numérica y una interfaz Python que no exponga punteros desprotegidos.

## 1. Solver: de Woodbury básico a precondicionador adaptativo

Para un operador:

$$
\mathcal{L}=A+UV^T,
$$

la implementación matrix-free debe exponer:

```text
apply_A(x)
apply_U(x)
apply_Vt(x)
solve_base(rhs)
```

La aplicación de Woodbury es:

$$
\mathcal{L}^{-1}b
=
A^{-1}b-
A^{-1}U
\left(I+V^TA^{-1}U\right)^{-1}
V^TA^{-1}b.
$$

Nunca se forma $\mathcal{L}$, $A^{-1}$ ni $[A\mid B]$. Se precomputan solamente:

$$
Z=A^{-1}U,
\qquad
S=I+V^TZ.
$$

Luego:

```text
z0     = solve_base(b)
rhsred = Vᵀ z0
corr   = solve_small(S, rhsred)
x      = z0 - Z corr
```

El coste del núcleo reducido es $r\times r$, donde $r$ es el rango efectivo de la actualización. Si $r$ crece demasiado, Woodbury deja de ser atractivo y debe aplicarse compresión.

## 2. Compresión adaptativa del rango

No debe asumirse que todas las columnas de $U$ y $V$ aportan información independiente. Usar una compresión QR o SVD truncada:

$$
U\approx Q_U R_U,
\qquad
V\approx Q_V R_V.
$$

Alternativas:

- QR con pivotado;
- SVD truncada;
- randomized range finder;
- randomized SVD;
- Nyström si la actualización es aproximadamente simétrica.

El rango $r$ debe elegirse por energía espectral:

$$
\frac{\sum_{i=1}^{r}\sigma_i^2}
{\sum_i\sigma_i^2}
\geq 1-\varepsilon_{\mathrm{rank}}.
$$

Para no formar matrices densas grandes, construir la base aleatoria únicamente mediante productos operador-vector. Los métodos Krylov y randomized range finding son especialmente adecuados cuando sólo está disponible la acción $v\mapsto Av$; resultados recientes enfatizan precisamente esa ventaja de los métodos Krylov en el acceso matrix-free.[^10_1]

La política debería ser:

```text
r pequeño:
    Woodbury directo

r variable:
    FGMRES con precondicionador flexible

r grande o núcleo mal condicionado:
    compresión adaptativa + fallback iterativo
```


## 3. FGMRES-DR y deflación

FGMRES resuelve el problema de precondicionadores variables, pero puede estancarse si existen modos espectrales lentos. La mejora SOTA es incorporar deflación o *recycling*:

$$
\text{FGMRES-DR}(m,k).
$$

Se conservan $k$ vectores asociados a los modos difíciles y se reutilizan después de cada restart. Esto reduce el coste de resolver secuencias de sistemas relacionados, como los que aparecen al actualizar el punto Stiefel o el estado del Swarm.

La variante FGMRES-DR es especialmente relevante si:

- cambia $U,V$ entre iteraciones;
- la base $A$ se modifica lentamente;
- el sistema se resuelve repetidamente;
- existe un subespacio casi nulo;
- la actualización de Woodbury cambia el espectro.

La literatura sobre GMRES distingue claramente entre flexibilidad, deflación y reinicio; FGMRES permite variar el precondicionador, mientras que GMRES-DR conserva información espectral para reducir el estancamiento.[^10_2][^10_3]

Estado recomendado:

```cpp
struct KrylovRecycleSpace {
    Matrix U_recycle;
    Matrix AU_recycle;
    std::size_t rank;
    std::uint64_t operator_generation;
};
```

Invalidar o actualizar el espacio reciclado cuando:

$$
\frac{\|U_{\mathrm{new}}-U_{\mathrm{old}}\|}
{\|U_{\mathrm{old}}\|}
>\tau_{\mathrm{recycle}}.
$$

## 4. Precisión mixta con refinamiento externo

La GPU puede ejecutar:

- productos operador-vector en FP32;
- precondicionador Woodbury en FP32 o FP16;
- núcleo reducido en FP32/FP64;
- ortogonalización en FP64 o precisión acumulada;
- residual final en FP64.

El esquema es:

$$
r_k=b-\mathcal{L}x_k
$$

calculado en alta precisión, mientras el paso interno usa menor precisión. Después:

$$
x_{k+1}=x_k+\Delta x_k.
$$

La investigación reciente sobre GMRES aumentado de precisión mixta muestra que se pueden reducir costes usando baja precisión en operaciones internas, siempre que la actualización y el residual externo se mantengan en alta precisión; además, variantes flexibles permiten precondicionadores aplicados en FP16 o FP32 sin perder necesariamente la convergencia de alta precisión.[^10_4][^10_5]

Configuración recomendada:


| Operación | Precisión |
| :-- | :-- |
| `apply_A` GPU | FP32 |
| `apply_U`, `apply_Vt` | FP32/TF32 |
| núcleo reducido $S$ | FP64 si $r$ es pequeño |
| Arnoldi/MGS | FP64 o acumulación compensada |
| residual true | FP64 |
| actualización $x$ | FP64 |
| almacenamiento de bases | FP32 con reortogonalización |

No usar FP16 indiscriminadamente. Si el núcleo reducido está mal condicionado, usar FP64 o factorización escalada.

## 5. Criterio de convergencia robusto

No aceptar solamente el residual predecido por el proceso de Arnoldi. Recalcular periódicamente el residual verdadero:

$$
r_{\mathrm{true}}=b-\mathcal{L}(x).
$$

Usar criterio combinado:

$$
\frac{\|r_{\mathrm{true}}\|}
{\|b\|+\|\mathcal{L}\|\|x\|}
\leq \tau_{\mathrm{backward}}
$$

y:

$$
\frac{\|r_k-r_{k-1}\|}
{\max(1,\|r_{k-1}\|)}
\leq \tau_{\mathrm{stagnation}}
$$

durante $q$ iteraciones.

Estados de salida:

```text
CONVERGED
MAX_ITERATIONS
STAGNATED
REDUCED_SYSTEM_ILL_CONDITIONED
BREAKDOWN
OUT_OF_MEMORY
NUMERICAL_NAN_INF
```

Esto es preferible a devolver sólo un booleano.

## 6. Fallback científico

El abandono del solver denso no debe significar eliminar todos los fallbacks. Se debe mantener una ruta de emergencia acotada:

```text
FGMRES + Woodbury
    ↓ si falla por estancamiento
FGMRES-DR / compresión de rango
    ↓ si el núcleo reducido es pequeño
LU/QR sólo sobre S
    ↓ si persiste el fallo
solver denso legacy en modo diagnóstico
```

El solver legacy no debe ser la ruta normal ni usarse sobre $2K\times2K$ en tamaños grandes. Puede conservarse temporalmente para:

- validación;
- tamaños pequeños;
- pruebas de regresión;
- diagnóstico de condicionamiento.


## 7. Binding: pybind11 frente a nanobind

### pybind11

Ventajas:

- ecosistema amplio;
- integración madura con clases C++;
- `py::smart_holder`;
- Buffer Protocol;
- soporte de arrays y excepciones;
- migración relativamente directa desde wrappers existentes.

`pybind11` 3 integra `smart_holder`, que mejora la interoperabilidad entre `unique_ptr`, `shared_ptr` y objetos Python. Para una clase que exporta memoria, debe usarse explícitamente `py::buffer_protocol()`.[^10_6][^10_7]

### nanobind

Nanobind puede ser superior si la prioridad principal es:

- menor overhead;
- objetos C++ más compactos;
- intercambio de arrays NumPy/PyTorch/JAX;
- DLPack;
- Python free-threaded;
- menor coste de conversión.

Su documentación destaca soporte de `nb::ndarray`, Buffer Protocol, DLPack y ownership sin aliasing de memoria liberada. También proporciona soporte para builds free-threaded de Python desde versiones recientes.[^10_8][^10_9][^10_10]

### Decisión

| Requisito | Elección |
| :-- | :-- |
| API C++ grande y estable | pybind11 |
| Migración incremental | pybind11 |
| Máximo rendimiento del binding | nanobind |
| DLPack y arrays heterogéneos | nanobind |
| Menor riesgo de adopción | pybind11 |
| Python free-threaded prioritario | evaluar ambos |
| Stable ABI estricto | extensión CPython específica |

Para V909, la recomendación conservadora es pybind11 si el proyecto ya tiene infraestructura C++; nanobind debe evaluarse mediante un benchmark de binding y ownership, no sólo por claims de rendimiento.

## 8. Zero-copy y ownership correcto

El objeto propietario debe tener esta relación:

```text
NativeSolver / MappedRegion
        owns RAII resource
              ↑
        Python wrapper
              ↑
      memoryview / ndarray
```

No devolver:

```cpp
py::memoryview::from_buffer(raw_ptr, ...)
```

si `raw_ptr` puede quedar inválido al destruir el objeto C++. La vista debe mantener vivo el propietario mediante el objeto exportador o una vista que conserve `shared_ptr`.

La clase de binding:

```cpp
py::class_<MappedRegion, py::smart_holder>(
    m, "MappedRegion", py::buffer_protocol())
    .def_buffer([](MappedRegion& r) {
        return py::buffer_info(
            r.data(),
            sizeof(float),
            py::format_descriptor<float>::format(),
            2,
            {r.rows(), r.cols()},
            {r.stride_row(), r.stride_col()});
    });
```

El constructor debe rechazar:

- tamaños desbordados;
- strides inválidos;
- write sobre mapping read-only;
- alignment insuficiente;
- buffers con lifetime externo no retenido.


## 9. DLPack para GPU

Si el solver trabaja directamente sobre tensores GPU, Buffer Protocol no es suficiente para todos los frameworks porque tradicionalmente representa memoria CPU. Exponer también DLPack permite transferencia zero-copy entre PyTorch, JAX, CuPy y el binding nativo.

Contrato conceptual:

```python
tensor = solver.output_dlpack()
x = torch.from_dlpack(tensor)
```

El productor debe transferir ownership del evento y del almacenamiento según el protocolo. No liberar la memoria GPU hasta que el consumidor haya terminado.

La arquitectura debería distinguir:

```text
CPU:
    Buffer Protocol / py::buffer

GPU:
    DLPack / __dlpack__

mapped host/device:
    owner object + explicit synchronization
```

Para un mapping CUDA/ROCm, incluir el device, stream y event asociados en el capsule o descriptor de interoperabilidad.

## 10. Free-threaded Python y GIL

No liberar el GIL de forma indiscriminada. El núcleo C++ puede ejecutarse sin el GIL si no accede a objetos Python:

```cpp
.def("solve", [](Solver& s, const Input& b) {
    py::gil_scoped_release release;
    return s.solve(b);
});
```

Pero el resultado debe construirse y exponerse con el GIL recuperado.

Si se pretende soportar Python free-threaded:

- no usar estado global mutable sin sincronización;
- separar caches por solver o por thread;
- proteger el registry de buffers;
- evitar referencias Python en callbacks de kernels;
- revisar la semántica de destructores;
- ejecutar ThreadSanitizer en el wrapper.

Nanobind documenta explícitamente su soporte para free-threading y mecanismos de locking localizado. pybind11 también ofrece soporte para builds sin GIL, pero la declaración de que un módulo es libre de GIL sólo debe hacerse después de una auditoría de concurrencia.[^10_9][^10_10]

## 11. Contrato de API recomendado

```python
solver = NativeFGMRES(
    tolerance=1e-10,
    max_iterations=200,
    restart=40,
    recycle_rank=8,
    precision="mixed",
    backend="rocm",
)

result = solver.solve(
    rhs,
    operator=operator_handle,
    low_rank_u=U,
    low_rank_v=V,
)
```

El resultado debe ser estructurado:

```python
result.solution
result.converged
result.iterations
result.restarts
result.residual_norm
result.true_residual_norm
result.condition_estimate
result.backend
result.precision
result.used_fallback
```

No esconder la activación de fallback ni el cambio de precisión.

## 12. Verificación formal y pruebas

### Equivalencia algebraica

Para tamaños pequeños:

$$
\|x_{\mathrm{dense}}-x_{\mathrm{matrixfree}}\|
$$

y:

$$
\|b-\mathcal{L}x_{\mathrm{matrixfree}}\|.
$$

### Propiedad Woodbury

Comparar:

```text
apply_low_rank_inverse(b)
```

contra:

```text
solve_explicit_dense(A + U @ V.T, b)
```

sólo en matrices pequeñas.

### Propiedad de Stiefel

Después de cada transformación:

$$
\|Y^TY-I\|_F
$$

debe permanecer bajo el umbral establecido.

### Ownership

Probar:

```text
destruir solver antes de memoryview
mover solver
crear múltiples vistas
excepción durante constructor
cierre explícito con vistas activas
GC forzado
threads concurrentes
```

Usar AddressSanitizer, UndefinedBehaviorSanitizer y pruebas de Python con `gc.collect()`.

### Memoria GPU

Comprobar:

```text
no alloc/free por iteración normal
no use-after-free en streams
eventos correctamente esperados
buffers DLPack vivos hasta consumo
```


## 13. Criterios de aceptación

El cambio puede aprobarse si cumple simultáneamente:

### Corrección

$$
\frac{\|b-\mathcal{L}x\|}
{\|b\|}
\leq \tau.
$$

### Escalabilidad

- no formar matrices $2K\times2K$;
- memoria subcuadrática respecto del solver denso;
- coste dominado por productos operador-vector;
- núcleo reducido limitado a $r\times r$.


### Estabilidad

- sin NaN/Inf;
- sin crecimiento inexplicado de iteraciones;
- convergencia bajo precisión mixta;
- fallback observable y controlado.


### FFI

- cero dangling pointers en pruebas de vida útil;
- ownership definido para todos los retornos;
- memoryview/ndarray conserva al propietario;
- no se expone handle liberable;
- sin data races en modo concurrente.


### Rendimiento

- menor memoria pico;
- menor p99;
- menor número de llamadas al allocator;
- throughput no inferior al baseline en tamaños pequeños;
- mejora clara en $K$ elevado.


## Ruta SOTA recomendada

La implementación final debería seguir este orden:

```text
1. Crear operador matrix-free y contrato de residual.
2. Implementar Woodbury con núcleo reducido.
3. Añadir compresión QR/SVD del rango.
4. Integrar FGMRES con restart.
5. Añadir FGMRES-DR/recycling.
6. Implementar precisión mixta con residual externo en alta precisión.
7. Crear núcleo C++ RAII independiente de Python.
8. Exponer clases con pybind11 smart_holder.
9. Añadir Buffer Protocol y DLPack.
10. Ejecutar dual-run contra solver denso.
11. Activar canary y fallback observable.
12. Retirar ctypes y el solve denso sólo tras cumplir métricas.
```

La innovación SOTA no es eliminar indiscriminadamente lo anterior, sino reemplazar la ruta costosa por una combinación adaptativa:

$$
\boxed{
\text{Woodbury comprimido}
+
\text{FGMRES-DR}
+
\text{precisión mixta}
+
\text{residual fiable}
+
\text{binding RAII zero-copy}
}
$$

Así se conserva una ruta de diagnóstico para matrices pequeñas, pero el camino de producción abandona la concatenación densa, la inversión formal y la gestión pasiva de `ctypes`.

<span style="display:none">[^10_11][^10_12][^10_13][^10_14][^10_15][^10_16][^10_17][^10_18][^10_19][^10_20][^10_21][^10_22][^10_23][^10_24][^10_25][^10_26][^10_27][^10_28][^10_29][^10_30][^10_31][^10_32][^10_33][^10_34][^10_35][^10_36][^10_37]</span>

<div align="center">⁂</div>

[^10_1]: https://isl.stanford.edu/talks/slides/2025q4/michal-derezinski.pdf

[^10_2]: https://arxiv.org/html/2110.04017v2

[^10_3]: https://ar5iv.labs.arxiv.org/html/2404.17870

[^10_4]: https://onlinelibrary.wiley.com/doi/10.1002/nla.70117

[^10_5]: https://onlinelibrary.wiley.com/doi/full/10.1002/nla.70117

[^10_6]: https://pigweed.googlesource.com/third_party/github/pybind/pybind11/+/refs/tags/v3.0.3/docs/changelog.md

[^10_7]: https://pybind11.readthedocs.io/en/stable/upgrade.html

[^10_8]: https://nanobind.readthedocs.io/en/latest/changelog.html

[^10_9]: https://nanobind.readthedocs.io/en/latest/why.html

[^10_10]: https://nanobind.readthedocs.io/en/latest/free_threaded.html

[^10_11]: https://www.informs-sim.org/wsc25papers/inv132.pdf

[^10_12]: https://pybind11.readthedocs.io/en/stable/changelog.html

[^10_13]: https://github.com/pybind/pybind11

[^10_14]: https://github.com/pybind/pybind11/blob/master/include/pybind11/pybind11.h

[^10_15]: https://github.com/pybind/pybind11/blob/master/docs/changelog.rst

[^10_16]: https://sparsedays.cerfacs.fr/wp-content/uploads/sites/72/2025/05/Sparse-days-2025-booklet.pdf

[^10_17]: https://sparsedays.cerfacs.fr/wp-content/uploads/sites/72/2025/05/Sparse-days-2025-booklet-1.pdf

[^10_18]: https://hal.science/hal-04525918v2/document

[^10_19]: https://github.com/lattice/quda/wiki/EigCG,-GMRES-DR,-and-FGMRES-DR

[^10_20]: https://research.chen.pw/slides.pdf

[^10_21]: https://pdfs.semanticscholar.org/334a/13bc6abe86611e1bc5ec0ec67916aaf2d894.pdf

[^10_22]: https://focm2026.univie.ac.at/?page_id=1450

[^10_23]: https://www.emergentmind.com/topics/randomized-solver

[^10_24]: https://pdfs.semanticscholar.org/1d72/f2cda37af2937d84bf165d1a154a8847a0fc.pdf

[^10_25]: https://nanobind.readthedocs.io/en/latest/porting.html

[^10_26]: https://pybind11.readthedocs.io/en/stable/advanced/pycpp/index.html

[^10_27]: https://raw.githubusercontent.com/pybind/pybind11/master/include/pybind11/detail/internals.h

[^10_28]: https://tessl.io/registry/tessl/pypi-pybind11/3.0.0/files/docs/advanced-features.md

[^10_29]: https://pybind11.readthedocs.io/\_/downloads/en/stable/pdf/

[^10_30]: https://pybind11.readthedocs.io/\_/downloads/en/latest/pdf/

[^10_31]: https://nanobind.readthedocs.io/en/latest/api_core.html

[^10_32]: https://nanobind.readthedocs.io/\_/downloads/en/latest/pdf/

[^10_33]: https://arxiv.org/html/2607.22004v1

[^10_34]: https://nanobind.readthedocs.io/en/latest/ndarray.html

[^10_35]: https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html

[^10_36]: https://pybind11.readthedocs.io/en/stable/advanced/misc.html

[^10_37]: https://github.com/pybind/pybind11/releases

