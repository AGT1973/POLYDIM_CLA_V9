<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## Evaluación

El diagnóstico de v911 es **correcto y ataca la causa raíz**: deslogaritmizar el RMS dentro de la reducción podía producir `+Inf`; después, `1 / (+Inf + eps)` daba `0`, anulando la matriz y sus gradientes. La solución de conservar el cálculo en logaritmos y obtener la escala mediante `exp(-log_rms)` evita ese overflow, porque el exponente es no positivo para un RMS finito positivo. El principio coincide con la forma estable estándar de log-sum-exp: desplazar por el máximo evita exponentes positivos grandes.[^1_1][^1_2]

Para RMS:

$$
\operatorname{RMS}(x)=\sqrt{\frac{1}{N}\sum_i x_i^2}
$$

la forma estable es:

$$
\log \operatorname{RMS}(x)
=
\frac12\left[
\operatorname{LSE}(2\log|x_i|)-\log N
\right]
$$

y la escala:

$$
s=\exp(-\log \operatorname{RMS})
$$

Luego:

$$
y_i=x_i\,s
$$

## Valoración de la solución v911

| Aspecto | Evaluación |
| :-- | :-- |
| Eliminación del overflow del RMS | Correcta |
| Preservación de gradientes | Correcta para entradas finitas |
| Riesgo de underflow | Generalmente benigno; produce escala cero solo cuando la magnitud es demasiado pequeña para representarse |
| Coste computacional | Mayor que una suma de cuadrados convencional |
| Compatibilidad con `float64` | Buena |
| Robustez frente a `Inf`/`NaN` de entrada | Incompleta si no se validan explícitamente |
| Estado “SOTA” | Bueno como parche crítico, pero no necesariamente óptimo como kernel de producción |

El umbral aproximado $709.78$ para `exp` en `float64` hace plausible el fallo descrito para valores logarítmicos cercanos a $710$. Sin embargo, conviene distinguir entre el valor de entrada $x_i$ y el valor intermedio $2\log|x_i|$: el overflow ocurre al exponentiar ese intermedio, no necesariamente porque el elemento original sea literalmente $710$.

## Mejoras recomendadas

### 1. Preferir `log1p` y evitar sumar `eps` fuera del dominio log

Si la operación pretendida es:

$$
s=\frac{1}{\operatorname{RMS}+\varepsilon}
$$

entonces calcular simplemente:

$$
s=\exp(-\log \operatorname{RMS})
$$

no es exactamente equivalente: omite $\varepsilon$. La forma estable sería:

$$
s=\exp\left[-\left(\log \operatorname{RMS}
+\log\left(1+\frac{\varepsilon}{\operatorname{RMS}}\right)\right)\right]
$$

o, usando $r=\log\operatorname{RMS}$:

$$
\log(\operatorname{RMS}+\varepsilon)
=
\operatorname{logaddexp}(r,\log\varepsilon)
$$

$$
s=\exp[-\operatorname{logaddexp}(r,\log\varepsilon)]
$$

Esto preserva la semántica exacta del denominador y evita construir valores enormes. En implementaciones prácticas, `logaddexp` es preferible a `log(exp(r) + eps)`.

### 2. Usar directamente una reducción de suma de cuadrados escalada

Aunque log-space es robusto, no siempre es la opción más rápida ni la de menor error. Para RMS puro, una alternativa numéricamente muy sólida es una suma escalada tipo `lassq`:

$$
m=\max_i |x_i|
$$

$$
\operatorname{RMS}(x)
=
m\sqrt{\frac{1}{N}\sum_i \left(\frac{x_i}{m}\right)^2}
$$

Así nunca se calcula $x_i^2$ directamente cuando $x_i$ es grande. Para una matriz, puede hacerse por fila, bloque o tensor completo, según la semántica de normalización. Esta estrategia suele ser mejor para un kernel de alto rendimiento porque requiere operaciones más baratas que `log`, `exp` y `logaddexp`.

**Recomendación:** mantener la ruta log-space como fallback o modo de máxima robustez, y usar una reducción escalada para entradas finitas normales.

### 3. Evitar `log(abs(x))` cuando $x=0$

Debe tratarse explícitamente:

- $x=0 \Rightarrow \log|x|=-\infty$.
- Si todos los elementos son cero, el RMS es cero.
- La escala debe ser $1/\varepsilon$, no `NaN`.

Una implementación robusta debe manejar:

```cpp
if (x == 0) log_abs_x = -INFINITY;
```

y asegurarse de que la reducción de `-INFINITY` no genere resultados inválidos.

### 4. Definir política para `NaN` e `Inf`

La solución v911 evita el overflow generado internamente, pero no resuelve entradas no finitas:

- Si existe `NaN`, el resultado debería ser `NaN` de forma determinista.
- Si existe `Inf`, el RMS es `Inf` y la escala es cero; multiplicar `Inf * 0` puede producir `NaN`.
- Si se requiere tolerancia operacional, hay que documentar si se propagan, se rechazan o se saturan.

No conviene ocultar estos casos con clipping silencioso: puede convertir un problema de datos en un resultado aparentemente válido.

### 5. Cuidar el backward

La derivada de RMSNorm, sin peso aprendido, puede escribirse como:

$$
y_i=\frac{x_i}{r}
$$

$$
\frac{\partial L}{\partial x_i}
=
\frac{1}{r}
\left(
g_i-\frac{x_i}{r^2}
\frac{1}{N}\sum_j g_jx_j
\right)
$$

donde $r$ incluye el término de estabilidad correspondiente. El backward debe reutilizar una escala finita y consistente con el forward. Es importante no recalcular el RMS con una ruta distinta, porque eso puede introducir discrepancias grandes entre forward y backward.

También conviene comprobar que:

- no aparezcan `NaN` ni `Inf` en `dx`;
- el gradiente no colapse a cero para entradas grandes pero finitas;
- el gradiente numérico coincida con el analítico en magnitudes extremas.


## Plan de pruebas SOTA

Como mínimo, añadiría estos casos:

1. **Valores grandes**
    - $x=10^{100}$, $10^{200}$, `DBL_MAX`.
    - Mezclas como `[1e300, 1e-300]`.
    - Valores logarítmicos alrededor de $709$, $710$ y $745$.
2. **Valores pequeños**
    - $x=0$.
    - Subnormales.
    - Matrices cuyos valores sean menores que `eps`.
3. **Casos no finitos**
    - `NaN`.
    - `+Inf`.
    - `-Inf`.
    - Mezclas de finitos e infinitos.
4. **Invariancia de escala**
Para $c>0$:

$$
\operatorname{RMSNorm}(cx)\approx \operatorname{RMSNorm}(x)
$$

salvo por el efecto esperado de $\varepsilon$.
5. **Equivalencia con referencia de alta precisión**
Comparar contra una implementación `long double`, MPFR o una referencia escalada. Las tolerancias deben depender del dtype; las implementaciones modernas de RMSNorm también eligen el `eps` según el tipo de cálculo, en vez de imponer siempre el mismo valor.[^1_3][^1_4]
6. **Gradientes**
    - finite differences en entradas normales;
    - gradcheck en entradas grandes;
    - gradcheck cerca de cero;
    - verificación explícita de que no haya gradientes totalmente nulos tras el caso de overflow.
7. **Metamorphic testing**
    - permutar elementos no debe cambiar el RMS;
    - duplicar todos los elementos debe conservar la salida normalizada, excepto el efecto de `eps`;
    - cambiar simultáneamente el signo de todos los elementos debe cambiar el signo de la salida, no su magnitud.

## Veredicto

**v911 debe aceptarse como corrección crítica**, porque elimina el camino destructivo `RMS = Inf → scale = 0 → matriz anulada`. No obstante, la versión final debería:

- incorporar `logaddexp(log_rms, log_eps)` si se quiere conservar exactamente el denominador con epsilon;
- definir explícitamente el comportamiento frente a ceros, `NaN` e `Inf`;
- validar el backward con gradcheck;
- considerar una reducción escalada tipo `lassq` como ruta rápida para valores finitos;
- mantener log-space como fallback robusto para rangos extremos.

En síntesis: **la corrección es matemáticamente válida y suficientemente sólida para cerrar el bug, pero aún requiere endurecimiento de casos límite y optimización del kernel para considerarse una implementación de nivel SOTA.**

<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://mc-stan.org/docs/2_23/stan-users-guide/log-sum-of-exponentials.html

[^1_2]: https://mc-stan.org/docs/2_26/stan-users-guide/log-sum-of-exponentials.html

[^1_3]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html

[^1_4]: https://docs.pytorch.org/docs/main/generated/torch.nn.RMSNorm.html

[^1_5]: https://docs.pytorch.org/docs/2.12/generated/torch.nn.RMSNorm.html

[^1_6]: https://docs.pytorch.org/docs/2.14/generated/torch.nn.RMSNorm.html

[^1_7]: https://docs.vllm.ai/en/latest/api/vllm/model_executor/layers/layernorm/

[^1_8]: https://mc-stan.org/docs/2_18/stan-users-guide/summing-out-the-responsibility-parameter.html

[^1_9]: https://raw.org/book/machine-learning/log-sum-exp-trick/

[^1_10]: https://huggingface.co/Hazan-Lab/Mamba_546M/resolve/383d55e6ea8aaef314f7b7afe30cc4d643ab58c6/norms.py?download=true

[^1_11]: https://getablaza.com/tech-tree/numerical-stability/

[^1_12]: https://deepwiki.com/Dao-AILab/quack/6.2-normalization-testing

[^1_13]: https://docs.quactuary.com/user_guide/numerical_stability.html

[^1_14]: https://neurapath.in/blog/numerical-stability-in-exponentials-and-softmax

[^1_15]: https://github.com/bzhangGo/rmsnorm


---

# Profundiza soluciones y mejoras sota

La mejora SOTA no debería limitarse a “mantener todo en log-space”. La solución más robusta es una implementación **híbrida**: reducción escalada para el camino normal, log-space como fallback extremo, acumulación en mayor precisión, semántica exacta de $\varepsilon$, y contratos explícitos para `NaN`, `Inf`, gradientes y determinismo.

## 1. Fijar primero la semántica matemática

Hay dos fórmulas distintas que suelen confundirse:

$$
r_1=\sqrt{\frac{1}{N}\sum_i x_i^2+\varepsilon}
$$

y:

$$
r_2=\sqrt{\frac{1}{N}\sum_i x_i^2}+\varepsilon
$$

La práctica estándar de RMSNorm coloca $\varepsilon$ **dentro de la raíz**, como en PyTorch y Transformer Engine.[^2_1][^2_2]

Por tanto, la escala correcta es:

$$
s=\frac{1}{\sqrt{\operatorname{mean}(x_i^2)+\varepsilon}}
$$

En logaritmos:

$$
\log r
=
\frac{1}{2}\operatorname{logaddexp}
\left(
\log\left(\frac{1}{N}\sum_i x_i^2\right),
\log\varepsilon
\right)
$$

$$
s=\exp(-\log r)
$$

Esto es preferible a `1 / (RMS + eps)`, porque conserva la definición habitual y no altera innecesariamente la escala en valores pequeños.

## 2. Arquitectura recomendada: tres rutas

### Ruta A: rápida y estable

Para entradas finitas, usar una reducción escalada:

$$
m=\max_i |x_i|
$$

Si $m=0$:

$$
r=\sqrt{\varepsilon}, \qquad s=\frac{1}{\sqrt{\varepsilon}}
$$

Si $m>0$:

$$
q=\frac{1}{N}\sum_i\left(\frac{x_i}{m}\right)^2
$$

$$
r=\sqrt{m^2q+\varepsilon}
$$

Pero no conviene calcular $m^2q$ directamente si $m$ es enorme. Es mejor trabajar con:

$$
\log r
=
\frac12\operatorname{logaddexp}
\left(
2\log m+\log q-\log N,\log\varepsilon
\right)
$$

o, para el caso habitual donde $\varepsilon$ es despreciable:

$$
s\approx \frac{1}{m\sqrt{q}}
$$

Esta técnica es conceptualmente equivalente a una reducción `lassq`, que evita formar $x_i^2$ en magnitudes peligrosas.

### Ruta B: log-space completo

Para rangos extremos:

```cpp
log_abs = log(abs(x))
log_sq  = 2 * log_abs
log_sum = logsumexp(log_sq)
log_mean = log_sum - log(N)
log_rms = 0.5 * logaddexp(log_mean, log_eps)
scale = exp(-log_rms)
```

La implementación de `logsumexp` debe usar desplazamiento:

```cpp
m = max(log_sq)
log_sum = m + log(sum(exp(log_sq - m)))
```

Nunca debe aparecer:

```cpp
exp(log_sq)
```

sin restar primero el máximo. El objetivo del método log-sum-exp es precisamente evitar ese overflow.[^2_3][^2_4]

### Ruta C: fallback defensivo

Si la entrada contiene valores no finitos:

- `NaN`: propagar `NaN`, salvo que el contrato del kernel indique rechazo.
- `Inf`: devolver una salida definida; no permitir `Inf * 0 = NaN` accidental.
- mezcla de `Inf` y valores finitos: normalizar según una política explícita o reportar error.

La política recomendada para entrenamiento es **propagación determinista**, no clipping silencioso. Ocultar un `NaN` puede hacer que el modelo continúe entrenando con estado corrupto.

## 3. Mejor solución práctica en C++

Una versión conceptualmente sólida sería:

```cpp
template <typename T>
struct RmsStats {
    double log_rms;
    bool has_nan;
    bool has_inf;
};

RmsStats rms_log_stable(const T* x, int64_t n, double eps) {
    double max_log_sq = -INFINITY;
    bool has_nan = false;
    bool has_inf = false;

    for (int64_t i = 0; i < n; ++i) {
        double v = static_cast<double>(x[i]);

        if (std::isnan(v)) {
            has_nan = true;
            continue;
        }

        if (std::isinf(v)) {
            has_inf = true;
            continue;
        }

        if (v != 0.0) {
            max_log_sq = std::max(max_log_sq, 2.0 * std::log(std::abs(v)));
        }
    }

    if (has_nan) {
        return {NAN, true, has_inf};
    }

    if (has_inf) {
        return {INFINITY, false, true};
    }

    if (max_log_sq == -INFINITY) {
        return {0.5 * std::log(eps), false, false};
    }

    double sum = 0.0;

    for (int64_t i = 0; i < n; ++i) {
        double v = static_cast<double>(x[i]);

        if (v != 0.0) {
            double z = 2.0 * std::log(std::abs(v)) - max_log_sq;
            sum += std::exp(z);
        }
    }

    double log_mean_sq =
        max_log_sq + std::log(sum) - std::log(static_cast<double>(n));

    double log_rms =
        0.5 * std::logaddexp(log_mean_sq, std::log(eps));

    return {log_rms, false, false};
}
```

En un kernel de producción habría que sustituir `std::logaddexp` por una implementación portable:

```cpp
double logaddexp(double a, double b) {
    if (a == -INFINITY) return b;
    if (b == -INFINITY) return a;

    double m = std::max(a, b);
    return m + std::log1p(std::exp(-std::abs(a - b)));
}
```

Para CPU SIMD, GPU o CUDA, la misma lógica debe implementarse con intrinsics o funciones device equivalentes.

## 4. Corrección importante: evitar `exp(-log_rms)` cuando no hace falta

Aunque `exp(-log_rms)` es seguro para el overflow original, todavía puede underflowar si $r$ supera el rango representable. Eso normalmente equivale a una escala tan pequeña que la salida es numéricamente cero.

Una mejora consiste en calcular el producto directamente en forma logarítmica:

$$
y_i=\operatorname{sign}(x_i)
\exp(\log|x_i|-\log r)
$$

Esto reduce el riesgo de formar primero una escala subnormal:

```cpp
double log_y = log_abs_x - log_rms;
double y = copysign(exp(log_y), x);
```

Sin embargo, esta variante tiene una desventaja: requiere un `log` adicional por elemento y puede perder precisión relativa cuando $x_i$ y $r$ son muy cercanos. Por eso:

- usar `x_i * scale` en el camino común;
- usar `exp(log_abs_x - log_rms)` solo en el fallback extremo.


## 5. La opción más eficiente: `lassq` escalado

Para producción, mi recomendación principal sería una reducción tipo Blue/LASSQ:

```cpp
double scale = 0.0;
double sumsq = 1.0;

for each x:
    ax = abs(x)

    if (ax != 0):
        if (scale < ax):
            sumsq = 1.0 + sumsq * (scale / ax) * (scale / ax)
            scale = ax
        else:
            sumsq += (ax / scale) * (ax / scale)

rms = scale * sqrt(sumsq / n)
```

Después se incorpora $\varepsilon$ de forma segura:

$$
r=\sqrt{\operatorname{rms}^2+\varepsilon}
$$

Si `rms` puede desbordar, se mantiene el resultado en logaritmos:

$$
\log r=
\frac12\operatorname{logaddexp}
(2\log(\operatorname{rms}),\log\varepsilon)
$$

Ventajas:

- menos funciones trascendentes;
- menor coste que `logsumexp`;
- buena precisión para datos finitos;
- evita overflow de cuadrados;
- adecuado para CPU vectorizada y kernels GPU.

La ruta log-space completa sigue siendo valiosa como oráculo de pruebas y fallback para rangos patológicos.

## 6. Acumulación y tipos

La entrada y la acumulación no deben compartir necesariamente el mismo dtype.


| Entrada | Acumulación mínima recomendada | Escala |
| :-- | --: | --: |
| `float16` | `float32` | `float32` |
| `bfloat16` | `float32` | `float32` |
| `float32` | `float32` o `float64` según precisión requerida | `float32` |
| `float64` | `float64` | `float64` |

En `float16`, formar $x^2$ en el mismo tipo es especialmente peligroso; la acumulación debe promoverse a `float32`. La documentación de RMSNorm de PyTorch también distingue el `opmath` y selecciona el epsilon en función del tipo de cálculo.[^2_1]

Para v911 en `float64`, la promoción no resuelve por sí sola el problema, porque el overflow ocurre incluso en `float64`; hace falta la reducción escalada o log-space.

## 7. Epsilon adaptable por dtype

No debería existir un único `eps` global para todos los tipos.

Una política razonable:

- `float16`: $10^{-5}$ o mayor.
- `bfloat16`: $10^{-5}$–$10^{-6}$.
- `float32`: $10^{-6}$ o el epsilon del tipo de acumulación.
- `float64`: `numeric_limits<double>::epsilon()` si se busca semántica de precisión, o un valor mayor si se busca regularización.

Pero hay que separar dos funciones:

1. `eps_numerical`: evita división inestable.
2. `eps_model`: forma parte deliberada de la definición del modelo.

Cambiar automáticamente `eps` según la magnitud de los datos puede romper reproducibilidad y modificar la dinámica del entrenamiento. Es mejor seleccionar por dtype y documentarlo.

## 8. Backward estable

Para:

$$
y_i=\gamma_i\frac{x_i}{r}
$$

con:

$$
r=\sqrt{\frac{1}{N}\sum_j x_j^2+\varepsilon}
$$

el gradiente respecto a $x_i$ es:

$$
\frac{\partial L}{\partial x_i}
=
\frac{\gamma_i g_i}{r}
-
\frac{x_i}{N r^3}
\sum_j \gamma_j g_j x_j
$$

Una forma más estable es reutilizar:

$$
s=\frac{1}{r}
$$

$$
c=\frac{s^3}{N}\sum_j \gamma_jg_jx_j
$$

$$
dx_i=s\gamma_i g_i-cx_i
$$

Pero si $s$ es subnormal o $r$ es extremo, conviene calcular las partes en una escala común, especialmente en `float16`/`bfloat16`.

Recomendaciones:

- guardar `log_rms` o `scale` del forward;
- no recalcular estadísticas distintas en backward;
- acumular el producto $\sum_j \gamma_jg_jx_j$ en `float32` o `float64`;
- validar el backward con entradas de magnitud $10^{-300}$, $10^{300}$, cero y combinaciones heterogéneas.


## 9. No usar pRMSNorm como “solución” al overflow

pRMSNorm reduce el coste estimando el RMS con un subconjunto de dimensiones, pero no corrige el problema matemático principal. Además, el trabajo original reporta inestabilidad de gradientes cuando la fracción muestreada es pequeña.[^2_5]

Puede ser útil como optimización independiente, pero no debe sustituir una reducción estable:

- primero estabilizar RMSNorm completo;
- después medir pRMSNorm;
- usar muestreo suficientemente grande;
- validar la varianza del estimador y el impacto sobre outliers.

Para una matriz topológica donde un solo valor extremo puede ser semánticamente importante, pRMSNorm puede ser particularmente arriesgado.

## 10. Contrato para casos extremos

Debe documentarse algo equivalente a lo siguiente:


| Entrada | RMS | Escala | Salida recomendada |
| :-- | --: | --: | :-- |
| Todo cero | $\sqrt{\varepsilon}$ | $1/\sqrt{\varepsilon}$ | Todo cero |
| Finita grande | Finito | Pequeña pero no necesariamente cero | Normalizada |
| RMS mayor que `DBL_MAX` matemático | `+Inf` lógico | $0$ lógico | Calcular salida en log-ratio |
| Algún `NaN` | `NaN` | `NaN` | Propagar |
| Algún `Inf` | `Inf` | $0$ | Política explícita, no `Inf * 0` |

El último caso requiere cuidado. Si hay un único `Inf`, la salida matemática del componente infinito sería aproximadamente una forma de `Inf/Inf`, que no tiene representación convencional útil. Lo más sano es tratarlo como entrada inválida y propagar un estado de error o `NaN` de forma determinista.

## 11. Suite SOTA de validación

### Exactitud

Comparar contra:

- referencia `long double`;
- referencia MPFR para casos extremos;
- implementación PyTorch para rangos normales;
- ruta `lassq`;
- ruta log-space.

Medir:

$$
\text{error relativo}
=
\frac{|y_{\text{kernel}}-y_{\text{ref}}|}
{\max(1,|y_{\text{ref}}|)}
$$

y también ULPs para valores cercanos a uno.

### Propiedades invariantes

- permutación de dimensiones: mismo RMS;
- cambio global de signo: salida con signo invertido;
- escala global $c$: salida casi invariante;
- duplicación de todos los elementos: misma salida, salvo efecto de $\varepsilon$;
- vector unitario: resultado conocido;
- vector constante: salida aproximadamente $\pm1$.


### Stress tests

Usar exponentes logarítmicamente espaciados:

$$
x_i=\pm 2^k,\qquad k\in[-1074,1023]
$$

y combinaciones:

```text
[DBL_MIN, 1, DBL_MAX]
[1e-300, 1e300]
[0, 0, 0]
[NaN, 1, 2]
[Inf, 1, 2]
```


### Gradientes

Comparar:

- gradiente analítico;
- finite differences;
- autodiferenciación de referencia;
- backward fusionado;
- backward no fusionado.

Debe verificarse especialmente que no vuelva a ocurrir:

```text
forward = matriz cero
backward = gradiente cero
```


## 12. Diseño final recomendado

Mi diseño de producción sería:

1. Acumular en `float32` o `float64` según dtype.
2. Detectar `NaN` e `Inf` durante la reducción.
3. Usar `lassq` o reducción por máximo para entradas finitas.
4. Incorporar $\varepsilon$ dentro de la raíz mediante `logaddexp` cuando el rango sea extremo.
5. Usar `x * scale` normalmente.
6. Usar `exp(log_abs_x - log_rms)` solo para el fallback donde la escala directa underflowaría.
7. Guardar `log_rms` o estadísticas equivalentes para backward.
8. Mantener una ruta log-space de referencia activable por flag.
9. Añadir tests de rango completo y gradcheck.
10. Instrumentar contadores de overflow evitado, underflow, `NaN` e `Inf`.

## Veredicto técnico

v911 es una corrección válida, pero la implementación SOTA debería evolucionar hacia:

$$
\boxed{
\text{LASSQ/escala para rendimiento}
+
\text{log-space para rango extremo}
+
\text{epsilon dentro de la raíz}
+
\text{backward coherente}
+
\text{contratos explícitos de no finitud}
}
$$

La mejora más importante no es únicamente sustituir `RMS` por `exp(-log_rms),` sino garantizar que **ningún punto intermedio forme cuadrados, exponentes o productos fuera de rango**, y que el forward y el backward compartan exactamente la misma estadística normalizadora.

<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_6][^2_7][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://docs.pytorch.org/docs/main/generated/torch.nn.RMSNorm.html

[^2_2]: https://docs.nvidia.com/deeplearning/transformer-engine-releases/release-1.10/user-guide/api/c/rmsnorm.html

[^2_3]: https://mc-stan.org/docs/2_23/stan-users-guide/log-sum-of-exponentials.html

[^2_4]: https://mc-stan.org/docs/2_18/stan-users-guide/summing-out-the-responsibility-parameter.html

[^2_5]: https://proceedings.neurips.cc/paper_files/paper/2019/file/1e8a19426224ca89e83cef47f1e7f53b-Paper.pdf

[^2_6]: https://proceedings.neurips.cc/paper/2019/file/1e8a19426224ca89e83cef47f1e7f53b-Paper.pdf

[^2_7]: https://docs.pytorch.org/docs/2.8/generated/torch.nn.modules.normalization.RMSNorm.html

[^2_8]: https://arxiv.org/html/2603.17771v2

[^2_9]: https://arxiv.org/html/2607.25494v3

[^2_10]: https://arxiv.org/html/2607.17822v1

[^2_11]: https://arxiv.org/html/2606.17781v1

[^2_12]: https://arxiv.org/html/2503.10251v2

[^2_13]: https://lizeman.github.io/llm-arch-kb/normalization/rmsnorm/

[^2_14]: https://en.wikipedia.org/wiki/RMSNorm

[^2_15]: https://www.aiwiki.ai/wiki/rmsnorm

[^2_16]: https://docs.pytorch.org/docs/2.14/generated/torch.nn.RMSNorm.html

[^2_17]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html


---

# 2. Cancelación Catastrófica en Geodésicas Riemannianas (Brecha Numérica O(N))evalua soluciones y mejoras sota

Falla: La variable chordal_sq acumulaba ingenuamente la varianza (ui−vi)2(u_i - v_i)^2(ui​−vi​)2 bajo un anillo \#pragma omp. Para dimensiones asintóticas D≥107D \\ge 10^7D≥107 y tensores topológicamente próximos, esta reducción directa padece deriva y cancelación catastrófica (floating-point drift).
Estado (v911): Solucionado inyectando un algoritmo iterativo Kahan Compensated Summation local a nivel de hilo, seguido de acumulación segura en la sección crítica, protegiendo la entropía de los últimos bits.

La corrección v911 con Kahan por hilo es **válida como mitigación**, pero no garantiza por sí sola exactitud ni reproducibilidad global. Para una geodésica basada en

$$
d^2(u,v)=\sum_{i=1}^{D}(u_i-v_i)^2
$$

el problema no es exactamente “cancelación catastrófica” dentro de cada cuadrado: después de calcular $u_i-v_i$, el término es no negativo. El fallo principal es la **pérdida de bits durante la resta** y la **deriva acumulativa de la reducción**, agravada por un orden paralelo no determinista.

La suma paralela tampoco es asociativa en punto flotante; distintos árboles de reducción pueden producir resultados distintos aunque los datos sean idénticos.[^3_1]

## 1. Diagnóstico más preciso

Hay tres fuentes separadas de error:

### A. Resta previa

Si $u_i$ y $v_i$ son casi iguales:

$$
\delta_i=u_i-v_i
$$

la resta puede perder cifras significativas cuando los operandos comparten muchos bits iniciales. En `float64`, si $u_i\approx v_i$, el error relativo de $\delta_i$ puede ser grande aunque el error absoluto sea pequeño.

La suma de cuadrados no puede recuperar la información perdida en esa resta.

### B. Cuadrado

Calcular:

```cpp
double d = u[i] - v[i];
double term = d * d;
```

puede provocar:

- underflow si $d$ es extremadamente pequeño;
- overflow si $d$ es grande;
- pérdida de precisión si la magnitud de `d` varía mucho.


### C. Reducción paralela

Aunque cada hilo utilice Kahan, la suma de los acumuladores parciales puede seguir siendo:

- dependiente del orden;
- no reproducible;
- vulnerable a diferencias grandes de magnitud;
- incorrecta si la sección crítica suma directamente todos los parciales.

Kahan local reduce el error de cada segmento, pero no convierte la reducción completa en exacta.

## 2. Evaluación de Kahan por hilo

La estructura v911 probablemente es:

```cpp
#pragma omp parallel
{
    double sum = 0.0;
    double correction = 0.0;

    #pragma omp for
    for (...) {
        double diff = u[i] - v[i];
        double term = diff * diff;

        double y = term - correction;
        double t = sum + y;
        correction = (t - sum) - y;
        sum = t;
    }

    #pragma omp critical
    {
        chordal_sq += sum;
    }
}
```

Esto mejora claramente a la suma ingenua. Sin embargo, tiene cuatro limitaciones:

1. `critical` serializa la fase final.
2. El orden de llegada de los hilos no es determinista.
3. La compensación local no cubre la suma global.
4. Kahan puede perder efectividad cuando los parciales tienen escalas muy diferentes.

Por tanto, lo describiría como:

> corrección numérica local y mitigación parcial de deriva, no reducción reproducible de máxima exactitud.

## 3. Mejora inmediata: reducción jerárquica determinista

La primera mejora SOTA práctica es sustituir la sección crítica por un arreglo de parciales y una reducción jerárquica fija:

```cpp
int nthreads = omp_get_max_threads();
std::vector<double> partial(nthreads, 0.0);
std::vector<double> comp(nthreads, 0.0);

#pragma omp parallel
{
    int tid = omp_get_thread_num();
    double sum = 0.0;
    double c = 0.0;

    #pragma omp for schedule(static)
    for (int64_t i = 0; i < D; ++i) {
        double diff = u[i] - v[i];
        double term = diff * diff;

        double y = term - c;
        double t = sum + y;
        c = (t - sum) - y;
        sum = t;
    }

    partial[tid] = sum;
    comp[tid] = c;
}
```

Después, reducir `partial` con un árbol fijo:

```cpp
for (int stride = 1; stride < nthreads; stride *= 2) {
    for (int i = 0; i + stride < nthreads; i += 2 * stride) {
        partial[i] += partial[i + stride];
    }
}

double chordal_sq = partial[^3_0];
```

Mejor aún, volver a aplicar Kahan o Neumaier en cada nivel del árbol.

Esto proporciona:

- menos dependencia del scheduling;
- mejor precisión que `critical`;
- mejor escalabilidad;
- reproducibilidad si `schedule(static)`, número de hilos y árbol permanecen fijos.

El orden fijo es importante porque la suma flotante no es asociativa.[^3_1]

## 4. Preferir Neumaier cuando las magnitudes difieren

Kahan funciona bien cuando los sumandos tienen escalas relativamente parecidas. Para una reducción de términos potencialmente heterogéneos, Neumaier suele ser más robusto:

```cpp
struct NeumaierSum {
    double sum = 0.0;
    double corr = 0.0;

    void add(double x) {
        double t = sum + x;

        if (std::abs(sum) >= std::abs(x)) {
            corr += (sum - t) + x;
        } else {
            corr += (x - t) + sum;
        }

        sum = t;
    }

    double value() const {
        return sum + corr;
    }
};
```

Para una suma de cuadrados los términos son no negativos, así que la ventaja sobre Kahan puede ser moderada; aun así, Neumaier es más resistente a parciales de magnitud muy distinta durante la combinación global.

Recomendación:

- Kahan para el bucle caliente si el rendimiento domina;
- Neumaier para combinar bloques;
- árbol fijo para reproducibilidad.


## 5. Escalar antes de sumar cuadrados

Una mejora especialmente importante es evitar sumar directamente los cuadrados. Usar una reducción escalada:

$$
m=\max_i |\delta_i|
$$

$$
d^2(u,v)=m^2\sum_i\left(\frac{\delta_i}{m}\right)^2
$$

Si $m=0$, la distancia es cero.

El problema es que $m^2$ aún puede desbordar. Por eso conviene mantener:

$$
\log d^2
=
2\log m+
\log\left(\sum_i(\delta_i/m)^2\right)
$$

o, si el resultado final cabe, materializarlo al final.

Implementación por hilo:

```cpp
struct ScaledSumsq {
    double scale = 0.0;
    double ssq = 1.0;

    void add(double x) {
        double ax = std::abs(x);

        if (ax == 0.0) return;

        if (scale < ax) {
            double r = scale / ax;
            ssq = 1.0 + ssq * r * r;
            scale = ax;
        } else {
            double r = ax / scale;
            ssq += r * r;
        }
    }

    double log_value(int64_t n) const {
        if (scale == 0.0) return -INFINITY;
        return 2.0 * std::log(scale)
             + std::log(ssq)
             - std::log(static_cast<double>(n));
    }
};
```

Para la suma sin normalización por $N$, se elimina `-log(n)`.

Esta técnica evita:

- overflow de $\delta_i^2$;
- underflow de términos pequeños frente a un outlier;
- pérdida completa de la distancia por una escala mal condicionada.

Es especialmente adecuada si la geodésica posteriormente aplica una función como:

$$
\operatorname{dist}(u,v)=\sqrt{d^2(u,v)}
$$

porque puede conservarse directamente:

$$
\log \operatorname{dist}(u,v)
=
\log m+\frac12\log(ssq)
$$

## 6. Mejorar la resta $u_i-v_i$

Si `u` y `v` son valores próximos, la resta es el cuello de botella informacional. Hay varias estrategias.

### A. Aritmética de doble doble

Representar cada valor como una expansión de dos `double`:

$$
x=x_{\text{hi}}+x_{\text{lo}}
$$

y usar `TwoSum`/`TwoDiff` para conservar el residuo:

```cpp
inline void two_diff(double a, double b, double& s, double& e) {
    s = a - b;
    double z = s - a;
    e = (a - (s - z)) - (b + z);
}
```

Entonces:

$$
u-v \approx d_{\text{hi}}+d_{\text{lo}}
$$

y el cuadrado puede calcularse con una transformación exacta del producto:

$$
(d_{\text{hi}}+d_{\text{lo}})^2
=
d_{\text{hi}}^2
+2d_{\text{hi}}d_{\text{lo}}
+d_{\text{lo}}^2
$$

Para `float64`, esto es útil si la distancia es mucho menor que la magnitud absoluta de las coordenadas.

### B. `long double`

En x86, `long double` puede ofrecer precisión extendida, aunque su comportamiento depende de ABI y compilador. No debe asumirse que siempre es IEEE binary128; a menudo es binary80.

Ventajas:

- cambio de código simple;
- alta precisión en la resta y acumulación.

Desventajas:

- rendimiento variable;
- vectorización más difícil;
- comportamiento distinto entre plataformas;
- no es una solución portable fuerte.


### C. Representación centrada

Si las coordenadas tienen un origen común grande, recentrar antes de calcular:

$$
\tilde u_i=u_i-c_i,\qquad
\tilde v_i=v_i-c_i
$$

idealmente con el mismo centro $c_i$. Matemáticamente:

$$
u_i-v_i=\tilde u_i-\tilde v_i
$$

pero una representación centrada puede reducir el rango de magnitudes y mejorar posteriores operaciones geométricas. No recupera bits ya perdidos, pero evita que todo el sistema trabaje alrededor de un offset innecesariamente grande.

### D. Datos de doble componente desde el origen

Si la topología requiere precisión sub-ULP respecto a coordenadas enormes, la solución correcta puede ser almacenar directamente:

```text
value = hi + lo
```

en lugar de intentar recuperar precisión tras haber cuantizado a un solo `double`.

## 7. Exactitud reproducible: ExBLAS y superacumulador

Si el requisito es **bitwise reproducibility**, Kahan no basta. Hay que utilizar:

- expansiones de punto flotante;
- transformaciones sin error, como `TwoSum` y `TwoProd`;
- superacumulador de punto fijo;
- árbol de reducción determinista.

ExBLAS usa precisamente expansiones y acumuladores tipo Kulisch para obtener resultados reproducibles y de alta exactitud en reducciones paralelas.[^3_2][^3_3]

Para una suma de cuadrados, la operación es un dot product:

$$
\sum_i \delta_i\delta_i
$$

Por tanto, una ruta exacta puede usar `TwoProd` para capturar el error del producto y después acumular el resultado en una expansión o superacumulador. Este enfoque puede alcanzar el redondeo correcto y ser independiente del orden paralelo.[^3_4][^3_5]

### Cuándo usarlo

- pruebas de referencia;
- validación científica;
- resultados que deben ser idénticos entre máquinas;
- checkpoints reproducibles;
- optimización geométrica sensible a pequeñas diferencias;
- construcción de oráculos para tests.


### Cuándo no usarlo como ruta por defecto

- kernels de inferencia de baja latencia;
- dimensiones muy grandes donde el coste domina;
- casos donde un error relativo de unos pocos ULPs es aceptable.

La estrategia ideal es tener tres modos:

```text
FAST       -> suma vectorizada / pairwise
STABLE     -> escalada + Neumaier/Kahan
EXACT      -> expansion o superacumulador
```


## 8. Evitar `critical`

La sección crítica debe eliminarse salvo que la simplicidad sea prioritaria. Sus problemas:

- serializa todos los hilos;
- produce orden dependiente del scheduler;
- puede crear variación entre ejecuciones;
- impide una reducción jerárquica eficiente.

Alternativas:

### OpenMP reduction personalizada

Si el compilador lo soporta:

```cpp
#pragma omp declare reduction( \
    neumaier : NeumaierSum : \
    omp_out.combine(omp_in)) \
    initializer(omp_priv = NeumaierSum{})

#pragma omp parallel for reduction(neumaier:acc)
```

La operación `combine` debe ser cuidadosamente definida y, para reproducibilidad estricta, el runtime debe ofrecer un árbol estable. La especificación de OpenMP no siempre garantiza que el orden de reducción sea bitwise determinista entre configuraciones.

### Parciales + árbol fijo

Es la opción más portable y controlable:

1. `schedule(static)`.
2. un acumulador por hilo;
3. combinación en orden de índice de hilo;
4. árbol binario fijo;
5. sin `critical`.

## 9. Manejo de overflow y underflow

Para cada $\delta_i$:

- si `u[i]` o `v[i]` es `NaN`, propagar estado inválido;
- si la resta produce `Inf`, reportar overflow;
- si `delta * delta` desborda, usar suma escalada;
- si `delta` es subnormal, decidir si se preservan subnormales o se acepta FTZ/DAZ.

En x86, activar flush-to-zero puede convertir distancias diminutas en cero. Eso puede ser aceptable en deep learning, pero es peligroso si la geometría depende de diferencias subnormales.

Debe registrarse el modo de hardware:

```text
rounding mode
FTZ enabled/disabled
DAZ enabled/disabled
FMA enabled/disabled
```

También hay que decidir si FMA se permite. `fma(delta, delta, sum)` puede mejorar la exactitud local, pero puede cambiar resultados frente a una implementación sin FMA. Para reproducibilidad entre plataformas, la política debe ser explícita.

## 10. FMA y acumulación

Si el camino rápido usa:

```cpp
sum = std::fma(diff, diff, sum);
```

se redondea una sola vez el producto más la suma. Esto suele mejorar precisión respecto a:

```cpp
sum += diff * diff;
```

Pero FMA no sustituye a una reducción estable:

- no evita que el sumatorio pierda bits;
- no corrige la resta `u-v`;
- puede producir resultados distintos según la arquitectura.

Una combinación razonable es:

```text
diff = compensated_difference(u, v)
term = fma(diff, diff, 0.0)
local_sum = compensated_add(local_sum, term)
```

para la ruta de alta precisión, con una ruta simple y vectorizada para el modo rápido.

## 11. Test de validación recomendado

### Casos de escala

```text
u = 1e300, v = 1e300 - delta
delta = 1e284, 1e200, 1e100
```


### Condición extrema

```text
u_i = 1
v_i = 1 + 2^-52
```

y variantes alrededor del ULP local.

### Cancelación geométrica

Construir vectores donde:

$$
\|u-v\|^2
\ll
\|u\|^2+\|v\|^2
$$

### Rangos mixtos

```text
[1e300, 1e-300, 1, 1e150]
```


### Dimensión grande

- $D=10^7$;
- $D=10^8$, si la memoria lo permite;
- distribuciones log-uniformes;
- un outlier dominante;
- muchos términos idénticos pequeños.


### Reproducibilidad

Ejecutar:

- 1, 2, 4, 8, 16, 32 hilos;
- diferentes afinidades;
- diferentes schedules;
- varias repeticiones.

Registrar:

$$
\max |d^2_k-d^2_{\text{ref}}|
$$

y comparar también la representación binaria exacta.

### Geometría

Si la distancia alimenta una geodésica, no basta con probar `chordal_sq`. Hay que probar:

- simetría: $d(u,v)=d(v,u)$;
- identidad: $d(u,u)=0$;
- positividad;
- comportamiento bajo escalado;
- continuidad al acercar $u$ y $v$;
- estabilidad del gradiente de la geodésica.

La estabilidad de la distancia no garantiza automáticamente estabilidad de la exponencial, logaritmo o proyección Riemanniana que se aplique después.

## 12. Recomendación final por niveles

### Nivel 1: parche mínimo aceptable

- Kahan local;
- parciales por hilo;
- `schedule(static)`;
- árbol fijo;
- eliminar `critical`.


### Nivel 2: solución de producción

- reducción `lassq`/escalada;
- Neumaier para combinación de bloques;
- FMA donde sea compatible;
- acumulación en mayor precisión;
- detección explícita de no finitos;
- tests de escala y reproducibilidad.


### Nivel 3: solución científica SOTA

- resta `TwoDiff` o doble doble;
- `TwoProd` para cuadrados;
- expansión o superacumulador;
- reducción jerárquica reproducible;
- resultado correctamente redondeado;
- modo exacto para validación y checkpoints.


## Veredicto

v911 **mejora sustancialmente** la deriva, pero la frase “protegiendo la entropía de los últimos bits” es demasiado fuerte si solo se usa Kahan local y una sección crítica. La solución no controla completamente:

- la pérdida de precisión en $u_i-v_i$;
- la suma global de parciales;
- el orden no determinista;
- el overflow/underflow del cuadrado;
- la reproducibilidad entre configuraciones.

La implementación recomendada es:

$$
\boxed{
\text{diferencia compensada}
+
\text{suma de cuadrados escalada}
+
\text{Neumaier por bloque}
+
\text{árbol fijo}
+
\text{modo exacto ExBLAS para validación}
}
$$

Con esto, v911 dejaría de ser solo una mitigación local y pasaría a ser una solución robusta para dimensiones $D\ge 10^7$, tensores casi coincidentes y pipelines geométricos sensibles a los últimos bits.

<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_6][^3_7][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://arxiv.org/html/1312.3300v1

[^3_2]: https://www.nist.gov/document/nre-2015-04-iakymchukpdf

[^3_3]: https://www.nist.gov/system/files/documents/itl/ssd/is/NRE-2015-04-iakymchuk.pdf

[^3_4]: https://hal.science/hal-01456307/document

[^3_5]: https://hal.science/hal-01419813v4/document

[^3_6]: https://www.jstage.jst.go.jp/article/nolta/1/1/1_1_2/\_pdf

[^3_7]: https://hal.science/hal-01202396v3/document

[^3_8]: https://hal.science/hal-02391618v2/document

[^3_9]: https://hal.science/hal-02265534v1/document

[^3_10]: https://hal.science/hal-01419813v3/file/reprolu.pdf

[^3_11]: https://hal.science/hal-02265534v3/document

[^3_12]: https://hal.science/hal-01140280/file/tikzp.pdf

[^3_13]: http://www.diva-portal.org/smash/get/diva2:1990191/FULLTEXT01.pdf

[^3_14]: https://accurate-algorithms.readthedocs.io/en/latest/ch04summation.html

[^3_15]: https://mwiesenberger.github.io/feltor/exblas/html/namespacedg_1_1exblas.html


---

# Profundiza soluciones y mejoras sota

Para llevar v911 a un nivel realmente SOTA, hay que reformular el problema: no es solo “cambiar suma ingenua por Kahan”, sino diseñar una **distancia euclídea reproducible, escalada y resistente a pérdida de precisión en la resta**.

La recomendación final sería separar tres objetivos:

1. **Rendimiento:** reducción vectorizada y escalada.
2. **Estabilidad:** diferencia compensada, acumulación Neumaier y árbol fijo.
3. **Exactitud/reproducibilidad:** suma por expansión o superacumulador.

OpenMP no garantiza el orden de combinación de una reducción, incluso con `schedule(static)`. Por tanto, `reduction(+:x)` y una sección `critical` no son suficientes para resultados bitwise reproducibles.[^4_1][^4_2]

## 1. Definir el contrato de precisión

Antes de optimizar el kernel, conviene declarar qué significa “correcto”.

Para:

$$
\operatorname{chordal\_sq}(u,v)
=
\sum_{i=0}^{D-1}(u_i-v_i)^2
$$

hay tres contratos posibles:

### Contrato rápido

Error esperado de pocos ULPs, sin garantía bitwise entre ejecuciones.

Adecuado para:

- entrenamiento aproximado;
- inferencia;
- pipelines donde la distancia no se usa como criterio de convergencia estricto.


### Contrato estable

Error cercano a una suma pairwise o compensada, con tolerancia controlada entre hilos.

Adecuado para:

- optimización geométrica;
- cálculo de gradientes;
- iteraciones donde pequeñas diferencias pueden amplificarse.


### Contrato exacto/reproducible

Mismo resultado bit a bit para el mismo flujo de entrada, independientemente del número de hilos o del árbol paralelo.

Adecuado para:

- tests científicos;
- checkpoints reproducibles;
- comparación entre versiones;
- depuración de divergencias;
- simulaciones sensibles.

No se debe afirmar “sin deriva” sin indicar cuál de estos contratos se cumple.

## 2. Separar error de resta y error de reducción

La expresión tiene dos operaciones numéricamente distintas:

$$
\delta_i = u_i-v_i
$$

$$
S = \sum_i\delta_i^2
$$

Kahan solo mejora la segunda. Si $u_i$ y $v_i$ son casi iguales, la pérdida dominante puede ocurrir en la primera.

### Ejemplo conceptual

Si:

$$
u_i = 10^{16}+a,\qquad v_i=10^{16}+b
$$

y $a-b$ es menor que el ULP local de `float64`, ambos valores pueden almacenarse iguales. Entonces:

$$
\operatorname{fl}(u_i-v_i)=0
$$

y ningún sumador posterior puede reconstruir la diferencia real.

Por eso, si la geometría exige precisión relativa a diferencias diminutas entre coordenadas enormes, el problema debe resolverse en la **representación de los datos**, no únicamente en el acumulador.

## 3. Arquitectura de tres rutas

### Ruta `FAST`

Para entradas normales:

```text
diff = u[i] - v[i]
term = diff * diff
sum = vectorized accumulation
```

Características:

- SIMD;
- FMA opcional;
- reducción por bloques;
- sin compensación completa;
- máxima velocidad.


### Ruta `STABLE`

Para tensores cercanos o rangos amplios:

```text
diff = compensated_difference(u[i], v[i])
term = stable_square(diff)
local_sum = Neumaier(local_sum, term)
global_sum = fixed_tree(local_sums)
```

Características:

- una suma compensada por bloque;
- acumulación promovida;
- árbol fijo;
- opción de escalado.


### Ruta `EXACT`

Para validación o reproducibilidad estricta:

```text
diff = TwoDiff(u[i], v[i])
term = TwoProd(diff, diff)
accumulate_into_superaccumulator(term)
```

La familia ExBLAS utiliza transformaciones sin error y acumuladores largos para conseguir resultados reproducibles y de alta exactitud en reducciones paralelas.[^4_3][^4_4]

## 4. Diferencia compensada con `TwoDiff`

Cuando se dispone de valores representados con suficiente precisión, `TwoDiff` conserva el residuo de la resta:

```cpp
struct DD {
    double hi;
    double lo;
};

inline DD two_diff(double a, double b) {
    DD r;
    r.hi = a - b;

    double z = r.hi - a;
    r.lo = (a - (r.hi - z)) - (b + z);
    return r;
}
```

El resultado aproximado es:

$$
a-b \approx r_{\text{hi}}+r_{\text{lo}}
$$

Para un cuadrado:

$$
(r_{\text{hi}}+r_{\text{lo}})^2
=
r_{\text{hi}}^2
+2r_{\text{hi}}r_{\text{lo}}
+r_{\text{lo}}^2
$$

En una ruta de precisión alta:

```cpp
DD d = two_diff(u[i], v[i]);

double p0 = d.hi * d.hi;
double p1 = 2.0 * d.hi * d.lo;
double p2 = d.lo * d.lo;

double term = (p0 + p1) + p2;
```

Para mayor exactitud, `TwoProd` o `fma` puede conservar el residuo del producto.

Importante: `TwoDiff` no recupera información ausente de la representación de `u` y `v`. Si las coordenadas ya fueron redondeadas y quedaron idénticas, el residuo real no existe en memoria.

## 5. Mejor que Kahan: bloques + árbol fijo

La estructura recomendada para OpenMP es:

1. dividir la dimensión en bloques estáticos;
2. cada hilo procesa un bloque;
3. cada bloque devuelve un acumulador estable;
4. combinar los bloques con un árbol fijo;
5. evitar `critical`.
```cpp
struct Neumaier {
    double sum = 0.0;
    double corr = 0.0;

    void add(double x) {
        double t = sum + x;

        if (std::abs(sum) >= std::abs(x))
            corr += (sum - t) + x;
        else
            corr += (x - t) + sum;

        sum = t;
    }

    double value() const {
        return sum + corr;
    }
};
```

El esquema conceptual:

```cpp
#pragma omp parallel
{
    int tid = omp_get_thread_num();
    Neumaier local;

    #pragma omp for schedule(static)
    for (int64_t i = 0; i < D; ++i) {
        double diff = u[i] - v[i];
        local.add(diff * diff);
    }

    partial[tid] = local.value();
}

for (int stride = 1; stride < nthreads; stride *= 2) {
    for (int i = 0; i + stride < nthreads; i += 2 * stride) {
        partial[i] = stable_add(partial[i], partial[i + stride]);
    }
}

double chordal_sq = partial[^4_0];
```

El árbol debe ser explícito. OpenMP no especifica necesariamente una parentización fija para combinar reducciones, y la no asociatividad del punto flotante hace que diferentes árboles produzcan diferentes redondeos.[^4_2][^4_5]

## 6. Reducción escalada para evitar overflow

La suma compensada no evita que un término individual desborde:

```cpp
term = diff * diff;
```

Si $|diff|> \sqrt{\text{DBL\_MAX}}$, el cuadrado es infinito aunque la distancia matemática pueda representarse en una forma alternativa.

Usar una suma de cuadrados escalada:

$$
m=\max_i|\delta_i|
$$

$$
S=m^2\sum_i(\delta_i/m)^2
$$

Una forma robusta es almacenar por bloque:

```cpp
struct ScaledSumsq {
    double scale = 0.0;
    double ssq = 1.0;

    void add(double x) {
        double ax = std::abs(x);
        if (ax == 0.0) return;

        if (scale < ax) {
            double r = scale / ax;
            ssq = 1.0 + ssq * r * r;
            scale = ax;
        } else {
            double r = ax / scale;
            ssq += r * r;
        }
    }

    double log_sum_sq() const {
        if (scale == 0.0) return -INFINITY;
        return 2.0 * std::log(scale) + std::log(ssq);
    }
};
```

El resultado puede combinarse en log-space:

$$
\log(S_1+S_2)
=
\operatorname{logaddexp}(\log S_1,\log S_2)
$$

Esto protege frente a:

- overflow de `diff * diff`;
- diferencias extremas de escala;
- pérdida de términos pequeños frente a un outlier.

Para producir `chordal_sq` en `double`, se deslogaritmiza solo al final y únicamente si el resultado cabe.

## 7. Combinar acumuladores escalados

No se deben sumar directamente dos estructuras `(scale, ssq)` sin normalizarlas.

Si:

$$
S_a=a^2q_a,\qquad S_b=b^2q_b
$$

y $a\ge b$, entonces:

$$
S_a+S_b
=
a^2\left(q_a+q_b\left(\frac{b}{a}\right)^2\right)
$$

Implementación:

```cpp
void combine(ScaledSumsq& a, const ScaledSumsq& b) {
    if (b.scale == 0.0) return;

    if (a.scale == 0.0) {
        a = b;
        return;
    }

    if (a.scale >= b.scale) {
        double r = b.scale / a.scale;
        a.ssq += b.ssq * r * r;
    } else {
        double r = a.scale / b.scale;
        a.ssq = b.ssq + a.ssq * r * r;
        a.scale = b.scale;
    }
}
```

Para reproducibilidad, la combinación debe seguir siempre el mismo árbol. El resultado será estable, aunque no necesariamente correctamente redondeado como una suma exacta.

## 8. `long double` frente a double-double

Hay dos caminos para preservar precisión en $\delta_i$.

### `long double`

Ventajas:

- fácil de integrar;
- menor complejidad conceptual;
- buena mejora en plataformas x86 compatibles.

Problemas:

- tamaño y precisión dependientes de la plataforma;
- puede degradar la vectorización;
- no es necesariamente binary128;
- resultados distintos entre ABI.


### Double-double

Ventajas:

- precisión y semántica más controlables;
- puede implementarse con `TwoSum`, `TwoDiff`, `TwoProd`;
- más portable conceptualmente.

Problemas:

- más operaciones;
- mayor presión de registros;
- menor rendimiento SIMD;
- difícil de integrar en un kernel GPU sin diseño específico.

Recomendación:

- `long double` para una referencia CPU;
- double-double para modo `EXACT_APPROX`;
- double normal con escalado para producción;
- superacumulador para reproducibilidad estricta.


## 9. Usar FMA con una política definida

Para el modo estable:

```cpp
term = std::fma(diff, diff, 0.0);
```

puede reducir un redondeo. Para la acumulación:

```cpp
sum = std::fma(diff, diff, sum);
```

también puede mejorar la precisión local.

Pero FMA puede cambiar los bits respecto de una arquitectura sin FMA. Intel documenta que vectorización, reasociación y reducciones paralelas pueden cambiar el resultado aunque el código matemático parezca idéntico.[^4_1]

Por tanto, hay que elegir entre:

- `FP_FAST`: permite FMA y reasociación;
- `FP_STABLE`: permite FMA, pero usa árbol fijo;
- `FP_REPRO`: controla FMA, orden y acumulador.

El compilador debe configurarse coherentemente. Flags agresivos como `-ffast-math` pueden invalidar supuestos de compensación o reordenar expresiones.

## 10. Reproducibilidad no significa solo mismo número de hilos

Una implementación puede ser repetible con un número fijo de hilos y aun así cambiar al modificar:

- número de hilos;
- vector width;
- compilador;
- uso de FMA;
- arquitectura;
- `schedule`;
- orden de almacenamiento;
- modo de redondeo;
- FTZ/DAZ.

Por ello, el contrato debe especificar el alcance:


| Nivel | Garantía |
| :-- | :-- |
| Repetición misma configuración | Mismo resultado |
| Distinto número de hilos | Puede variar |
| Distinta arquitectura | Puede variar |
| Bitwise universal | Requiere acumulador exacto o esquema canónico |

P4016 propone precisamente definir una expresión paralela canónica, con parentización y orden especificados, permitiendo paralelizar sin cambiar el resultado abstracto.[^4_5]

## 11. Evitar una confusión: “entropía de bits”

La expresión “proteger la entropía de los últimos bits” no es técnicamente precisa. Los últimos bits no son una reserva que Kahan preserve completamente. Lo correcto sería decir:

- reduce la pérdida de precisión por absorción;
- conserva una corrección del residuo de redondeo;
- mejora el error de suma;
- no corrige la pérdida de información de la resta;
- no garantiza redondeo correcto;
- no garantiza reproducibilidad entre árboles paralelos.

Esto es importante para documentar v911 correctamente.

## 12. Diseño de API recomendado

La función debería exponer explícitamente el modo numérico:

```cpp
enum class DistanceMode {
    Fast,
    Stable,
    Reproducible,
    ExactReference
};

struct DistanceDiagnostics {
    bool saw_nan;
    bool saw_inf;
    bool overflow_avoided;
    bool underflow_detected;
    double estimated_condition;
    int threads_used;
};
```

Firma conceptual:

```cpp
double chordal_sq(
    const double* u,
    const double* v,
    int64_t D,
    DistanceMode mode,
    DistanceDiagnostics* diagnostics);
```

Esto evita esconder el coste y las garantías dentro del kernel.

## 13. Diagnóstico de condicionamiento

Conviene medir la relación:

$$
\kappa
=
\frac{\|u\|+\|v\|}
{\|u-v\|}
$$

Si $\kappa$ es muy grande, la resta es mal condicionada en representación de precisión finita.

En log-space:

$$
\log\kappa
=
\log(\|u\|+\|v\|)-\log\|u-v\|
$$

Si $\log\kappa$ supera un umbral, activar automáticamente la ruta estable o emitir un diagnóstico.

Esto permite una política híbrida:

```text
si magnitudes normales y κ bajo:
    FAST
si κ alto:
    STABLE
si se requiere bitwise:
    REPRODUCIBLE
```

El umbral debe calibrarse empíricamente con el dtype y el uso geométrico.

## 14. Testing de alto nivel

### Referencia

Usar:

- `long double`;
- MPFR;
- acumulador exacto;
- una implementación serial de alta precisión.


### Casos de prueba

1. $u=v$: resultado exactamente cero.
2. Un solo componente no nulo.
3. Componentes idénticos repetidos.
4. Escala global $2^k$.
5. Valores alrededor de cada ULP.
6. Coordenadas grandes con diferencias pequeñas.
7. Rangos mixtos de exponentes.
8. `NaN`, `Inf`, subnormales.
9. $D=10^7$ y superiores.
10. diferente cantidad de hilos.

### Métricas

- error absoluto;
- error relativo;
- ULPs;
- desviación frente a referencia;
- variación entre hilos;
- tiempo;
- ancho de banda;
- energía;
- estabilidad de gradientes posteriores.


### Propiedades geométricas

- simetría;
- no negatividad;
- identidad de indiscernibles dentro de la resolución disponible;
- invariancia ante permutación;
- continuidad;
- estabilidad de la geodésica resultante.


## 15. Estrategia de despliegue

### Fase 1

Implementar:

- parciales por hilo;
- `schedule(static)`;
- árbol fijo;
- Neumaier;
- instrumentación.


### Fase 2

Añadir:

- suma escalada;
- combinación estable de `(scale, ssq)`;
- FMA controlado;
- selección automática por rango.


### Fase 3

Añadir:

- `TwoDiff`;
- referencia double-double;
- modo reproducible;
- comparación con superacumulador.


### Fase 4

Validar en CI:

- GCC;
- Clang;
- Intel;
- AVX2;
- AVX-512;
- ARM NEON/SVE;
- configuraciones con y sin FMA;
- uno y múltiples hilos.


## Veredicto final

La versión v911 con Kahan por hilo es un **buen primer nivel**, pero no es todavía la solución SOTA completa. La mejora decisiva es pasar de:

$$
\text{Kahan local}+\text{critical}
$$

a:

$$
\boxed{
\text{resta compensada}
+
\text{norma escalada}
+
\text{Neumaier por bloque}
+
\text{árbol canónico}
+
\text{modo exacto opcional}
}
$$

La ruta recomendada para producción sería:

```text
FAST:
    diff normal
    FMA
    reducción por bloques

STABLE:
    TwoDiff o acumulación promovida
    suma de cuadrados escalada
    Neumaier
    árbol fijo

REPRO:
    expansión/superacumulador
    orden canónico
    resultado correctamente redondeado
```

Así se cubren por separado rendimiento, estabilidad y reproducibilidad, sin imponer el coste de un superacumulador a todos los casos.

<span style="display:none">[^4_10][^4_11][^4_12][^4_13][^4_14][^4_15][^4_16][^4_17][^4_6][^4_7][^4_8][^4_9]</span>

<div align="center">⁂</div>

[^4_1]: https://www.intel.com/content/dam/develop/external/us/en/documents/pdf/fp-consistency-121918.pdf

[^4_2]: https://arxiv.org/html/2408.05148v3

[^4_3]: https://www.nist.gov/document/nre-2015-04-iakymchukpdf

[^4_4]: https://www.nist.gov/system/files/documents/itl/ssd/is/NRE-2015-04-iakymchuk.pdf

[^4_5]: https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2026/p4016r0.pdf

[^4_6]: https://www.intel.com/content/www/us/en/docs/advisor/user-guide/2023-0/openmp-reduction-operations.html

[^4_7]: https://www.intel.com/content/www/us/en/docs/advisor/user-guide/2024-1/openmp-reduction-operations.html

[^4_8]: https://www.sciencedirect.com/science/article/pii/S0167819115001155

[^4_9]: https://www.jstage.jst.go.jp/article/tjsst/7/4/7_109/\_pdf/-char/ja

[^4_10]: https://www.openmp.org/spec-html/5.0/openmpsu107.html

[^4_11]: https://www.sintef.no/globalassets/project/evitameeting/2013/advanced_topics_in_reproducible_science.pdf

[^4_12]: https://theses.hal.science/tel-02025855v1/file/These Finale.pdf

[^4_13]: https://digitalcommons.csbsju.edu/cgi/viewcontent.cgi?article=1028\&context=honors_theses

[^4_14]: https://www.tuhh.de/ti3/paper/rump/Ru23.pdf

[^4_15]: https://hal-lirmm.ccsd.cnrs.fr/lirmm-01206348v1/document

[^4_16]: https://stackoverflow.com/questions/67444249/can-i-deterministically-sum-a-vector-of-arbitrarily-arranged-floating-point-numb/67444250

[^4_17]: https://stackoverflow.com/questions/75211606/openmp-reproducible-reduction


---

# profundiza en nivel 3: solucion cientifica sota

El **nivel 3 científico SOTA** debe tratar `chordal_sq` como un **dot product exacto de diferencias**, no como una suma con Kahan:

$$
S=\sum_{i=0}^{D-1}(u_i-v_i)^2
$$

La solución de referencia es una combinación de:

$$
\boxed{
\texttt{TwoDiff}
\rightarrow
\texttt{TwoProd}
\rightarrow
\text{floating-point expansion}
\rightarrow
\text{superacumulador Kulisch}
\rightarrow
\text{redondeo correcto}
}
$$

Esto puede producir el resultado correctamente redondeado de la suma exacta y hacerlo independiente del orden paralelo. ExBLAS sigue precisamente esta arquitectura para reducciones y dot products reproducibles.[^5_1][^5_2]

## 1. Qué garantiza realmente el nivel 3

Hay que distinguir cuatro objetivos:


| Objetivo | Kahan | FPE | Superacumulador |
| :-- | --: | --: | --: |
| Reducir error medio | Sí | Sí | Sí |
| Manejar rango dinámico extremo | Limitado | Parcial | Sí |
| Independencia del árbol paralelo | No | Sí, con diseño fijo | Sí |
| Redondeo correcto del resultado exacto | No | No siempre | Sí |
| Bitwise reproducible | No | Sí, bajo condiciones | Sí |

Un superacumulador no “hace exacta” la resta original si `u` y `v` ya perdieron información al almacenarse. Lo que sí hace es preservar exactamente la suma de los productos correspondientes a los valores representados:

$$
S_{\text{almacenado}}
=
\sum_i \operatorname{fl}(u_i-v_i)^2
$$

Si también se conserva el residuo de la resta mediante `TwoDiff`, la aproximación puede extenderse a:

$$
S_{\text{dd}}
=
\sum_i(d_{i,\mathrm{hi}}+d_{i,\mathrm{lo}})^2
$$

## 2. Primera capa: `TwoDiff`

Para cada coordenada:

```cpp
struct DiffExpansion {
    double hi;
    double lo;
};

inline DiffExpansion two_diff(double a, double b) {
    double hi = a - b;
    double z  = hi - a;
    double lo = (a - (hi - z)) - (b + z);
    return {hi, lo};
}
```

Bajo las condiciones habituales de IEEE-754 y redondeo al más cercano:

$$
a-b = \mathrm{hi}+\mathrm{lo}
$$

exactamente como expansión de dos términos, siempre que no haya overflow, underflow patológico o excepciones de rango.

### Por qué importa

La resta ordinaria conserva solamente el resultado redondeado:

```cpp
hi = a - b;
```

`TwoDiff` conserva también el error de redondeo:

```cpp
lo = exact(a - b) - hi;
```

Así, la distancia no parte inmediatamente de una diferencia truncada.

### Límite fundamental

Si `a` y `b` ya fueron redondeados al mismo número, `TwoDiff` no puede reconstruir la diferencia física original. Para resolver eso hay que almacenar las coordenadas como:

```text
a = a_hi + a_lo
b = b_hi + b_lo
```

o utilizar una representación exacta/fija desde la ingestión.

## 3. Segunda capa: expansión del cuadrado

Sea:

$$
d=d_h+d_l
$$

Entonces:

$$
d^2=d_h^2+2d_hd_l+d_l^2
$$

No conviene formar primero `d_hi + d_lo` en un único `double`, porque volvería a redondear.

Una versión básica:

```cpp
struct SquareExpansion {
    double p0;
    double p1;
    double p2;
};

inline SquareExpansion square_expansion(double hi, double lo) {
    return {
        hi * hi,
        2.0 * hi * lo,
        lo * lo
    };
}
```

Una versión más fuerte usa `TwoProd`:

```cpp
struct ProductExpansion {
    double hi;
    double lo;
};

inline ProductExpansion two_prod(double a, double b) {
    double hi = a * b;
    double lo = std::fma(a, b, -hi);
    return {hi, lo};
}
```

Entonces:

```cpp
auto p = two_prod(d.hi, d.hi);
double cross = 2.0 * d.hi * d.lo;
double tail  = d.lo * d.lo;
```

La expansión del término queda aproximadamente:

$$
d^2 =
p_{\mathrm{hi}}
+
p_{\mathrm{lo}}
+
2d_hd_l
+
d_l^2
$$

Cada componente debe introducirse en el acumulador exacto, no sumarse ingenuamente en un `double`.

## 4. Tercera capa: floating-point expansion

Una FPE representa un número como:

$$
x \approx x_0+x_1+\cdots+x_{p-1}
$$

con componentes ordenados por magnitud y mínima superposición.

Para añadir un término:

```cpp
inline void two_sum(double a, double b,
                    double& s, double& e) {
    s = a + b;
    double z = s - a;
    e = (a - (s - z)) + (b - z);
}
```

Acumulador conceptual:

```cpp
template <int P>
struct Expansion {
    double x[P] = {};

    void add(double value) {
        double q = value;

        for (int i = 0; i < P; ++i) {
            double s, e;
            two_sum(x[i], q, s, e);
            x[i] = s;
            q = e;

            if (q == 0.0) break;
        }

        if (q != 0.0) {
            overflow_to_superaccumulator(q);
        }
    }
};
```

Para binary64, una FPE8 puede representar aproximadamente $8\times53$ bits de significando en condiciones favorables; trabajos basados en ExBLAS la usan como alternativa más ligera al superacumulador completo.[^5_1]

### FPE8 no es una garantía universal

La expansión fija puede quedarse corta si:

- el rango dinámico es enorme;
- hay muchas magnitudes distintas;
- se acumulan demasiados términos;
- la condición numérica es extrema.

Por eso el residuo que no cabe debe ir a un superacumulador. Sin ese fallback, FPE8 es solo una aproximación de precisión extendida.

## 5. Cuarta capa: superacumulador Kulisch

Un superacumulador transforma cada término binario en un entero alineado con su exponente y acumula todos los bits sin redondear.

Para binary64, la suma de productos requiere un rango fijo suficientemente amplio para cubrir:

- exponentes mínimos y máximos;
- bits fraccionarios;
- producto de dos significandos;
- cantidad de términos;
- signo y carries.

La arquitectura clásica utiliza un acumulador largo, frecuentemente representado como palabras enteras con carry-save. El trabajo de reproducibilidad paralela describe un acumulador de aproximadamente 2098 bits para sumas de binary64 y acumuladores más amplios para productos completos.[^5_2]

### Idea matemática

Cada producto finito se descompone como:

$$
p_i = s_i M_i 2^{e_i}
$$

donde $M_i$ es un entero de significando. El superacumulador almacena:

$$
A=\sum_i s_iM_i2^{e_i-k}
$$

como un entero grande, sin redondear cada suma.

Al final:

1. normaliza carries;
2. localiza el bit más significativo;
3. obtiene bits de guarda y sticky;
4. redondea a binary64;
5. devuelve un único resultado canónico.

El redondeo final es el único punto donde se pierde información.

## 6. Arquitectura paralela exacta

La implementación no debe compartir un único superacumulador con un atomic por elemento. Eso sería demasiado costoso y no escalaría.

La jerarquía recomendada es:

### Nivel 1: registros SIMD

Cada lane mantiene una FPE pequeña:

```text
vector<Expansion<P>>
```

Se procesan varios elementos por instrucción.

### Nivel 2: superacumulador privado

Cuando la FPE no puede absorber el residuo, se deposita en un superacumulador local al hilo o al bloque.

### Nivel 3: combinación por grupo

Los superacumuladores de varios hilos se combinan mediante suma de palabras enteras, no mediante punto flotante.

### Nivel 4: acumulador global

Se combinan los acumuladores de los grupos mediante un árbol fijo o una operación asociativa sobre la representación entera.

### Nivel 5: redondeo

Solo el acumulador final se convierte a `double`.

Esquema:

```text
datos
  ↓
TwoDiff
  ↓
TwoProd / square expansion
  ↓
FPE por lane
  ↓
superaccumulator por hilo
  ↓
superaccumulator por bloque
  ↓
superaccumulator global
  ↓
round-to-nearest-even
  ↓
chordal_sq
```

ExBLAS utiliza una estrategia multinivel de este tipo: expansiones rápidas para filtrar la mayoría de términos y superacumuladores para conservar los residuos restantes.[^5_2]

## 7. Pseudocódigo científico

```cpp
struct ExactDistance {
    bool nan = false;
    bool pos_inf = false;
    SuperAccumulator acc;
};

ExactDistance chordal_sq_exact(
    const double* u,
    const double* v,
    int64_t n)
{
    ExactDistance out;

    #pragma omp parallel
    {
        Expansion<8> fpe;
        SuperAccumulator local_acc;

        #pragma omp for schedule(static)
        for (int64_t i = 0; i < n; ++i) {
            double a = u[i];
            double b = v[i];

            if (std::isnan(a) || std::isnan(b)) {
                out.nan = true;
                continue;
            }

            if (std::isinf(a) || std::isinf(b)) {
                out.pos_inf = true;
                continue;
            }

            auto d = two_diff(a, b);

            auto p = two_prod(d.hi, d.hi);
            fpe.add(p.hi);
            fpe.add(p.lo);

            fpe.add(2.0 * d.hi * d.lo);
            fpe.add(d.lo * d.lo);

            fpe.flush_to(local_acc);
        }

        local_acc.add_expansion(fpe);

        #pragma omp critical
        {
            out.acc.merge(local_acc);
        }
    }

    if (out.nan) return nan_result();
    if (out.pos_inf) return inf_result();

    return {false, false, out.acc.round_to_double()};
}
```

Este pseudocódigo aún no es una implementación de producción porque:

- `out.nan` y `out.pos_inf` tienen carreras;
- `critical` no es el diseño óptimo;
- falta especificar el ancho del acumulador;
- falta la normalización de carries;
- el cross-term necesita tratamiento exacto;
- la combinación debe hacerse mediante arreglo de acumuladores y árbol fijo.

Una forma correcta de eliminar la carrera sería usar flags por hilo:

```cpp
std::vector<uint8_t> thread_nan(nthreads);
std::vector<uint8_t> thread_inf(nthreads);
std::vector<SuperAccumulator> partial(nthreads);
```

y combinar después de la barrera.

## 8. Cómo tratar exactamente el cuadrado de `TwoDiff`

Si:

$$
d=d_h+d_l
$$

el cuadrado exacto es:

$$
d^2=d_h^2+2d_hd_l+d_l^2
$$

Para no perder los bits del primer producto:

```cpp
auto [p_hi, p_lo] = two_prod(d_hi, d_hi);
```

Después se acumulan cuatro piezas:

```text
p_hi
p_lo
2 * d_hi * d_lo
d_lo * d_lo
```

El término `2*d_hi*d_lo` también puede requerir `TwoProd` si `d_lo` no es insignificante. Una implementación rigurosa puede usar:

```cpp
auto cross = two_prod(d_hi, d_lo);
accumulate(2 * cross.hi);
accumulate(2 * cross.lo);
```

y después:

```cpp
auto tail = two_prod(d_lo, d_lo);
accumulate(tail.hi);
accumulate(tail.lo);
```

En la práctica, `d_lo` suele ser mucho menor que `d_hi`, pero el objetivo del nivel 3 es no depender de esa suposición.

## 9. ¿Qué significa “exacto” aquí?

Hay tres niveles de exactitud posibles:

### Exacto respecto a la diferencia redondeada

$$
d_i=\operatorname{fl}(u_i-v_i)
$$

Luego se suma exactamente:

$$
\sum_i d_i^2
$$

### Exacto respecto a la expansión de la resta

$$
d_i=d_{hi}+d_{lo}
$$

Luego se suma exactamente el cuadrado de esa expansión.

### Exacto respecto a los valores físicos originales

Esto solo es posible si los valores originales se almacenaron con suficiente precisión, por ejemplo:

- double-double;
- binary128;
- enteros escalados;
- coordenadas exactas;
- intervalos o representaciones afines.

No se puede obtener retrospectivamente desde dos `double` idénticos.

## 10. Superacumulador y overflow

La ventaja clave frente a `double` es que el acumulador intermedio no desborda aunque el resultado final sea grande, siempre que el ancho haya sido diseñado para el número máximo de términos.

Para `D` finito y binary64, el ancho debe considerar:

$$
W \ge W_{\text{producto}}+\lceil\log_2 D\rceil+\text{margen}
$$

Si se permite `D` arbitrariamente grande, un acumulador fijo puede desbordar. La API debe imponer:

- máximo `D`;
- saturación detectada;
- acumulador dinámico;
- o una ruta logarítmica separada.

No se debe confundir “no redondea” con “no puede desbordar”. Un superacumulador también necesita un contrato de rango.

## 11. Política para `NaN`, `Inf` y ceros

### `NaN`

La suma matemática no está definida:

```text
si hay NaN → resultado NaN
```

El flag debe acumularse con OR lógico por hilo y combinarse determinísticamente.

### `Inf`

Si una diferencia es infinita:

$$
(u_i-v_i)^2=+\infty
$$

pero `Inf - Inf` produce `NaN`. La política recomendada:

- `Inf - finite` → `+Inf`;
- `finite - Inf` → `-Inf`, cuadrado `+Inf`;
- `Inf - Inf` → `NaN`;
- cualquier `NaN` → `NaN`.


### Cero

Si `u_i == v_i`, el término exacto es cero. Puede saltarse para reducir trabajo, pero sin alterar flags.

## 12. Reproducibilidad distribuida

Si `chordal_sq` se calcula entre múltiples nodos:

```text
nodo → MPI rank → global reduction
```

un `MPI_Allreduce` convencional sobre `double` no garantiza resultado bitwise idéntico entre árboles de comunicación.

La solución científica es reducir **superacumuladores**, no `double`:

1. cada rank produce un superacumulador;
2. se combinan las palabras enteras;
3. se normaliza al final;
4. se redondea solo en el rank final.

Alternativas:

- `MPI_Op` personalizado sobre el acumulador;
- gather de acumuladores y árbol explícito;
- reducción jerárquica canónica;
- serialización de palabras del acumulador.

La reducción de superacumuladores es asociativa en su representación entera, por lo que el árbol puede cambiar sin alterar el resultado matemático, siempre que no haya overflow interno.

## 13. FPE8 frente a superacumulador completo

Una solución muy práctica es ofrecer dos modos científicos:

### `REPRO_FPE8`

- dos `TwoProd`;
- expansión de 8 términos;
- early exit cuando el residuo es cero;
- superacumulador solo para residuos;
- más rápido;
- exactitud garantizada solo dentro de los límites de la expansión.


### `REPRO_EXACT`

- superacumulador para todos los residuos;
- resultado correctamente redondeado;
- rango completo;
- mayor memoria y coste.

El trabajo sobre ExBLAS señala precisamente esta diferencia: FPE es una alternativa ligera y configurable, mientras que el superacumulador se reserva para rangos y condicionamientos extremos.[^5_1]

## 14. Presupuesto de rendimiento

Para $D\ge10^7$, el kernel suele ser memory-bound. Eso cambia la decisión:

- `TwoDiff` añade operaciones, pero casi no añade lecturas;
- FPE consume registros y puede reducir occupancy;
- superacumulador añade accesos indirectos;
- la memoria de entrada domina si los datos no caben en caché.

La estrategia recomendada es:

```text
primera pasada:
    detectar rango, NaN, Inf y condicionamiento

si benigno:
    ruta FAST/STABLE

si extremo o modo exacto:
    ruta FPE + superaccumulator
```

Sin embargo, una primera pasada adicional puede costar demasiado. Mejor alternativa:

- usar un bloque pequeño como sonda;
- activar fallback solo si se detectan rangos críticos;
- o seleccionar el modo por metadatos del tensor.


## 15. Condicionamiento y selección automática

Definir una estimación:

$$
\kappa_i\approx
\frac{|u_i|+|v_i|}
{|u_i-v_i|}
$$

y conservar el máximo o percentil alto de $\log_2\kappa_i$.

Política orientativa:

```text
si max_log_condition < 30:
    FAST/STABLE
si 30 <= max_log_condition < 100:
    FPE8
si max_log_condition >= 100:
    exact superaccumulator
```

Estos umbrales no deben fijarse universalmente; dependen de:

- dtype;
- tolerancia geométrica;
- número de iteraciones;
- si la distancia alimenta un gradiente;
- sensibilidad de la geodésica.

La política debe calibrarse con pruebas de backward error, no solo con error de `chordal_sq`.

## 16. Validación científica

### Referencia de precisión

Usar MPFR o un acumulador entero exacto para generar:

$$
S_{\text{ref}}
$$

Para binary64, una precisión de al menos unos 2100 bits es apropiada para verificar sumas de productos de amplio rango; el trabajo de superacumulación usa este orden de magnitud como referencia para garantizar exactitud bitwise.[^5_2]

### Propiedades

Verificar:

$$
S(u,v)=S(v,u)
$$

$$
S(u,u)=0
$$

$$
S\ge0
$$

$$
S(cu,cv)=c^2S(u,v)
$$

cuando el resultado sea representable y no intervengan redondeos de entrada.

### Pruebas adversarias

- pares casi idénticos;
- signos alternantes en las diferencias;
- aunque el cuadrado sea positivo, `TwoDiff` puede producir residuos con signo;
- exponentes desde subnormales hasta máximos;
- un término dominante y millones de términos pequeños;
- $D=10^7,10^8$;
- valores `Inf`, `NaN`;
- distintas arquitecturas;
- 1, 2, 4, 8, 16, 32 hilos;
- diferentes órdenes de partición.


### Métricas

No limitarse a comparar `double` final. Medir:

- correcto redondeo;
- ULP frente a referencia;
- identidad bitwise;
- error en $\sqrt{S}$;
- error en la geodésica posterior;
- error del gradiente;
- variación de iteraciones del optimizador.


## 17. Gradiente de la distancia

Si:

$$
d(u,v)=\sqrt{S}
$$

entonces:

$$
\frac{\partial d}{\partial u_i}
=
\frac{u_i-v_i}{d}
$$

cuando $d>0$.

Para $d\approx0$, esta derivada es singular o mal condicionada. Un `chordal_sq` exacto no resuelve por sí solo el problema del gradiente:

- hay que definir subgradiente;
- usar regularización;
- tratar el caso $d<\tau$;
- evitar división directa por una distancia subnormal.

Una forma estable:

$$
d_\varepsilon=\sqrt{S+\varepsilon^2}
$$

$$
\frac{\partial d_\varepsilon}{\partial u_i}
=
\frac{u_i-v_i}{d_\varepsilon}
$$

Pero esto cambia la geometría. Debe ser una decisión explícita del modelo, no un parche oculto.

## 18. Diseño de modos final

Recomendaría esta API:

```cpp
enum class AccuracyMode {
    Fast,
    Stable,
    ReproducibleFPE,
    ExactSuperaccumulator
};

struct DistanceResult {
    double value;
    bool nan;
    bool inf;
    bool exact_rounded;
    uint64_t ulp_error_bound;
};
```

Semántica:


| Modo | Garantía |
| :-- | :-- |
| `Fast` | rápido, no reproducible |
| `Stable` | error reducido, árbol estable |
| `ReproducibleFPE` | reproducible dentro del contrato de rango |
| `ExactSuperaccumulator` | suma correctamente redondeada para el dominio soportado |

`ulp_error_bound` debe ser una cota documentada, no una estimación informal.

## 19. Plan de implementación

### Etapa A: referencia

Implementar una versión serial:

- `TwoDiff`;
- `TwoProd`;
- FPE;
- superacumulador;
- redondeo correcto.

Usarla como oráculo, aunque sea lenta.

### Etapa B: versión OpenMP

- un acumulador por hilo;
- sin `critical` por elemento;
- flags por hilo;
- merge de superacumuladores;
- árbol entero.


### Etapa C: SIMD

- FPE por lane;
- `TwoProd` con FMA;
- early exit;
- alineación y layout controlados;
- benchmark contra ruta normal.


### Etapa D: distribuida

- superacumulador serializable;
- reducción MPI de palabras;
- pruebas entre número de ranks;
- comparación bitwise.


### Etapa E: integración geométrica

- propagar la garantía a $\sqrt{S}$;
- log map;
- exp map;
- gradientes;
- criterio de convergencia.


## Veredicto

La solución científica SOTA para v911 no es “Kahan más grande”. Es un pipeline exacto:

$$
\boxed{
\text{representación precisa}
\rightarrow
\texttt{TwoDiff}
\rightarrow
\texttt{TwoProd}
\rightarrow
\text{FPE}
\rightarrow
\text{superacumulador}
\rightarrow
\text{redondeo correcto}
}
$$

La recomendación concreta es implementar dos rutas avanzadas:

1. **FPE8 + fallback a superacumulador**, como ruta reproducible eficiente.
2. **Superacumulador directo**, como referencia exacta y modo científico.

El superacumulador preserva toda la información de la reducción y permite un resultado correctamente redondeado, determinista y reproducible incluso con distintos árboles paralelos. Pero hay que documentar el límite fundamental: ninguna técnica posterior puede recuperar precisión que ya se perdió al almacenar `u` y `v` en `float64`.[^5_3][^5_2]

<span style="display:none">[^5_10][^5_11][^5_12][^5_13][^5_14][^5_15][^5_4][^5_5][^5_6][^5_7][^5_8][^5_9]</span>

<div align="center">⁂</div>

[^5_1]: https://arxiv.org/html/2005.07282v1

[^5_2]: https://hal.science/hal-00949355v3/file/superaccumulator.pdf

[^5_3]: https://backend.orbit.dtu.dk/ws/portalfiles/portal/254095184/JCAM_R3_Reproducible_PCG_12.pdf

[^5_4]: https://backend.orbit.dtu.dk/ws/portalfiles/portal/176480912/Wiesenberger2019Reproducibility.pdf

[^5_5]: https://riunet.upv.es/bitstreams/ba8c4695-0576-4fda-a415-18b9c2adc1e2/download

[^5_6]: https://riunet.upv.es/bitstreams/275bedd3-1c58-4020-b73e-fbe7ac85cb30/download

[^5_7]: https://hal.science/hal-01419813/document

[^5_8]: https://www.diva-portal.org/smash/get/diva2:1990191/FULLTEXT01.pdf

[^5_9]: https://github.com/riakymch/exblas

[^5_10]: https://www.nist.gov/system/files/documents/itl/ssd/is/NRE-2015-04-iakymchuk.pdf

[^5_11]: https://hal.science/hal-01202396v3/document

[^5_12]: https://hal.science/hal-01419813v3/file/reprolu.pdf

[^5_13]: https://hal.science/hal-01419813v4/document

[^5_14]: https://theses.hal.science/tel-02025855v1/file/These Finale.pdf

[^5_15]: https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2026/p4016r0.pdf


---

# 3. Inestabilidad Asintótica Antipodal (Bug Teórico / Geométrico)evalua soluciones y mejoras sota

Falla: En el cálculo de ángulo, cuando el producto punto caía por debajo de −0.9999-0.9999−0.9999 (vectores antiparalelos), el kernel invocaba std::acos(dot). La derivada de acos tiende a infinito al aproximarse a -1, amplificando violentamente el error de cuantización preexistente.
Estado (v911): Parche matemático. Ante paralelismo reverso se computa un sumatorio dual chordanti2=∑(ui+vi)2chord\_{anti}^2 = \\sum (u_i + v_i)^2chordanti2​=∑(ui​+vi​)2, infiriendo la distancia usando π−2arcsin⁡(chordanti/2)\\pi - 2\\arcsin(chord\_{anti} / 2)π−2arcsin(chordanti​/2). Continuidad topológica restaurada sin saltos bruscos.

El parche v911 es **matemáticamente razonable como estabilización del ángulo**, pero no elimina la singularidad geométrica antipodal. La mejora con

$$
c_{\text{anti}}^2=\sum_i(u_i+v_i)^2
$$

y

$$
\theta=\pi-2\arcsin\left(\frac{c_{\text{anti}}}{2}\right)
$$

evita evaluar directamente `acos(dot)` cerca de $-1$, pero todavía requiere una política explícita para la **dirección de la geodésica**, porque entre puntos antipodales hay infinitos grandes círculos y el logaritmo riemanniano no es único. La exponencial inversa en la esfera tiene precisamente esa singularidad en el antipodal.[^6_1][^6_2]

## 1. Evaluación matemática de v911

Para vectores unitarios $u,v$:

$$
\theta=\arccos(u^\top v)
$$

y:

$$
\|u+v\|=2\cos\frac{\theta}{2}
$$

Por tanto:

$$
\theta=2\arccos\left(\frac{\|u+v\|}{2}\right)
$$

o, equivalentemente:

$$
\theta=\pi-2\arcsin\left(\frac{\|u+v\|}{2}\right)
$$

La segunda forma es adecuada cuando $\theta\approx\pi$, porque $\|u+v\|$ es pequeño y `asin` opera cerca de cero, no cerca de un extremo. Esto elimina la amplificación directa de `acos` en $c\approx-1$.

La identidad es correcta para vectores unitarios. Si $u$ y $v$ no están exactamente normalizados, hay que normalizarlos o calcular:

$$
c=\frac{u^\top v}{\|u\|\|v\|}
$$

y usar distancias chordales normalizadas:

$$
h_{\text{anti}}
=
\frac12
\left\|
\frac{u}{\|u\|}
+
\frac{v}{\|v\|}
\right\|
$$

La implementación no debe asumir que la matriz topológica ya es perfectamente unitaria.

## 2. La mejor fórmula general: `atan2`

Para el ángulo completo $[0,\pi]$, la formulación más robusta es:

$$
\theta=
\operatorname{atan2}
\left(
\sqrt{1-c^2},
c
\right)
$$

si $u$ y $v$ son unitarios.

En el caso tridimensional:

$$
\theta=
\operatorname{atan2}
\left(
\|u\times v\|,
u^\top v
\right)
$$

La ventaja es que `atan2` conserva simultáneamente la información de seno y coseno y no necesita invertir una función casi plana en los extremos. La formulación con `atan2` se recomienda como alternativa estable a `acos` para vectores casi paralelos o antiparalelos.[^6_3][^6_4]

Para dimensión general, no hace falta construir un producto cruzado:

$$
s^2=
\|u\|^2\|v\|^2-(u^\top v)^2
$$

Después:

$$
\theta=\operatorname{atan2}(\sqrt{\max(0,s^2)},u^\top v)
$$

Pero calcular $s^2$ como diferencia de dos cantidades cercanas puede sufrir cancelación cuando los vectores son casi paralelos. Por eso conviene obtener el seno mediante una cuerda estable.

## 3. Fórmula híbrida superior

Para vectores unitarios, usar:

$$
h_-=\frac12\|u-v\|
$$

$$
h_+=\frac12\|u+v\|
$$

Entonces:

$$
\sin\frac{\theta}{2}=h_-
$$

$$
\cos\frac{\theta}{2}=h_+
$$

y:

$$
\boxed{
\theta=2\operatorname{atan2}(h_-,h_+)
}
$$

Esta es una de las mejores formulaciones globales:

- cerca de $\theta=0$, $h_-$ es pequeño y $h_+\approx1$;
- cerca de $\theta=\pi$, $h_-\approx1$ y $h_+$ es pequeño;
- no depende de `acos`;
- evita decidir artificialmente entre una fórmula paralela y antiparalela;
- usa ambas cuerdas para conservar información geométrica.

Para entradas no normalizadas:

$$
a=\frac{u}{\|u\|},\qquad b=\frac{v}{\|v\|}
$$

$$
\theta=
2\operatorname{atan2}
\left(
\frac12\|a-b\|,
\frac12\|a+b\|
\right)
$$

La operación crítica pasa a ser el cálculo estable de $\|a-b\|$ y $\|a+b\|$, que puede reutilizar la solución científica del problema anterior: diferencia compensada, suma escalada y reducción exacta opcional.

## 4. Implementación recomendada

```cpp
struct AngleResult {
    double theta;
    bool invalid;
    bool antipodal;
    bool zero_norm;
};

AngleResult stable_angle(
    const double* u,
    const double* v,
    int64_t n,
    double eps)
{
    ScaledSumsq minus_norm;
    ScaledSumsq plus_norm;

    double uu = stable_norm_sq(u, n);
    double vv = stable_norm_sq(v, n);

    if (!(uu > eps) || !(vv > eps)) {
        return {NAN, true, false, true};
    }

    double inv_u = 1.0 / std::sqrt(uu);
    double inv_v = 1.0 / std::sqrt(vv);

    for (int64_t i = 0; i < n; ++i) {
        double a = u[i] * inv_u;
        double b = v[i] * inv_v;

        minus_norm.add(a - b);
        plus_norm.add(a + b);
    }

    double hm = 0.5 * minus_norm.norm();
    double hp = 0.5 * plus_norm.norm();

    double theta = 2.0 * std::atan2(hm, hp);

    bool anti = hp <= antipodal_threshold;

    return {theta, false, anti, false};
}
```

Para evitar que `hm` o `hp` se salgan ligeramente de $[0,1]$:

```cpp
hm = std::clamp(hm, 0.0, 1.0);
hp = std::clamp(hp, 0.0, 1.0);
```

El `clamp` aquí es una protección de representación, no la solución numérica principal.

## 5. La singularidad geométrica no desaparece

Para $v=-u$, el ángulo es perfectamente definido:

$$
d(u,v)=\pi
$$

pero el vector tangente de la geodésica no lo es. En la esfera:

$$
\operatorname{Log}_u(v)
=
\frac{\theta}{\sin\theta}
\left(v-\cos\theta\,u\right)
$$

Cuando $\theta\to\pi$:

- $\sin\theta\to0$;
- $v-\cos\theta\,u\to0$;
- la dirección depende de la perturbación;
- en $\theta=\pi$, no existe una única dirección.

Esto no es un bug de punto flotante. Es el cut locus geométrico del punto $u$.[^6_5][^6_1]

Por tanto:

> v911 puede estabilizar el valor escalar de la distancia, pero no puede crear una dirección geodésica única donde la geometría no la define.

## 6. Política necesaria para el vector logarítmico

La implementación debe distinguir tres casos.

### Caso A: normal

Si:

$$
\|u+v\|>\tau_{\text{anti}}
$$

usar:

$$
w=v-(u^\top v)u
$$

$$
\operatorname{Log}_u(v)
=
\frac{\theta}{\|w\|}w
$$

### Caso B: casi antipodal

Si:

$$
\|u+v\|\le\tau_{\text{anti}}
$$

no dividir directamente por $\|w\|$. Elegir una dirección tangente estable $q$ tal que:

$$
q^\top u=0,\qquad\|q\|=1
$$

y definir:

$$
\operatorname{Log}_u(v)\approx \theta q
$$

La elección de $q$ debe ser determinista y documentada.

### Caso C: exactamente antipodal

Si $v=-u$ dentro de la tolerancia:

- devolver una dirección canónica;
- devolver un subgradiente;
- usar un vector de referencia externo;
- introducir una perturbación determinista;
- o marcar el logaritmo como multivaluado.

La peor opción es seleccionar una dirección basada en una comparación frágil que cambie con el orden de reducción.

## 7. Selección determinista de dirección antipodal

Dado $u$, elegir el eje coordenado menos alineado con él:

$$
j=\arg\min_k |u_k|
$$

Sea $e_j$ ese eje. Proyectarlo al espacio tangente:

$$
q_0=e_j-(e_j^\top u)u
$$

Normalizar:

$$
q=\frac{q_0}{\|q_0\|}
$$

Pseudocódigo:

```cpp
Vector canonical_tangent(Vector u) {
    int j = argmin_abs_component(u);

    Vector e = basis_vector(j);
    Vector q = e - dot(e, u) * u;

    return q / stable_norm(q);
}
```

Esto es mucho más estable que elegir siempre `e_0`, porque si $u$ está cerca del primer eje, la proyección queda casi nula.

Para resolver el signo, pueden adoptarse políticas:

- signo positivo respecto al primer componente no nulo;
- continuidad temporal respecto a la dirección anterior;
- dirección proporcionada por el optimizador;
- orientación externa del problema.

No existe un signo matemáticamente privilegiado en el antipodal exacto.

## 8. Umbral antipodal: no usar `-0.9999` fijo

El umbral `dot < -0.9999` es demasiado arbitrario. Debe depender de:

- precisión del dtype;
- error acumulado del producto punto;
- dimensión $D$;
- condición de la normalización;
- tolerancia requerida para la dirección;
- si el cálculo es forward o backward.

En vez de umbral sobre `dot`, es mejor usar la cuerda:

$$
h_+=\frac12\|a+b\|
$$

porque es justamente la cantidad que mide la proximidad al antipodal.

Una tolerancia razonable debería tener la forma:

$$
\tau_{\text{anti}}
=
C\sqrt{\epsilon_{\text{mach}}}
\cdot f(D,\text{error de reducción})
$$

La raíz aparece porque el error angular asociado a la cuerda puede escalar de manera distinta al error del producto punto. El valor de $C$ debe calibrarse con gradcheck y error máximo observado.

Ejemplo conceptual:

```cpp
double tau =
    32.0 * std::sqrt(std::numeric_limits<double>::epsilon())
    * std::sqrt(std::log2(static_cast<double>(n) + 1.0));
```

No conviene copiar esta fórmula sin validación; debe ser un parámetro de política.

## 9. Error del ángulo y error de la dirección

Cerca del antipodal, el valor escalar $\theta$ puede calcularse con alta precisión aunque la dirección sea completamente indeterminada.

Hay que reportar ambos errores:

$$
e_\theta=|\hat\theta-\theta|
$$

y:

$$
e_q=\sin^{-1}(|\hat q^\top q_{\text{ref}}|)
$$

Pero en el antipodal exacto no existe $q_{\text{ref}}$ único. En ese caso se valida:

- ortogonalidad $q^\top u\approx0$;
- norma $\|q\|\approx1$;
- determinismo;
- continuidad según la política elegida.


## 10. Gradientes: el parche escalar no basta

Para:

$$
\theta=\arccos(c)
$$

el gradiente respecto a $c$ es:

$$
\frac{d\theta}{dc}
=
-\frac{1}{\sqrt{1-c^2}}
$$

y diverge cuando $c\to\pm1$.

La fórmula con `atan2` mejora el forward, pero el backward debe derivarse de las cantidades realmente utilizadas. Si:

$$
\theta=2\operatorname{atan2}(h_-,h_+)
$$

entonces:

$$
d\theta
=
2\frac{h_+\,dh_- - h_-\,dh_+}{h_-^2+h_+^2}
$$

Para vectores unitarios, idealmente:

$$
h_-^2+h_+^2=1
$$

pero en punto flotante conviene calcular el denominador realmente observado.

### Problema en antipodal

Cuando $h_+\to0$, la derivada respecto a la dirección puede volverse no única. El valor de la distancia sigue siendo estable, pero el gradiente de una selección canónica puede tener un salto.

Recomendación:

- estabilizar el valor angular;
- definir explícitamente el gradiente en la región antipodal;
- usar `stop_gradient` para la dirección canónica si solo se necesita la distancia;
- o regularizar la geometría con una métrica suavizada.

No debe pretenderse que una elección arbitraria de dirección tenga un gradiente geométrico auténtico en el cut locus.

## 11. Distancia suavizada opcional

Si el optimizador necesita una función diferenciable en toda la esfera, puede definirse:

$$
\theta_\varepsilon
=
2\operatorname{atan2}
\left(
h_-,
\sqrt{h_+^2+\varepsilon^2}
\right)
$$

o usar una energía basada en cuerda:

$$
E(u,v)=\frac12\|u-v\|^2
$$

La energía chordal es suave incluso cuando la distancia geodésica tiene una selección no única. Pero esto cambia el objetivo:

- geodésica: respeta la métrica intrínseca;
- chordal: métrica embebida extrínseca.

La elección debe depender del algoritmo. No conviene mezclar ambas sin documentarlo.

## 12. Cálculo estable de las cuerdas

La solución debe reutilizar el kernel estable del problema 2:

$$
c_-^2=\sum_i(a_i-b_i)^2
$$

$$
c_+^2=\sum_i(a_i+b_i)^2
$$

Usar:

- reducción escalada;
- acumulación `float64` o superior;
- `TwoDiff`/`TwoSum` para modo científico;
- árbol determinista;
- superacumulador opcional.

Entonces:

$$
h_-=\frac12\sqrt{c_-^2}
$$

$$
h_+=\frac12\sqrt{c_+^2}
$$

No calcular primero el producto punto para luego derivar ambas cantidades:

$$
1-c
\quad\text{o}\quad
1+c
$$

porque esas restas vuelven a sufrir cancelación cerca de los extremos.

## 13. Normalización segura

Si $u,v$ tienen magnitudes arbitrarias, calcular `norm` con una suma directa puede desbordar. Usar:

$$
\|u\|=\operatorname{hypot}\text{-style}
$$

o una reducción escalada.

No hacer:

```cpp
double norm = std::sqrt(dot(u, u));
```

si los componentes pueden ser extremos.

La secuencia recomendada:

1. calcular $\log\|u\|$, $\log\|v\|$ o normas escaladas;
2. formar $a=u/\|u\|$, $b=v/\|v\|$;
3. calcular $a-b$ y $a+b$ con acumulación estable;
4. aplicar `atan2`.

Si la normalización pierde precisión, toda la decisión antipodal se contamina.

## 14. Comparación de métodos

| Método | Cerca de 0 | Cerca de $\pi$ | Gradiente | Coste |
| :-- | --: | --: | --: | --: |
| `acos(dot)` | Malo | Malo | Singular en extremos | Bajo |
| `acos(clamp(dot))` | Evita NaN | Evita NaN | Sigue inestable | Bajo |
| Fórmula `anti` de v911 | Bueno | Muy bueno | Debe derivarse aparte | Medio |
| `atan2(sin, cos)` | Bueno | Bueno | Mejor condicionado | Medio |
| $2\atan2(h_-,h_+)$ | Excelente | Excelente | Requiere política antipodal | Medio |
| Chordal pura | Excelente | Excelente | Suave | Bajo |
| Superacumulador + `atan2` | Excelente | Excelente | Coste alto | Muy alto |

La mejor ruta general es:

$$
\boxed{\theta=2\operatorname{atan2}
\left(\frac{\|a-b\|}{2},
\frac{\|a+b\|}{2}\right)}
$$

con normas y reducciones estables.

## 15. Continuidad topológica

La frase “continuidad topológica restaurada” debe matizarse:

- el **valor escalar** de la distancia puede hacerse continuo;
- la **dirección de la geodésica** no es continua globalmente en el antipodal;
- ninguna selección global de dirección evita el cut locus;
- una política canónica puede ser determinista, pero tendrá una discontinuidad en alguna frontera.

Esto es una propiedad topológica de la esfera, no un defecto de la implementación.

## 16. Tests SOTA

### Ángulo

Generar:

$$
v=\cos\theta\,u+\sin\theta\,q
$$

con $q\perp u$, para:

```text
theta = 0
theta = 1e-16
theta = 1e-12
theta = pi/2
theta = pi - 1e-12
theta = pi - 1e-16
theta = pi
```

Comparar contra una referencia de alta precisión.

### Vectores no normalizados

Multiplicar independientemente por:

```text
1e-300, 1e-100, 1, 1e100, 1e300
```

y verificar invariancia angular.

### Antipodal

- $v=-u$;
- $v=-u+\delta q$;
- perturbaciones en cada coordenada;
- diferentes órdenes de reducción;
- diferentes números de hilos.


### Derivadas

Comparar:

- forward;
- gradiente autodiferenciado;
- diferencias finitas;
- gradiente de `acos`;
- gradiente de `atan2`;
- gradiente de la fórmula híbrida.

En el antipodal exacto, no usar finite differences sobre una dirección arbitraria como si existiera un gradiente único.

### Propiedades

- $\theta(u,v)=\theta(v,u)$;
- $\theta(u,u)=0$;
- $\theta(u,-u)=\pi$;
- $\theta(-u,-v)=\theta(u,v)$;
- invariancia ante rotaciones ortogonales;
- rango $[0,\pi]$;
- monotonicidad en la familia de prueba.


## Veredicto

v911 corrige correctamente el **fallo numérico del valor angular cerca de $-1$**, y su fórmula antipodal es válida si los vectores están normalizados y las cuerdas se calculan de manera estable.

Pero una solución SOTA debe reemplazar el parche condicional por:

$$
\boxed{
\theta=
2\operatorname{atan2}
\left(
\frac{\|u-v\|}{2},
\frac{\|u+v\|}{2}
\right)
}
$$

después de una normalización robusta y una reducción estable.

Además debe separar:

1. **distancia angular**, que sí puede estabilizarse;
2. **dirección logarítmica**, que no es única en el antipodal;
3. **gradiente**, que requiere una política explícita o regularización;
4. **reproducibilidad**, que depende de la reducción de las dos cuerdas.

La solución completa es, por tanto:

$$
\boxed{
\text{normas escaladas}
+
\text{cuerdas }(u-v),(u+v)
+
\text{reducción reproducible}
+
2\operatorname{atan2}
+
\text{política explícita de cut locus}
}
$$

La corrección v911 debería aceptarse para el forward escalar, pero no declararse completa hasta definir el comportamiento del log map, los gradientes y el caso antipodal exacto.

<span style="display:none">[^6_10][^6_11][^6_12][^6_13][^6_14][^6_15][^6_16][^6_6][^6_7][^6_8][^6_9]</span>

<div align="center">⁂</div>

[^6_1]: https://d-nb.info/1302614177/34

[^6_2]: https://anson.ucdavis.edu/~mueller/sphere6.pdf

[^6_3]: https://mechcodex.com/learn/quality-reliability/vector-dot-and-cross-product

[^6_4]: https://thelinuxcode.com/angles-between-two-lines-in-3d-space-direction-vectors-conventions-edge-cases-and-solved-examples/

[^6_5]: https://caillau.perso.math.cnrs.fr/research/ampa-2014.pdf

[^6_6]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html

[^6_7]: http://www.few.vu.nl/~rci270/publications/preprintNODEA.pdf

[^6_8]: https://en.wikipedia.org/wiki/Great-circle_distance

[^6_9]: https://aimathcalculator.com/angle-between-vectors-calculator/

[^6_10]: https://thelinuxcode.com/spherical-trigonometry-for-developers-from-intuition-to-production-ready-geometry/

[^6_11]: https://thelinuxcode.com/angles-in-a-pentagon-interior-exterior-and-central-plus-the-checks-i-trust-in-real-code/

[^6_12]: https://thelinuxcode.com/derivative-of-inverse-trigonometric-functions-practical-differentiation-domains-and-stability/

[^6_13]: https://github.com/pytorch/pytorch/issues/59194

[^6_14]: https://possiblywrong.wordpress.com/2020/07/17/computing-the-angle-between-two-vectors/

[^6_15]: https://henk-reints.nl/HR-geodesics.pdf

[^6_16]: https://community.intel.com/t5/Intel-Fortran-Compiler/Numerically-stable-algorithm-for-the-angle-between-two-vectors/td-p/1010374?profile.language=en\&countrylabel=Latin%2525252525252520America


---

# Profundiza soluciones y mejoras sota

Para llevar este bug a una solución SOTA, hay que separar **tres problemas distintos**:

1. calcular de forma estable el ángulo;
2. calcular de forma estable el logaritmo riemanniano fuera del cut locus;
3. definir una política legítima cuando el punto es antipodal, donde el logaritmo no es único.

El parche v911 resuelve principalmente el primero. No puede resolver por sí solo el tercero, porque en una esfera el antipodal es el cut locus: existen infinitas geodésicas minimizantes y el logaritmo no tiene un valor único allí.[^7_1][^7_2]

## 1. Sustituir el branching por una fórmula global

La implementación no debería depender principalmente de:

```cpp
if (dot < -0.9999)
    // ruta antipodal
else
    acos(dot);
```

Ese umbral mezcla error de producto punto, dimensión, dtype y condición geométrica. La formulación global recomendada, para vectores normalizados $a,b$, es:

$$
h_-=\frac12\|a-b\|
$$

$$
h_+=\frac12\|a+b\|
$$

$$
\theta=2\operatorname{atan2}(h_-,h_+)
$$

La identidad se basa en:

$$
h_-=\sin\frac{\theta}{2},
\qquad
h_+=\cos\frac{\theta}{2}
$$

Ventajas:

- cerca de $0$, usa una cuerda pequeña sin restar $1-\cos\theta$;
- cerca de $\pi$, usa una cuerda antipodal pequeña sin calcular $1+\cos\theta$;
- devuelve naturalmente $[0,\pi]$;
- no necesita `acos`;
- no necesita un umbral discontinuo para elegir fórmula.

La mejora fundamental es que el branch deja de decidir **cómo calcular el ángulo**. Solo decide cómo tratar la **dirección del log map**.

## 2. Implementar las cuerdas con precisión científica

Las dos cantidades críticas son:

$$
c_-^2=\sum_i(a_i-b_i)^2
$$

$$
c_+^2=\sum_i(a_i+b_i)^2
$$

Deben calcularse con el mismo kernel robusto de la incidencia anterior:

- resta o suma compensada;
- acumulación promovida;
- suma de cuadrados escalada;
- reducción determinista;
- superacumulador opcional.

Después:

$$
h_-=\frac12\sqrt{c_-^2},
\qquad
h_+=\frac12\sqrt{c_+^2}
$$

No conviene calcular:

```cpp
dot = sum(a[i] * b[i]);
theta = acos(clamp(dot, -1.0, 1.0));
```

y luego intentar corregir el resultado con `1 + dot`. Cerca de $-1$, la cantidad útil es directamente $a+b$, no la diferencia entre dos números próximos a uno.

Una implementación conceptual:

```cpp
double angle_sphere(const Vector& u, const Vector& v) {
    double nu = stable_norm(u);
    double nv = stable_norm(v);

    if (!(nu > 0.0) || !(nv > 0.0))
        return NAN;

    Vector a = u / nu;
    Vector b = v / nv;

    double chord_minus_sq = stable_sumsq_difference(a, b);
    double chord_plus_sq  = stable_sumsq_sum(a, b);

    double hm = 0.5 * std::sqrt(std::max(0.0, chord_minus_sq));
    double hp = 0.5 * std::sqrt(std::max(0.0, chord_plus_sq));

    return 2.0 * std::atan2(hm, hp);
}
```

En producción, conviene evitar materializar `a` y `b` si la memoria es crítica: calcular los factores de normalización primero y realizar una segunda pasada fusionada.

## 3. No normalizar con un dot product ingenuo

La normalización también puede contaminar el test antipodal:

```cpp
norm = sqrt(sum(x[i] * x[i]));
```

debe reemplazarse por:

- `lassq`;
- reducción escalada;
- superacumulador en modo exacto.

Para cada vector:

$$
\|u\|^2=\sum_i u_i^2
$$

puede mantenerse como par escalado:

$$
\|u\|^2=s_u^2q_u
$$

y solo producirse la norma final si es representable.

Si $u,v$ contienen valores de rango extremo, incluso la división `u / norm` puede subdesbordar. En ese caso, calcular las cuerdas con escalado conjunto:

$$
a_i=\frac{u_i/\alpha}{\|u/\alpha\|},
\qquad
b_i=\frac{v_i/\beta}{\|v/\beta\|}
$$

donde $\alpha,\beta$ son escalas máximas de cada vector.

## 4. Reformular el `log map`

Para $a,b\in S^{n-1}$, sea:

$$
c=a^\top b
$$

$$
w=b-ca
$$

$$
s=\|w\|
$$

Fuera del antipodal:

$$
\operatorname{Log}_a(b)
=
\frac{\theta}{s}w
$$

Pero calcular $s=\sqrt{1-c^2}$ es inestable cerca de $\pm1$. Es mejor obtenerlo mediante la cuerda o una norma estable.

Una versión robusta:

```cpp
Vector sphere_log(Vector a, Vector b, double tau) {
    double c = stable_dot(a, b);
    c = std::clamp(c, -1.0, 1.0);

    double theta = stable_angle_from_chords(a, b);

    Vector w = b - c * a;
    double s = stable_norm(w);

    if (s > tau) {
        return (theta / s) * w;
    }

    return antipodal_policy(a, b, theta);
}
```

Sin embargo, si `s` es pequeño porque los puntos son casi paralelos, la dirección de `w` puede ser fiable o no según el tamaño relativo del error. Por eso hay que distinguir paralelo y antipodal usando `h_-` y `h_+`, no solo `s`.

## 5. Tres regiones geométricas

Definir:

$$
h_-=\frac12\|a-b\|,
\qquad
h_+=\frac12\|a+b\|
$$

### Región paralela

Si:

$$
h_- \le \tau_{\text{parallel}}
$$

entonces:

$$
\theta\approx0,
\qquad
\operatorname{Log}_a(b)\approx0
$$

Debe evitarse dividir por $h_-$.

### Región regular

Si:

$$
h_->\tau_{\text{parallel}}
\quad\text{y}\quad
h_+>\tau_{\text{anti}}
$$

usar el log map habitual:

$$
w=b-(a^\top b)a
$$

$$
\log_a(b)=\theta\frac{w}{\|w\|}
$$

### Región antipodal

Si:

$$
h_+\le\tau_{\text{anti}}
$$

la dirección no es única. Debe aplicarse una política explícita, no fingir que la fórmula ordinaria sigue siendo válida.

## 6. Política antipodal determinista

Una política útil para reproducibilidad es construir una dirección tangente canónica.

Elegir el eje menos alineado con $a$:

$$
j=\arg\min_k|a_k|
$$

$$
q_0=e_j-(e_j^\top a)a
$$

$$
q=\frac{q_0}{\|q_0\|}
$$

y devolver:

$$
\operatorname{Log}_a(b)=\theta q
$$

Código:

```cpp
Vector canonical_antipodal_direction(Vector a) {
    int j = argmin_abs_component(a);

    Vector q = basis(j) - a[j] * a;
    double nq = stable_norm(q);

    if (!(nq > 0.0))
        return deterministic_fallback(a);

    q /= nq;

    // Fijar signo de forma determinista.
    for (int i = 0; i < a.size(); ++i) {
        if (q[i] != 0.0) {
            if (q[i] < 0.0) q = -q;
            break;
        }
    }

    return q;
}
```


### Limitación topológica

Esta política es determinista, pero no globalmente continua. Alguna frontera debe existir porque no hay un campo tangente unitario global continuo en toda la esfera. Además, el logaritmo deja de ser único exactamente en el cut locus.[^7_3][^7_1]

Por tanto, debe documentarse como:

> selección canónica de una geodésica, no recuperación de la geodésica única.

## 7. Mejor opción si existe información temporal

Si los puntos forman una secuencia $b_t$, una dirección canónica basada únicamente en $a$ puede saltar entre frames. Es mejor usar continuidad temporal:

1. conservar la dirección anterior $q_{t-1}$;
2. proyectarla al espacio tangente de $a_t$;
3. normalizarla;
4. usarla como dirección antipodal si sigue siendo válida;
5. cambiar al eje canónico solo si la proyección degenera.
```cpp
q = q_prev - dot(q_prev, a) * a;

if (norm(q) > tau)
    q /= norm(q);
else
    q = canonical_antipodal_direction(a);
```

Esta política es adecuada para:

- trayectorias;
- integración temporal;
- seguimiento de geodésicas;
- optimización iterativa.

Pero introduce estado y ya no es una función puramente determinista de `(a,b)`.

## 8. Mejor opción si existe una dirección externa

En problemas con orientación física, el antipodal puede resolverse usando un vector de referencia:

- dirección de velocidad;
- tangente anterior;
- eje preferente;
- gradiente externo;
- frame local;
- vector de transporte paralelo.

Si $r$ es una referencia tangente:

$$
q=
\frac{r-(r^\top a)a}
{\|r-(r^\top a)a\|}
$$

Esto es superior a una elección arbitraria si el problema tiene semántica física. La geometría sola no selecciona una dirección.

## 9. Gradiente estable de la distancia

El ángulo mediante `atan2` mejora el forward, pero el gradiente necesita una derivación compatible.

Con:

$$
\theta=2\operatorname{atan2}(h_-,h_+)
$$

$$
d\theta
=
2\frac{h_+dh_- - h_-dh_+}
{h_-^2+h_+^2}
$$

Para vectores unitarios:

$$
h_-^2+h_+^2=1
$$

idealmente, pero conviene no imponerlo algebraicamente si las magnitudes tienen error.

El gradiente escalar de la distancia geodésica respecto a los vectores normalizados puede escribirse, fuera del cut locus, como:

$$
\nabla_a \theta
=
-\frac{b-(a^\top b)a}
{\sqrt{1-(a^\top b)^2}}
$$

Es precisamente el factor que se vuelve mal condicionado cerca de antipodal y paralelo.

Una forma numéricamente coherente es reutilizar:

$$
w=b-ca
$$

y:

$$
s=\|w\|
$$

pero calcular $s$ establemente y activar una política en ambas regiones extremas.

## 10. Gradiente en el antipodal

No existe un gradiente único de la distancia geodésica en el antipodal. Por ello hay tres estrategias válidas:

### A. Subgradiente canónico

Elegir $q$ determinista y usar:

$$
\nabla_a\theta=-q
$$

Esto permite continuar la optimización, pero la elección es una convención.

### B. Gradiente bloqueado

Para la rama antipodal:

```text
theta = pi
gradient = 0
```

Es estable, pero puede detener el optimizador.

### C. Regularización suave

Usar una función suavizada:

$$
\theta_\varepsilon
=
2\operatorname{atan2}
\left(
h_-,
\sqrt{h_+^2+\varepsilon^2}
\right)
$$

o una energía chordal:

$$
E=\frac12\|a-b\|^2
$$

Esto proporciona gradientes más manejables, pero ya no optimiza exactamente la distancia geodésica.

Para entrenamiento, la opción C suele ser más robusta. Para geometría científica, A o una exclusión explícita del cut locus puede ser preferible.

## 11. Hessiano y optimización

La inestabilidad puede reaparecer aunque el gradiente parezca estable. El Hessiano de la distancia cuadrada riemanniana también presenta estructura singular en el cut locus. En la esfera, el antipodal es exactamente donde convergen múltiples geodésicas minimizantes.[^7_1]

Si se optimiza:

$$
F(a)=\frac12\theta(a,b)^2
$$

fuera del cut locus:

$$
\nabla_a F=-\operatorname{Log}_a(b)
$$

Pero cerca de $\theta=\pi$:

- el gradiente depende de la dirección elegida;
- el Hessiano puede cambiar bruscamente;
- Newton o quasi-Newton puede divergir;
- la selección canónica puede introducir artefactos.

Recomendaciones:

- trust region;
- step clipping;
- line search geodésico;
- evitar saltos a través del cut locus;
- usar energía chordal durante la fase inicial;
- cambiar a distancia intrínseca cuando $h_+$ sea suficientemente grande.


## 12. Umbrales adaptativos

No usar:

```cpp
dot < -0.9999
```

Usar dos umbrales geométricos:

$$
\tau_-=C_-\sqrt{\epsilon_{\text{eff}}}
$$

$$
\tau_+=C_+\sqrt{\epsilon_{\text{eff}}}
$$

donde:

$$
\epsilon_{\text{eff}}
\approx
\epsilon_{\text{mach}}
+
\epsilon_{\text{reduction}}
+
\epsilon_{\text{normalization}}
$$

Para una reducción de $D$ términos, el error simple puede crecer como $O(D\epsilon)$, mientras que una suma pairwise o compensada tiene un crecimiento menor. El valor exacto debe medirse para el kernel real.

Una estimación práctica:

```cpp
double eps_eff =
    eps_machine
    * (1.0 + reduction_error_bound(D, mode))
    + normalization_error_bound;

double tau = C * std::sqrt(eps_eff);
```

La constante $C$ debe validarse con:

- error angular máximo;
- tasa de activación de la rama;
- continuidad observada;
- gradcheck.


## 13. Forward y backward deben compartir estadísticas

Un error frecuente es:

- forward calcula $\theta$ con `chordanti`;
- backward vuelve a calcular `dot`;
- las dos rutas toman decisiones distintas.

Debe almacenarse en el contexto del operador:

```cpp
struct AngleCache {
    double theta;
    double h_minus;
    double h_plus;
    double dot;
    Vector tangent;
    uint8_t region;
};
```

Regiones:

```text
0 = regular
1 = parallel
2 = antipodal
3 = invalid
```

El backward debe usar exactamente la región y los estadísticos del forward. Esto evita que un valor cercano al umbral produzca:

```text
forward = antipodal branch
backward = acos branch
```


## 14. Reproducibilidad de la rama antipodal

Aunque `atan2` sea estable, la decisión de la rama puede variar si `h_plus` cambia en el último bit entre hilos. Para evitarlo:

- calcular `h_plus` con reducción reproducible;
- usar un umbral con margen;
- almacenar la región;
- no recalcularla en backward;
- usar comparación con intervalo si el resultado está dentro de la incertidumbre.

Una política avanzada puede clasificar:

```text
regular:
    h_plus > tau_high

definitely antipodal:
    h_plus < tau_low

ambiguous:
    tau_low <= h_plus <= tau_high
```

En la región ambigua:

- usar la fórmula escalar global;
- no construir un log vector único;
- devolver un flag `near_cut_locus`;
- activar regularización o dirección externa.

Esto es mejor que una decisión binaria artificial.

## 15. API científica recomendada

```cpp
enum class CutLocusPolicy {
    Reject,
    CanonicalDirection,
    PreviousDirection,
    ExternalDirection,
    SmoothRegularization,
    ChordalFallback
};

enum class AngleMode {
    FastAtan2,
    StableChord,
    ReproducibleChord,
    ExactChord
};

struct GeodesicResult {
    double angle;
    Vector log;
    bool valid;
    bool near_parallel;
    bool near_antipodal;
    bool on_cut_locus;
    bool regularized;
    double conditioning;
};
```

Semántica:

- `Reject`: devuelve error al alcanzar cut locus;
- `CanonicalDirection`: dirección determinista;
- `PreviousDirection`: continuidad temporal;
- `ExternalDirection`: usa una referencia física;
- `SmoothRegularization`: modifica el objetivo para obtener diferenciabilidad;
- `ChordalFallback`: abandona temporalmente la métrica intrínseca.

Ocultar estas decisiones dentro de un `if` produce comportamientos difíciles de auditar.

## 16. Integración con la solución exacta anterior

La solución SOTA completa debe reutilizar el pipeline de `chordal_sq`:

```text
normalización estable
    ↓
cuerda u-v con reducción reproducible
    ↓
cuerda u+v con reducción reproducible
    ↓
sqrt estable
    ↓
atan2 de medio ángulo
    ↓
clasificación de región
    ↓
log map regular o política cut locus
```

En modo `ExactSuperaccumulator`:

- calcular ambas cuerdas con acumuladores exactos;
- redondearlas una sola vez;
- calcular el ángulo;
- registrar si $h_+$ está dentro de la zona de incertidumbre.

Esto evita que el ángulo y la decisión geométrica estén basados en dos reducciones con distinta precisión.

## 17. Tests de nivel científico

### Forward

Generar un $a$ unitario y un $q\perp a$:

$$
b(\theta)=\cos\theta\,a+\sin\theta\,q
$$

Probar:

$$
\theta\in
\{0,10^{-16},10^{-12},10^{-8},
\frac{\pi}{2},
\pi-10^{-8},\pi-10^{-12},\pi\}
$$

Comparar con MPFR o una referencia de precisión extendida.

### Log map

Para región regular:

$$
\|\operatorname{Log}_a(b)\|\approx\theta
$$

$$
a^\top\operatorname{Log}_a(b)\approx0
$$

$$
\operatorname{Exp}_a(\operatorname{Log}_a(b))\approx b
$$

Para antipodal:

- norma del log igual a $\pi$;
- ortogonalidad;
- determinismo;
- política correctamente reportada.


### Gradientes

- finite differences lejos del cut locus;
- gradcheck con perturbaciones que no crucen el cut locus;
- pruebas separadas de la rama regularizada;
- no comparar contra un gradiente único inexistente en el antipodal exacto.


### Reproducibilidad

Comparar:

- distinto número de hilos;
- distinto orden de bloques;
- FMA activado/desactivado;
- AVX2, AVX-512, ARM;
- rutas `Fast`, `Stable`, `Exact`.


## 18. Veredicto técnico

v911 es un buen parche para el valor angular, pero la solución SOTA debe evolucionar a:

$$
\boxed{
\text{ángulo por cuerdas}
+
\operatorname{atan2}
+
\text{reducción reproducible}
+
\text{clasificación adaptativa}
+
\text{política explícita del cut locus}
}
$$

La fórmula central recomendada es:

$$
\boxed{
\theta=
2\operatorname{atan2}
\left(
\frac{\|a-b\|}{2},
\frac{\|a+b\|}{2}
\right)
}
$$

Y para el log map:

$$
\boxed{
\operatorname{Log}_a(b)=
\begin{cases}
\theta\,\dfrac{b-(a^\top b)a}
{\|b-(a^\top b)a\|},
& \text{fuera del cut locus},\\[1.2em]
\theta q,
& \text{casi antipodal, con política explícita}.
\end{cases}
}
$$

La mejora más importante no es cambiar `acos` por `asin`, sino reconocer que:

- el ángulo es escalar y puede estabilizarse;
- la dirección antipodal no es única;
- el gradiente puede no existir de forma única;
- la continuidad global del log map es imposible;
- la implementación debe exponer esa singularidad como parte del contrato matemático.

Con este diseño, el sistema deja de “ocultar” la singularidad antipodal y pasa a tratarla de manera numéricamente estable, geométricamente correcta y reproducible.

<span style="display:none">[^7_10][^7_11][^7_12][^7_13][^7_14][^7_15][^7_4][^7_5][^7_6][^7_7][^7_8][^7_9]</span>

<div align="center">⁂</div>

[^7_1]: https://www-sop.inria.fr/members/Xavier.Pennec/AOS-DiffRiemannianLog.pdf

[^7_2]: https://inria.hal.science/inria-00614994v1/document

[^7_3]: https://www-sop.inria.fr/asclepios/Publications/Xavier.Pennec/Pennec_ETVC08.pdf

[^7_4]: https://papers.nips.cc/paper/2021/file/b91b1facf3b3a7890177f02ac188f14c-Paper.pdf

[^7_5]: https://www-sop.inria.fr/asclepios/Publications/Xavier.Pennec/Pennec_RR_Tensors.pdf

[^7_6]: https://arxiv.org/html/2502.13106

[^7_7]: https://www.arxiv.org/pdf/2101.09346.pdf

[^7_8]: https://pmc.ncbi.nlm.nih.gov/articles/PMC3085642/

[^7_9]: https://arxiv.org/pdf/1801.06881v1.pdf

[^7_10]: https://findresearcher.sdu.dk/ws/portalfiles/portal/194955772/thesis_main.pdf

[^7_11]: https://arxiv.org/pdf/2606.07926v1.pdf

[^7_12]: https://www-sop.inria.fr/asclepios/Publications/Xavier.Pennec/ComputationalAnatomy.pdf

[^7_13]: https://arxiv.org/pdf/1908.04233.pdf

[^7_14]: https://en.wikipedia.org/wiki/Arctan2

[^7_15]: https://simulations4all.com/simulations/circle-theorems-explorer


---

# 4. Fragmentación de Heap en Retracción Cayley-Stiefel (Cuello de Botella de Cómputo)evalua soluciones y mejoras sota

Falla: El solver iterativo matricial matric-free solve_linear_system_2k instanciaba un vector dinámico std::vector\<double> aug(...) internamente. Siendo llamado en el hot path (cada iteración del optimizador), el malloc / free masivo saturaba el anillo del sistema operativo destruyendo el throughput multinúcleo en cargas de grafos pesadas.
Estado (v911): Optimizado. Se insertó un stack array 256×384256 \\times 384256×384 capaz de contener subvariedades hasta K≤128K \\le 128K≤128. Dinamismo delegado exclusivamente a desbordes extremos.

El parche v911 elimina el coste más obvio, pero no es todavía una solución SOTA completa. Sustituir `std::vector<double>` por un array fijo `256×384` evita `malloc/free` para ciertos tamaños, pero introduce riesgos de **stack overflow, presión de caché, falsa seguridad de capacidad, spill path caro y posible pérdida de paralelismo**.

La solución de producción debería ser:

$$
\boxed{
\text{workspace persistente por contexto/hilo}
+
\text{solver de baja memoria}
+
\text{fallback dimensionado}
+
\text{control de concurrencia}
+
\text{benchmark de asignación y caché}
}
$$

## 1. Qué resuelve y qué no resuelve v911

### Beneficios

- elimina asignaciones dinámicas en el caso común;
- reduce contención del allocator;
- mejora la latencia de la iteración;
- evita fragmentación del heap;
- hace predecible el coste de memoria.

Las asignaciones frecuentes pueden serializarse internamente porque los allocators generales son thread-safe; en cargas de tareas finas, la contención del allocator puede convertirse en una fracción apreciable del tiempo total.[^8_1]

### Problemas del array `256×384`

Si cada elemento es `double`:

$$
256\times384\times8
=
786\,432\text{ bytes}
$$

es decir, aproximadamente **768 KiB por invocación**.

Eso es demasiado grande para un stack típico por hilo en muchos entornos. Si el solver se ejecuta dentro de una región OpenMP y cada hilo tiene su propio array, el consumo puede crecer como:

$$
768\text{ KiB}\times N_{\text{threads}}
$$

Con 64 hilos son unos 48 MiB de stack distribuido, además de riesgos de:

- desbordamiento de stack;
- presión sobre la caché L2/L3;
- fallos de página;
- pérdida de localidad;
- aumento del tiempo de inicialización;
- interferencia con otras variables automáticas.

Por tanto, el array fijo debe considerarse una optimización condicionada, no la arquitectura final.

## 2. Cuestionar el tamaño $256\times384$

El texto afirma que soporta subvariedades $K\le128$. Hay que verificar la dimensión real del sistema.

Si `solve_linear_system_2k` resuelve un sistema de tamaño $2K$, una matriz aumentada densa necesita:

$$
(2K)\times(2K+1)
$$

Para $K=128$:

$$
256\times257
$$

No $256\times384$, salvo que:

- exista padding vectorial;
- se reserve espacio para varios RHS;
- el algoritmo mantenga bloques adicionales;
- el kernel use una representación ampliada.

La capacidad debe expresarse con una constante semántica:

```cpp
constexpr int MAX_K = 128;
constexpr int NMAX = 2 * MAX_K;
constexpr int RHS_PAD = ...;
```

y no con números mágicos.

## 3. Mejor alternativa: workspace persistente

La solución recomendada es asignar el workspace una vez fuera del hot path y reutilizarlo.

```cpp
struct CayleyWorkspace {
    double* aug;
    int capacity;
    int stride;
    std::size_t bytes;
};
```

Creación:

```cpp
CayleyWorkspace create_workspace(int max_n) {
    std::size_t bytes =
        aligned_bytes(max_n * (max_n + 1), 64);

    void* p = aligned_alloc(64, bytes);

    if (!p)
        throw std::bad_alloc();

    return {
        static_cast<double*>(p),
        max_n,
        max_n + 1,
        bytes
    };
}
```

Uso:

```cpp
void solve(..., CayleyWorkspace& ws) {
    if (n > ws.capacity)
        fallback_or_grow(ws, n);

    double* aug = ws.aug;
    ...
}
```

Ventajas:

- cero asignaciones por iteración;
- tamaño ajustado a la configuración real;
- control explícito de alineación;
- vida útil clara;
- facilita NUMA y afinidad;
- evita consumir stack.


## 4. Workspace por hilo

Si varias ejecuciones concurrentes usan el solver, un único workspace compartido requiere locks o produce carreras. La opción SOTA es un workspace por worker:

```cpp
struct ThreadWorkspace {
    alignas(64) std::vector<double> storage;
    int capacity = 0;
};

#pragma omp parallel
{
    int tid = omp_get_thread_num();

    ThreadWorkspace& ws = workspaces[tid];

    #pragma omp for
    for (...) {
        solve_with_workspace(..., ws);
    }
}
```

El vector se reserva una sola vez durante la fase de inicialización. La asignación no ocurre en el hot path.

OpenMP también define allocators con alcance `thread`, `pteam` y `omp_default_mem_alloc`, lo que permite expresar formalmente la visibilidad y el ownership del workspace.[^8_2][^8_3]

### Cuidado con `std::vector`

Un `std::vector` persistente es aceptable. Lo que debe evitarse es:

```cpp
std::vector<double> aug(...);
```

dentro de cada llamada.

Debe hacerse:

```cpp
ws.aug.resize(required);
```

solo cuando se supera la capacidad, idealmente durante una fase controlada y no durante la iteración crítica.

## 5. Alternativa: arena monotónica

Si el solver necesita varias estructuras temporales, no solo `aug`, usar una arena por hilo:

```cpp
class ScratchArena {
public:
    void* allocate(std::size_t bytes,
                   std::size_t alignment);

    void reset() noexcept;
};
```

Cada iteración:

```cpp
arena.reset();

double* aug = arena.allocate(bytes_aug, 64);
double* piv = arena.allocate(bytes_piv, 64);
double* tmp = arena.allocate(bytes_tmp, 64);
```

El `reset()` solo mueve un puntero. No hay `free` individual.

Una arena por hilo evita locks y mejora la localidad; los allocators locales por worker son una estrategia común para reducir contención.[^8_4][^8_5]

### No usar una arena global

Una arena global con bump pointer atómico puede convertirse en un nuevo cuello de botella. El ownership recomendado es:

```text
solver instance
    └── worker 0 arena
    └── worker 1 arena
    └── ...
```

No:

```text
todos los hilos → arena global con atomic
```


## 6. Stack: cuándo sí y cuándo no

Un buffer en stack puede ser correcto si:

- el tamaño es pequeño;
- la función no se llama recursivamente;
- el límite está documentado;
- el número de hilos y stack disponible están controlados;
- el compilador no produce un frame enorme inesperado.

Para $n\le64$, un buffer local puede ser razonable:

```cpp
std::array<double, 64 * 65> local;
```

Para $n=256$, no lo recomendaría como stack por defecto. Es preferible:

- workspace persistente;
- buffer `thread_local`;
- arena por hilo;
- memoria alineada preasignada.


## 7. `thread_local` como solución intermedia

Una opción simple:

```cpp
thread_local ScratchArena arena;
```

Ventajas:

- no requiere pasar explícitamente el workspace;
- ownership natural;
- cero locks;
- persistencia entre llamadas.

Desventajas:

- difícil de controlar memoria total;
- vida útil asociada al hilo;
- problemas si cambian los pools de threads;
- menos transparencia en tests;
- posible retención excesiva de memoria.

Para una biblioteca científica, prefiero pasar un `Workspace&` explícito. Para un kernel interno de alto rendimiento, `thread_local` puede ser aceptable si se documenta.

## 8. Mejorar el solver: no formar la matriz aumentada completa

La mayor mejora puede no ser el allocator, sino eliminar `aug`.

Si el sistema de Cayley tiene estructura especial, hay que explotarla. Una retraction Cayley típica utiliza una matriz skew-symmetric $W$ y resuelve:

$$
(I-\alpha W)X=(I+\alpha W)X_0
$$

En estructuras Stiefel, el gradiente o actualización frecuentemente permite una representación de rango bajo. El uso de Sherman–Morrison–Woodbury puede reducir el problema a un sistema de tamaño $2K$, evitando inversiones grandes; este patrón se utiliza en optimizadores Stiefel recientes.[^8_6]

Pero incluso un sistema $2K\times2K$ puede evitarse si:

- el operador se aplica matrix-free;
- se usa GMRES/MINRES;
- se explota bajo rango;
- se factoriza una vez y se actualiza;
- se usa un solver block-tridiagonal o estructurado.

La pregunta clave es:

> ¿El solver necesita una matriz aumentada densa, o solo un operador $A x$?

Si solo necesita productos matriz-vector, el workspace puede bajar de $O(K^2)$ a $O(K)$.

## 9. Solver matrix-free

En lugar de construir:

```cpp
aug[i * ld + j]
```

definir:

```cpp
void apply_operator(
    const Vector& x,
    Vector& y,
    const CayleyState& state);
```

y usar un método iterativo:

- CG si el operador es SPD;
- MINRES si es simétrico indefinido;
- GMRES si es no simétrico;
- BiCGSTAB si la memoria es crítica.

Workspace aproximado:

- CG: varios vectores de tamaño $n$;
- MINRES: pocos vectores;
- GMRES: $O(mn)$ para restart $m$.

Para $n=256$, una matriz aumentada puede ser barata, pero para muchos solves por iteración y múltiples hilos, evitar materialización puede reducir:

- memoria;
- tráfico de caché;
- inicialización;
- presión de bandwidth.


## 10. Factorización reutilizable

Si la estructura del sistema cambia lentamente, se puede reutilizar:

- pivotado;
- precondicionador;
- factorización aproximada;
- patrón de sparsity;
- workspace de eliminación.

Pero no se debe reutilizar ciegamente una factorización si el operador cambia significativamente. La política puede basarse en:

$$
\frac{\|A_{t+1}-A_t\|}{\|A_t\|}
<\tau_A
$$

Si se cumple, actualizar parcialmente. Si no, refactorizar.

Para sistemas $2K$ pequeños, una factorización LU compacta reutilizable puede ser más rápida que un solver iterativo general.

## 11. Evitar la matriz aumentada si hay varios RHS

Si el sistema se resuelve para varios vectores, no construir una matriz aumentada separada por RHS. Usar un layout block:

```text
A | B
```

o factorizar:

$$
A=LU
$$

y resolver todos los RHS juntos:

$$
AX=B
$$

Esto mejora:

- reutilización de caché;
- BLAS-3;
- vectorización;
- coste amortizado de pivotado.

Si `2K=256` y hay varios RHS, el formato debería ser adaptable:

```cpp
enum class Layout {
    RowMajor,
    ColMajor,
    Blocked
};
```

La elección depende de si el solver está orientado a filas, columnas o kernels SIMD.

## 12. Alineación y layout

El workspace debe alinearse al menos a:

- 64 bytes para líneas de caché;
- 64 o 128 bytes según el vector ISA;
- alineación requerida por BLAS externo.

Usar:

```cpp
void* p = std::aligned_alloc(64, bytes_rounded);
```

o un allocator alineado propio.

Evitar:

```cpp
struct {
    double aug[...];
    double other[...];
};
```

si múltiples hilos escriben estructuras contiguas, porque pueden compartir líneas de caché. El false sharing puede degradar la escalabilidad cuando hilos actualizan memoria adyacente.[^8_7][^8_8]

Separar workspaces por al menos una línea de caché:

```cpp
struct alignas(64) ThreadWorkspace {
    ...
};
```

y añadir padding si el allocator coloca objetos adyacentes.

## 13. NUMA y afinidad

En cargas pesadas de grafos, el problema puede pasar de allocator a NUMA.

Recomendaciones:

1. crear el workspace dentro de la región paralela;
2. tocar las páginas desde el hilo que las usará;
3. mantener afinidad de hilo;
4. evitar que un workspace de NUMA node 0 sea utilizado por todos;
5. usar first-touch.

Esquema:

```cpp
#pragma omp parallel
{
    int tid = omp_get_thread_num();
    auto& ws = workspaces[tid];

    if (!ws.initialized)
        ws.initialize_on_local_cpu();

    ...
}
```

La asignación NUMA-local reduce latencia de memoria y tráfico entre nodos. En implementaciones modernas se recomienda asociar cada hilo a su dominio NUMA y mantener su working set local.[^8_9]

## 14. Overflow path correctamente diseñado

“Dinamismo delegado exclusivamente a desbordes extremos” es correcto como principio, pero el fallback no debe volver a llamar a `std::vector` en cada overflow.

Mala implementación:

```cpp
if (k > MAX_K) {
    std::vector<double> dynamic_aug(...);
}
```

Mejor:

```cpp
struct Workspace {
    StaticBuffer fast;
    DynamicBuffer slow;
};
```

El buffer slow debe:

- reservarse una vez;
- crecer geométricamente;
- conservar capacidad;
- estar asociado al hilo;
- registrar el número de overflows.

```cpp
if (required > ws.capacity) {
    ws.reserve(round_up_pow2(required));
    ws.overflow_count++;
}
```

Si el tamaño máximo es conocido por fase, reservarlo antes de comenzar el hot loop.

## 15. Evitar crecimiento no determinista

Si el solver puede ejecutarse concurrentemente, el crecimiento lazy del workspace puede producir:

- jitter;
- carreras;
- diferencias de rendimiento;
- fallos de memoria en mitad del entrenamiento.

Hacer una fase de planificación:

```cpp
WorkspacePlan plan = inspect_problem_sizes(graph_batch);
initialize_workspaces(plan);
run_hot_loop();
```

El hot loop debe funcionar con:

```text
no malloc
no free
no resize
no locks
```

Si ocurre un overflow no planificado:

- abortar con diagnóstico;
- cambiar a modo lento controlado;
- o replanificar fuera de la iteración crítica.


## 16. Estabilidad numérica del solver

Eliminar `malloc` no garantiza que la retraction sea numéricamente estable. El solve debe medir:

- crecimiento de pivotes;
- condición estimada;
- residuo relativo;
- número de iteraciones;
- breakdown;
- pérdida de ortogonalidad.

Para cada solve, verificar:

$$
r=b-Ax
$$

$$
\eta=
\frac{\|r\|}
{\|A\|\|x\|+\|b\|}
$$

Si $\eta>\tau_{\text{solve}}$:

- repetir con mayor precisión;
- aplicar reortogonalización;
- usar fallback LU;
- reducir paso de la retraction;
- reportar fallo.

La solución SOTA combina optimización de memoria con **iterative refinement**:

1. resolver en `float32` o `float64`;
2. calcular residual en mayor precisión;
3. corregir;
4. repetir hasta tolerancia.

Esto puede reducir coste sin sacrificar precisión.

## 17. Tipos mixtos

Para sistemas pequeños y repetidos:

- matriz/workspace en `float32`;
- acumulación y residual en `float64`;
- refinamiento iterativo en `float64`.

Pero si la geometría Stiefel requiere alta precisión, no degradar automáticamente el solve solo para ahorrar memoria.

Una política:

```text
FAST:
    float32 solve + float32 residual

STABLE:
    float32 solve + float64 residual + refinement

EXACT:
    float64 solve + deterministic pivoting
```

El uso de mixed precision debe validarse sobre:

$$
\|X^\top X-I\|
$$

después de la retraction, no solo sobre el residuo lineal.

## 18. Retraction Cayley y coste estructural

Para $X\in\mathrm{St}(n,p)$, la retraction Cayley debe preservar aproximadamente:

$$
X^\top X=I
$$

La implementación debe medir:

$$
\delta_{\text{orth}}
=
\|X_{\text{new}}^\top X_{\text{new}}-I\|
$$

Si el solver lineal es aproximado, el error de ortogonalidad puede acumularse aunque cada iteración parezca aceptable.

Mejoras:

- resolver con tolerancia relativa;
- adaptar la tolerancia al tamaño del paso;
- reortogonalizar periódicamente;
- usar polar/QR como corrección ocasional;
- controlar $\|W\|\alpha$;
- rechazar pasos con deterioro ortogonal excesivo.

La ruta híbrida habitual es:

```text
Cayley barata en cada iteración
QR/polar correctiva cada M iteraciones o si orthogonality error > τ
```

Esto suele ser mejor que aplicar QR siempre o confiar ciegamente en un solve aproximado.

## 19. Benchmark correcto

No medir solo tiempo total. Separar:

### Allocator

- número de `malloc/free`;
- bytes asignados;
- p50/p95/p99 de latencia;
- contención;
- fallos de página.


### Solver

- tiempo de setup;
- tiempo de reducción;
- tiempo de factorización;
- tiempo de iteraciones;
- residual;
- fallos y reintentos.


### Memoria

- RSS;
- memoria por hilo;
- L1/L2/L3 misses;
- ancho de banda;
- false sharing;
- NUMA remote accesses.


### Geometría

- error de ortogonalidad;
- convergencia;
- número de iteraciones del optimizador;
- calidad final;
- estabilidad entre hilos.

Herramientas:

```text
perf stat
perf record
heaptrack
valgrind massif
VTune
LIKWID
Nsight, si aplica GPU
```

Una mejora que elimina malloc pero aumenta LLC misses puede empeorar el throughput total.

## 20. Diseño SOTA recomendado

### Nivel 1: reparación inmediata

- sacar `std::vector` del hot path;
- usar workspace persistente;
- eliminar `critical`;
- reservar capacidad una vez;
- usar `std::array` solo para tamaños pequeños.


### Nivel 2: producción

- workspace por hilo;
- arena monotónica;
- alineación de 64 bytes;
- first-touch NUMA;
- fallback pre-reservado;
- instrumentación de overflow;
- layout compatible con BLAS/SIMD.


### Nivel 3: científico

- solver matrix-free o Woodbury;
- factorización reutilizable;
- mixed precision con refinamiento;
- residual y ortogonalidad monitorizados;
- retraction correctiva periódica;
- modo determinista;
- benchmark de error y rendimiento.


## Veredicto

v911 es una mejora válida, pero el `stack array 256×384` no debería considerarse la solución definitiva. Para $K\le128$, ese buffer tiene aproximadamente 768 KiB por llamada y puede ser demasiado grande para el stack, especialmente dentro de OpenMP.

La solución SOTA es:

$$
\boxed{
\text{workspace persistente por hilo}
+
\text{arena sin locks}
+
\text{fallback pre-reservado}
+
\text{memoria NUMA-local}
+
\text{solver estructurado o matrix-free}
+
\text{refinamiento y control de ortogonalidad}
}
$$

El objetivo operativo debe ser que el hot path cumpla:

```text
0 malloc/free
0 resize
0 lock
0 false sharing deliberado
0 acceso remoto innecesario
```

y que el solver reporte simultáneamente:

```text
residual lineal
error de ortogonalidad
número de iteraciones
uso de fallback
bytes de workspace
```

Solo así se puede afirmar que v911 resolvió el cuello de botella de cómputo, y no simplemente trasladó el coste desde el heap hacia el stack, la caché o la memoria NUMA.

<span style="display:none">[^8_10][^8_11][^8_12][^8_13][^8_14][^8_15]</span>

<div align="center">⁂</div>

[^8_1]: http://arxiv.org/pdf/2502.05293.pdf

[^8_2]: https://www.openmp.org/spec-html/5.2/openmpse35.html

[^8_3]: https://www.openmp.org/spec-html/5.0/openmpsu53.html

[^8_4]: https://arxiv.org/html/2502.13862v1

[^8_5]: https://dev.to/beefedai/designing-a-custom-arena-allocator-for-high-throughput-services-1hkk

[^8_6]: https://arxiv.org/pdf/2609.21039v1.pdf

[^8_7]: https://www.openmp.org/wp-content/uploads/openmp-webinar-vanderPas-20210318.pdf

[^8_8]: https://docs.oracle.com/cd/E19059-01/stud.9/817-6703/6_tuning.html

[^8_9]: https://arxiv.org/html/2506.09198v2

[^8_10]: https://www.arxiv.org/pdf/2303.16510.pdf

[^8_11]: https://www.openmp.org/spec-html/5.2/openmp.html

[^8_12]: https://dionisio.dev/en/artigos-tecnicos/cpp-hft-low-latency/

[^8_13]: https://ccmcode.dev/engineering/why-malloc-kills-latency

[^8_14]: https://simplifycpp.org/download/book.php?id=17170

[^8_15]: https://github.com/KilianDiama/StiefelOptimizer


---

# Profundiza soluciones y mejoras sota

La mejora SOTA para este cuello de botella no es simplemente cambiar `std::vector` por un array en stack. Hay que optimizar simultáneamente:

$$
\boxed{
\text{modelo de memoria}
+
\text{estructura algebraica}
+
\text{solver}
+
\text{precisión}
+
\text{retraction}
}
$$

La prioridad debería ser eliminar la necesidad de crear una matriz aumentada densa en cada llamada. Los métodos Cayley eficientes ya explotan aproximaciones iterativas, multiplicaciones matriciales y estructuras de bajo rango para evitar inversiones costosas.[^9_1][^9_2]

## 1. Diagnóstico profundo

La ruta actual probablemente hace algo conceptualmente similar a:

```cpp
solve_linear_system_2k(A, b) {
    std::vector<double> aug((2 * k) * (2 * k + rhs));
    build_augmented_matrix(aug, A, b);
    gaussian_elimination(aug);
    extract_solution(aug);
}
```

El coste no es solo `malloc/free`. Cada llamada también incurre en:

- inicialización de la matriz;
- escritura completa del workspace;
- lectura y escritura de pivotes;
- presión sobre L1/L2/L3;
- posibles fallos de caché;
- sincronización del allocator;
- pérdida de localidad entre iteraciones;
- serialización accidental si varios hilos usan el mismo allocator.

Por ello, aunque v911 elimine las asignaciones, el sistema puede seguir limitado por **ancho de banda y tráfico de caché**.

La métrica correcta no es únicamente:

```text
allocations = 0
```

sino:

```text
bytes escritos por solve
bytes leídos por solve
L1/L2/L3 misses
tiempo de setup
tiempo de factorización
tiempo de aplicación del operador
```


## 2. Arquitectura de memoria recomendada

### Workspace persistente por solver

```cpp
struct CayleyWorkspace {
    double* aligned_data = nullptr;
    std::size_t capacity = 0;
    std::size_t used = 0;

    void reset() noexcept {
        used = 0;
    }
};
```

El objeto se crea durante la fase de inicialización, no en la iteración:

```cpp
class CayleyContext {
public:
    std::vector<CayleyWorkspace> per_thread;
    int max_dim;
};
```

El hot path solo ejecuta:

```cpp
workspace.reset();
double* p = workspace.allocate(bytes, 64);
```

donde `allocate` es un bump pointer sin locks.

### Arena por hilo

```cpp
class ScratchArena {
    std::byte* base_;
    std::size_t capacity_;
    std::size_t offset_;

public:
    void reset() noexcept {
        offset_ = 0;
    }

    template <typename T>
    T* allocate(std::size_t count) {
        std::size_t bytes = count * sizeof(T);
        std::size_t aligned = align_up(offset_, alignof(T));

        if (aligned + bytes > capacity_)
            return nullptr;

        auto* p = reinterpret_cast<T*>(base_ + aligned);
        offset_ = aligned + bytes;
        return p;
    }
};
```

Características necesarias:

- alineación explícita;
- ownership por hilo;
- `reset()` O(1);
- capacidad conocida;
- contador de overflow;
- ningún lock durante la iteración.


## 3. Por qué el stack array no es la mejor solución general

Un buffer de $256\times384$ `double` ocupa aproximadamente 768 KiB. Si se declara dentro de una función llamada por cada hilo:

```cpp
double aug[^9_256][^9_384];
```

pueden aparecer:

- desbordamientos de stack;
- guard pages activadas;
- mayor coste de prologue/epilogue;
- presión de caché;
- pérdida de capacidad para otras funciones;
- comportamiento distinto entre runtimes OpenMP.

Un stack buffer pequeño puede permanecer como fast path:

```cpp
constexpr int SMALL_N = 64;
double small[SMALL_N * (SMALL_N + 1)];
```

pero para $N=256$ es preferible memoria preasignada por hilo.

## 4. Layout: no almacenar una matriz aumentada si no es necesario

La matriz aumentada mezcla:

```text
coeficientes A | rhs
```

Esto puede dificultar la vectorización y escribir más memoria de la necesaria. Mejor separar:

```cpp
double* A;
double* rhs;
double* pivots;
```

o usar una representación bloqueada:

```text
[A11 A12 | b1]
[A21 A22 | b2]
```

Ventajas:

- mejor localidad;
- RHS separado;
- posibilidad de usar kernels BLAS;
- menos movimientos durante pivotado;
- más fácil reutilizar la factorización.

Si hay múltiples RHS, usar un bloque `B` y resolver de forma conjunta:

$$
AX=B
$$

en vez de repetir el solve escalar.

## 5. Eliminar la matriz completa: operador matrix-free

La mejora de mayor impacto es representar el sistema como operador:

$$
y=A x
$$

sin materializar $A$.

```cpp
void apply_cayley_operator(
    const Vector& x,
    Vector& y,
    const CayleyState& state)
{
    // y = x - alpha * W(x)
}
```

Después usar un solver Krylov:

- CG si el operador es simétrico definido positivo;
- MINRES si es simétrico indefinido;
- GMRES si no es simétrico;
- BiCGSTAB cuando el coste de memoria sea prioritario.

El workspace pasa de $O(K^2)$ a varios vectores de $O(K)$, aunque GMRES sin restart puede volver a crecer a $O(mK)$.

Para una dimensión reducida $2K\le256$, una LU densa puede seguir siendo más rápida. Por eso hay que seleccionar según:

- número de RHS;
- número de solves por iteración;
- coste de formar $A$;
- condición;
- disponibilidad de BLAS-3;
- tamaño real de $K$.

No conviene imponer matrix-free si el sistema es pequeño y bien condicionado.

## 6. Explotar Woodbury y bajo rango

Si el operador tiene forma:

$$
A=A_0+UV^\top
$$

usar Sherman–Morrison–Woodbury:

$$
A^{-1}
=
A_0^{-1}
-
A_0^{-1}U
\left(I+V^\top A_0^{-1}U\right)^{-1}
V^\top A_0^{-1}
$$

Esto reduce el solve a:

1. aplicaciones de $A_0^{-1}$;
2. construcción de una matriz pequeña;
3. resolución de un sistema de rango reducido.

En variantes Stiefel y symplectic-Stiefel, la identidad de Sherman–Morrison–Woodbury se usa para reemplazar inversiones grandes por sistemas de tamaño proporcional al rango de la actualización.[^9_2]

Para un rango $r$, el coste puede pasar de:

$$
O(n^3)
$$

a algo más cercano a:

$$
O(nr^2+r^3)
$$

dependiendo de la estructura de $A_0$.

## 7. Reutilizar factorizaciones

Si el sistema lineal cambia poco entre iteraciones:

```text
A_t ≈ A_{t-1}
```

no refactorizar en cada paso. Mantener:

```cpp
struct FactorizationCache {
    Matrix LU;
    PivotVector piv;
    double reference_norm;
    bool valid;
};
```

Reutilizar si:

$$
\frac{\|A_t-A_{t-1}\|}{\|A_{t-1}\|}
<\tau_{\text{reuse}}
$$

Después, comprobar el residuo:

$$
r=b-A_tx
$$

Si el residuo supera el umbral:

- aplicar refinamiento;
- actualizar la factorización;
- cambiar a fallback robusto.

Esta estrategia puede tener más impacto que optimizar el allocator.

## 8. Refinamiento iterativo mixto

Una ruta SOTA es:

1. factorizar en precisión baja;
2. resolver inicialmente;
3. calcular el residual en precisión alta;
4. resolver una corrección usando la factorización existente;
5. actualizar $x$;
6. repetir.

$$
r_k=b-Ax_k
$$

$$
A\delta_k=r_k
$$

$$
x_{k+1}=x_k+\delta_k
$$

La aritmética de factorización puede usar `float32`, mientras que el residual se calcula en `float64` o mayor precisión. El objetivo es recuperar una solución cercana a la precisión alta con un coste menor.[^9_3][^9_4][^9_5]

Pseudocódigo:

```cpp
x = solve_low_precision(A, b);

for (int iter = 0; iter < max_refine; ++iter) {
    r = b - A * x;              // high precision
    if (relative_norm(r) < tol)
        break;

    delta = solve_using_existing_factors(r);
    x += delta;
}
```

Debe monitorizarse el fallo de refinamiento:

- mala condición;
- crecimiento del residual;
- corrección que deja de disminuir;
- pivotes inestables.

Si falla, pasar a `float64` completo o a un solver robusto.

## 9. Escalado y equilibrado

Antes del solve, aplicar equilibrado si las filas o columnas tienen escalas muy diferentes:

$$
\tilde A=D_r A D_c
$$

$$
\tilde b=D_r b
$$

Resolver:

$$
\tilde A\tilde x=\tilde b
$$

y recuperar:

$$
x=D_c\tilde x
$$

Esto mejora:

- estabilidad del pivotado;
- convergencia Krylov;
- éxito del refinamiento;
- predictibilidad de la ruta fast.

El escalado debe evitar crear nuevas asignaciones: los factores pueden vivir en arrays pequeños del workspace.

## 10. Pivoteado y determinismo

El pivoteado parcial puede seleccionar filas distintas si dos candidatos son casi iguales. Eso produce resultados numéricamente equivalentes pero no bitwise idénticos.

Para reproducibilidad:

```cpp
if (abs(candidate_a) > abs(candidate_b))
    choose a;
else if (abs(candidate_a) < abs(candidate_b))
    choose b;
else
    choose lowest row index;
```

Usar desempate por índice fijo. Si la aplicación no necesita bitwise reproducibilidad, puede usar el pivotado optimizado de BLAS.

Separar modos:

```text
FAST:
    pivotado estándar, FMA y vectorización

STABLE:
    pivotado determinista, residual monitorizado

REPRO:
    orden fijo, desempates deterministas, aritmética controlada
```


## 11. Control de ortogonalidad Stiefel

La retraction debe preservar:

$$
X^\top X=I
$$

Medir:

$$
e_{\text{orth}}=\|X^\top X-I\|_F
$$

Después de cada paso o cada cierto número de pasos:

```cpp
if (orthogonality_error(X) > tau_orth)
    corrective_reorthogonalization(X);
```

Posibles correcciones:

- QR;
- polar decomposition;
- Newton–Schulz para $(X^\top X)^{-1/2}$;
- SVD solo como fallback.


### Corrección polar

Si $X$ está cerca de Stiefel:

$$
X_{\text{new}}
=
X(X^\top X)^{-1/2}
$$

Se puede aproximar $(X^\top X)^{-1/2}$ con Newton–Schulz si el tamaño reducido lo permite. Esto puede ser más barato que una SVD completa, aunque requiere controlar convergencia.

### Estrategia híbrida

```text
Cayley barata en cada iteración
QR/polar cuando e_orth > τ
```

Esto limita la deriva sin pagar ortogonalización completa siempre.

## 12. Tolerancia del solve adaptada al paso

No tiene sentido resolver el sistema con tolerancia fija excesivamente estricta si el paso del optimizador es grande o el gradiente es ruidoso.

Usar:

$$
\tau_{\text{solve}}
=
\min(\tau_{\max},
C\cdot\| \text{step} \|)
$$

o una tolerancia ligada al error de ortogonalidad:

$$
\tau_{\text{solve}}
\le
C_{\text{orth}}\tau_{\text{orth}}
$$

La tolerancia debe ser suficientemente estricta para que el error del solve no domine el error de la retraction, pero no más.

## 13. Precondicionamiento

Para matrix-free Krylov, un precondicionador puede reducir drásticamente iteraciones:

- diagonal;
- block-diagonal;
- Jacobi escalado;
- factorización incompleta;
- aproximación de bajo rango;
- precondicionador reutilizado entre iteraciones.

Si $M\approx A$:

$$
M^{-1}Ax=M^{-1}b
$$

El precondicionador también debe vivir en el workspace persistente y reutilizarse cuando sea válido.

## 14. Detección automática de modo

La implementación puede decidir dinámicamente:

```text
si K <= K_small y solve_count bajo:
    LU densa en workspace persistente

si K <= K_medium y hay varios RHS:
    LU bloqueada/reutilizada

si estructura bajo rango:
    Woodbury

si operador barato y K grande:
    matrix-free Krylov

si condición alta:
    mixed precision + refinement o FP64
```

La selección debe basarse en benchmarks reales, no solo en complejidad asintótica.

## 15. Memoria por hilo y false sharing

El workspace por hilo debe estar separado en líneas de caché:

```cpp
struct alignas(64) ThreadWorkspace {
    ScratchArena arena;
    SolverStats stats;
    char padding[...];
};
```

No colocar contadores contiguos que todos los hilos actualicen:

```cpp
stats[tid].fallbacks++;
```

Si `stats[^9_0]` y `stats[^9_1]` comparten una línea, puede aparecer false sharing. El false sharing entre procesadores es una fuente conocida de mala escalabilidad en estructuras compartidas.[^9_6][^9_7]

Usar:

- padding;
- reducción local de estadísticas;
- agregación al final;
- escritura por hilo en bloques alejados.


## 16. NUMA

Para múltiples sockets:

```text
socket 0 → threads 0..T0 → workspaces 0..T0
socket 1 → threads T0..T1 → workspaces T0..T1
```

Inicializar cada workspace desde el hilo que lo usará:

```cpp
#pragma omp parallel
{
    int tid = omp_get_thread_num();
    touch_pages(workspaces[tid]);
}
```

No inicializar todo desde el hilo principal si se busca first-touch NUMA-local.

Las implementaciones modernas de alto rendimiento suelen asociar threads y working sets con su nodo NUMA para evitar accesos remotos.[^9_8]

## 17. Fallback robusto sin jitter

El fallback debe ser parte del plan de memoria:

```cpp
struct WorkspacePool {
    ScratchArena fast;
    ScratchArena overflow;
    std::atomic<uint64_t> overflow_count;
};
```

Pero no usar `std::atomic` en cada asignación del hot path. El contador debe ser local al hilo y combinarse después.

Si el tamaño excede la capacidad:

```cpp
if (required > fast.capacity()) {
    if (required <= overflow.capacity()) {
        use_overflow();
    } else {
        return Status::WorkspaceExceeded;
    }
}
```

Es preferible devolver un error controlado que hacer `malloc` imprevisible durante una iteración crítica.

## 18. Perfilado obligatorio

Para demostrar la mejora:

### Memoria

- allocations por iteración;
- bytes reservados;
- RSS;
- memoria por hilo;
- número de overflows;
- páginas remotas.


### Microarquitectura

- ciclos;
- instrucciones;
- IPC;
- L1/L2/L3 misses;
- branch misses;
- bandwidth;
- false sharing;
- vectorización.


### Álgebra

- residual;
- condición estimada;
- iteraciones;
- pivotes;
- error de ortogonalidad;
- refinamientos;
- retractions rechazadas.


### End-to-end

- tiempo por iteración;
- throughput;
- convergencia;
- calidad final;
- estabilidad entre ejecuciones.

Una implementación puede ser más rápida por solve y más lenta globalmente si aumenta el número de iteraciones del optimizador por peor precisión.

## 19. Diseño final recomendado

### Fast path

```text
workspace persistente por hilo
LU pequeña en memoria alineada
sin malloc/free
sin locks
FMA permitido
pivoteado optimizado
```


### Stable path

```text
workspace persistente
equilibrado
LU o Krylov
residual FP64
refinamiento
control de ortogonalidad
```


### Scientific path

```text
operador matrix-free o Woodbury
pivoteado determinista
reducción reproducible
residual de alta precisión
iterative refinement
QR/polar correctiva controlada
```


## Veredicto

v911 corrige el síntoma inmediato, pero el array fijo `256×384` no debería ser la solución principal. Para convertirlo en una solución SOTA:

1. mover el workspace del stack a una arena persistente por hilo;
2. eliminar `malloc/free`, `resize` y locks del hot path;
3. explotar Woodbury o estructura de bajo rango;
4. evitar materializar la matriz aumentada cuando el operador pueda aplicarse matrix-free;
5. reutilizar factorizaciones;
6. usar refinamiento mixto con residual en mayor precisión;
7. medir y controlar la ortogonalidad Stiefel;
8. hacer el fallback pre-reservado y observable;
9. aplicar first-touch y afinidad NUMA;
10. separar modos `Fast`, `Stable` y `Scientific`.

La arquitectura objetivo es:

$$
\boxed{
\text{workspace por hilo}
+
\text{solver estructurado}
+
\text{reutilización}
+
\text{refinamiento}
+
\text{corrección geométrica}
}
$$

El criterio de éxito no debe ser únicamente “ya no hay fragmentación del heap”, sino:

$$
\boxed{
\text{más throughput}
+
\text{misma o mejor convergencia}
+
\text{error de ortogonalidad controlado}
+
\text{latencia reproducible}
}
$$

<span style="display:none">[^9_10][^9_11][^9_12][^9_13][^9_14][^9_15][^9_16][^9_17][^9_18][^9_19][^9_9]</span>

<div align="center">⁂</div>

[^9_1]: https://ar5iv.labs.arxiv.org/html/2002.01113

[^9_2]: https://ar5iv.labs.arxiv.org/html/2211.09481

[^9_3]: https://www.osti.gov/servlets/purl/1872699

[^9_4]: https://www.osti.gov/servlets/purl/1825849

[^9_5]: https://arxiv.org/html/2405.18363v1

[^9_6]: https://www.openmp.org/wp-content/uploads/openmp-webinar-vanderPas-20210318.pdf

[^9_7]: https://docs.oracle.com/cd/E19059-01/stud.9/817-6703/6_tuning.html

[^9_8]: https://arxiv.org/html/2506.09198v2

[^9_9]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html

[^9_10]: https://www.jstage.jst.go.jp/article/ipsjjip/31/0/31_860/\_pdf

[^9_11]: https://www.mccormick.northwestern.edu/research/optimization-machine-learning-center/documents/presentation-slides/ay23/croci-slides.pdf

[^9_12]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7735315/

[^9_13]: https://www.arxiv.org/pdf/2408.13400v1.pdf

[^9_14]: https://optimization-online.org/wp-content/uploads/2016/09/5617.pdf

[^9_15]: https://ulopenaccess.com/papers/ULETE_V03I02/ULETE20260302_013.pdf

[^9_16]: https://solvax.readthedocs.io/en/latest/solvers/mixed_precision.html

[^9_17]: https://arxiv.org/pdf/2609.21039v1.pdf

[^9_18]: https://simplifycpp.org/download/book.php?id=17170

[^9_19]: https://dev.to/beefedai/designing-a-custom-arena-allocator-for-high-throughput-services-1hkk


---

# 5. Dangling Pointers en Mapeo de Memoria FFI Python (Brecha de Memoria / GC)evalua soluciones y mejoras sota

Falla: En polydim_v906_monolito.py, el argtype para la API Win32 CreateFileMappingA estaba declarado como c_char_p. En ciclos prolongados sin referencias fuertes de Python, el Garbage Collector está diseñado para purgar la cadena, lo que introduce el riesgo estadístico de segment faults o corrupción de páginas de memoria PMTP.
Estado (v911): Puntero congelado como c_void_p opaco y estricto.

El diagnóstico de v911 necesita una corrección importante: cambiar el `argtype` de `c_char_p` a `c_void_p` puede ocultar una conversión incorrecta, pero **no garantiza por sí solo la vida útil del buffer ni corrige el ownership del mapeo**.

Además, `ctypes` normalmente mantiene vivas las conversiones temporales durante la llamada síncrona. El riesgo real aparece cuando la API nativa **guarda el puntero para usarlo después**, o cuando Python conserva solo una dirección opaca sin mantener el objeto propietario. La documentación de `ctypes` distingue `c_char_p` como cadena C terminada en NUL y recomienda `POINTER(c_char)` para memoria binaria general.[^10_1]

## 1. Diagnóstico exacto

`CreateFileMappingA` tiene conceptualmente esta firma:

```cpp
HANDLE CreateFileMappingA(
    HANDLE                hFile,
    LPSECURITY_ATTRIBUTES lpFileMappingAttributes,
    DWORD                 flProtect,
    DWORD                 dwMaximumSizeHigh,
    DWORD                 dwMaximumSizeLow,
    LPCSTR                lpName
);
```

El último parámetro es:

```cpp
LPCSTR
```

Por tanto, para una llamada normal, `c_char_p` es el tipo semánticamente correcto:

```python
CreateFileMappingA.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_char_p,
]
```

Cambiarlo a:

```python
CreateFileMappingA.argtypes = [..., ctypes.c_void_p]
```

solo dice a `ctypes`:

> “acepta una dirección opaca”.

No transforma mágicamente un nombre Python en un buffer válido. Tampoco mantiene vivo el objeto subyacente. La documentación de `ctypes` deja claro que un puntero general a memoria binaria debería modelarse con `POINTER(c_char)` y que los objetos usados por código C deben mantenerse vivos mientras C pueda acceder a ellos.[^10_2][^10_1]

### Conclusión

v911 puede ser correcto **si el código pasa explícitamente un puntero estable y conserva su propietario**. Si solo cambió el tipo a `c_void_p`, la corrección está incompleta.

## 2. Tres problemas distintos

### A. Tipo ABI

¿El parámetro es realmente:

```text
const char*
```

o es:

```text
void*
```

Para `CreateFileMappingA`, es `const char*`.

### B. Vida útil

¿La función nativa usa el puntero solo durante la llamada o lo guarda?

- uso síncrono: basta mantenerlo durante la llamada;
- uso asíncrono: el objeto debe vivir hasta que C deje de usarlo.


### C. Ownership del handle

`CreateFileMappingA` devuelve un `HANDLE`, que debe cerrarse con `CloseHandle`. Las vistas obtenidas con `MapViewOfFile` deben liberarse con `UnmapViewOfFile`. Microsoft especifica que las vistas mantienen referencias internas al objeto de mapping y que para cerrarlo correctamente hay que desmapear todas las vistas y cerrar el handle.[^10_3]

Cambiar el `argtype` no resuelve fugas de handles ni vistas huérfanas.

## 3. Binding correcto para `ctypes`

Usar `use_last_error=True` y tipos Windows explícitos:

```python
import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreateFileMappingW.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,       # LPSECURITY_ATTRIBUTES
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPCWSTR,
]
kernel32.CreateFileMappingW.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.MapViewOfFile.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_size_t,
]
kernel32.MapViewOfFile.restype = ctypes.c_void_p

kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL
```

Para nombres nuevos, preferir `W` sobre `A`:

- `CreateFileMappingW` usa UTF-16;
- evita problemas de code page;
- permite nombres Unicode;
- evita conversiones ANSI implícitas.

Para un nombre ASCII fijo, `A` puede funcionar, pero no ofrece ventaja relevante en un wrapper moderno.

## 4. Mantener viva la cadena correctamente

### Opción recomendada: usar `W`

```python
name = "Global\\MyMapping"
handle = kernel32.CreateFileMappingW(
    wintypes.HANDLE(-1),
    None,
    PAGE_READWRITE,
    high,
    low,
    name,
)
```

`ctypes` realiza la conversión necesaria para la llamada. Esto es correcto si Windows consume el nombre de forma síncrona, como ocurre aquí.

### Opción `A` con buffer explícito

```python
name_buf = ctypes.create_string_buffer(
    b"Global\\MyMapping"
)

handle = kernel32.CreateFileMappingA(
    wintypes.HANDLE(-1),
    None,
    PAGE_READWRITE,
    high,
    low,
    ctypes.cast(name_buf, ctypes.c_char_p),
)
```

Aquí `name_buf` mantiene el almacenamiento y sigue vivo mientras exista la variable.

Si el puntero se guarda en una estructura o se entrega a una API asíncrona:

```python
class MappingRequest:
    def __init__(self, name: bytes):
        self.name_buf = ctypes.create_string_buffer(name)
        self.name_ptr = ctypes.cast(
            self.name_buf,
            ctypes.c_char_p
        )
```

La referencia `self.name_buf` es la garantía de vida útil. Guardar solo `self.name_ptr` o un entero con la dirección no basta.

## 5. Por qué `c_void_p` no es una solución completa

Este patrón es peligroso:

```python
raw = ctypes.c_char_p(b"name")
ptr = ctypes.cast(raw, ctypes.c_void_p)

# raw desaparece
native_call(ptr)
```

Aunque a veces funcione durante la llamada, la seguridad depende de detalles de temporales y ownership. Si el código nativo conserva `ptr`, queda un puntero sin propietario.

El patrón correcto es:

```python
raw = ctypes.create_string_buffer(b"name")
ptr = ctypes.cast(raw, ctypes.c_void_p)

request = NativeRequest(ptr)
request._keepalive = raw
```

La regla es:

$$
\boxed{
\text{cada puntero almacenado fuera de Python debe tener un owner Python explícito}
}
$$

## 6. Wrapper RAII en Python

El recurso principal es el `HANDLE`, no la cadena del nombre. Crear un wrapper que cierre automáticamente:

```python
class FileMapping:
    def __init__(self, size, name=None, protection=PAGE_READWRITE):
        self._handle = None
        self._view = None
        self._size = size
        self._name_keepalive = None

        high = (size >> 32) & 0xffffffff
        low = size & 0xffffffff

        if name is not None:
            self._name_keepalive = name

        h = kernel32.CreateFileMappingW(
            wintypes.HANDLE(-1),
            None,
            protection,
            high,
            low,
            name,
        )

        if not h:
            raise ctypes.WinError(ctypes.get_last_error())

        self._handle = h

    def map(self, access, size=0):
        p = kernel32.MapViewOfFile(
            self._handle,
            access,
            0,
            0,
            size,
        )

        if not p:
            err = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(err)

        self._view = p
        return p

    def unmap(self):
        if self._view is not None:
            if not kernel32.UnmapViewOfFile(self._view):
                raise ctypes.WinError(ctypes.get_last_error())
            self._view = None

    def close(self):
        self.unmap()

        if self._handle is not None:
            if not kernel32.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
```

Uso:

```python
with FileMapping(size=4096, name="Global\\Demo") as mapping:
    view = mapping.map(FILE_MAP_ALL_ACCESS, 4096)
    # usar view
```


### `__del__` no debe ser la única defensa

El recolector puede retrasar la destrucción y los ciclos pueden complicarla. `__del__` puede usarse como fallback defensivo, pero el contrato principal debe ser:

- context manager;
- método `close`;
- ownership explícito;
- cierre idempotente.


## 7. Manejo correcto de `GetLastError`

Configurar:

```python
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
```

y llamar inmediatamente:

```python
if not handle:
    raise ctypes.WinError(ctypes.get_last_error())
```

No hacer operaciones Python intermedias entre la llamada fallida y `get_last_error()`. De lo contrario, puede perderse el error relevante.

También distinguir:

- `CreateFileMapping` devuelve `NULL` en error;
- si abre un mapping existente, `GetLastError()` puede devolver `ERROR_ALREADY_EXISTS`;
- esto no es necesariamente un fallo.

```python
handle = CreateFileMappingW(...)
if not handle:
    raise WinError(get_last_error())

already_exists = (
    ctypes.get_last_error() == ERROR_ALREADY_EXISTS
)
```


## 8. Handles inválidos y tipos

No usar `c_int` para handles Windows de forma genérica. En 64 bits, un `HANDLE` es un puntero opaco y debe representarse con:

```python
wintypes.HANDLE
```

El `restype` debe estar correctamente definido:

```python
CreateFileMappingW.restype = wintypes.HANDLE
```

Si se omite `restype`, `ctypes` puede interpretar incorrectamente el valor retornado en procesos de 64 bits.

Para las vistas:

```python
MapViewOfFile.restype = ctypes.c_void_p
```

porque la vista es una dirección de memoria, no un `HANDLE`.

## 9. Vista mapeada: no mezclar puntero con buffer

`MapViewOfFile` devuelve una dirección. Para acceder desde Python:

```python
address = kernel32.MapViewOfFile(...)
if not address:
    raise ctypes.WinError(ctypes.get_last_error())

buffer_type = ctypes.c_ubyte * size
buffer = buffer_type.from_address(address)
```

Pero `buffer` no es necesariamente el owner del mapping. Debe mantenerse vivo el objeto `FileMapping` y desmapearlo antes de cerrar el handle.

Diseño correcto:

```python
class MappingView:
    def __init__(self, owner, address, size):
        self.owner = owner
        self.address = address
        self.size = size
        self.buffer = (
            ctypes.c_ubyte * size
        ).from_address(address)

    def close(self):
        self.owner.unmap()
        self.buffer = None
```

La dependencia debe ser:

```text
MappingView → FileMapping → HANDLE
```

No:

```text
MappingView → raw address
```


## 10. Lifetime graph explícito

Para evitar use-after-free, documentar el grafo:

```text
Python FileMapping
    ├── name buffer, si aplica
    ├── HANDLE
    └── MappingView
          ├── raw address
          └── ctypes buffer
```

Regla de destrucción:

1. detener consumidores;
2. liberar objetos Python que acceden a la vista;
3. `UnmapViewOfFile`;
4. `CloseHandle`;
5. liberar el buffer del nombre, si existe.

Nunca:

```text
CloseHandle
→ seguir usando view
```

Microsoft indica que el mapping object no queda completamente cerrado hasta que todas las vistas se liberan y el handle se cierra.[^10_3]

## 11. Si el nativo guarda el puntero

Si la API C guarda el nombre o cualquier buffer para uso posterior, `argtypes` no solucionan nada. Hay que modelar el ownership.

### Wrapper con keepalive

```python
class NativeRequest:
    def __init__(self, name: bytes):
        self.name = ctypes.create_string_buffer(name)
        self.ptr = ctypes.cast(self.name, ctypes.c_void_p)
        self.pending = True

    def complete(self):
        self.pending = False
        self.name = None
        self.ptr = None
```

La referencia se libera solo después de una señal fiable de que C terminó.

### Callback

Si C llama a Python después, mantener viva la función `CFUNCTYPE`:

```python
self._callback = CALLBACK(self._on_complete)
native_register(self._callback)
```

No:

```python
native_register(CALLBACK(self._on_complete))
```

La documentación de `ctypes` advierte explícitamente que los callbacks pueden ser recolectados si no se conserva una referencia, provocando un crash cuando C intente invocarlos.[^10_1]

## 12. CFFI como alternativa

Para wrappers FFI complejos, CFFI puede ofrecer una semántica de ownership más clara, pero también exige mantener vivo el objeto que posee la memoria. Su documentación advierte que un puntero casteado puede quedar colgando si se recolecta el objeto original que poseía el buffer.[^10_4]

Por tanto:

- `ctypes`: sencillo, adecuado para API Win32 sin callbacks complejos;
- `cffi`: mejor para declaraciones C grandes y ownership explícito;
- extensión CPython/Rust: mejor si se necesita un wrapper RAII fuerte, concurrencia o callbacks prolongados.

Cambiar de `ctypes` a CFFI no elimina automáticamente los dangling pointers.

## 13. No usar `cast` como sustituto del ownership

Este patrón solo cambia el tipo:

```python
ptr = ctypes.cast(obj, ctypes.c_void_p)
```

No crea una copia ni una relación de ownership. La documentación de CFFI describe el mismo principio: al castear un puntero, el objeto original sigue siendo quien posee la memoria y debe permanecer vivo.[^10_4]

Si se necesita una copia independiente:

```python
buf = ctypes.create_string_buffer(bytes_value)
```

La copia posee su propia memoria y puede mantenerse explícitamente.

## 14. Pruebas de lifetime

Un test básico debe forzar presión de GC entre la creación del buffer y el consumo:

```python
import gc

name = ctypes.create_string_buffer(b"Global\\Test")
ptr = ctypes.cast(name, ctypes.c_void_p)

for _ in range(10000):
    junk = [bytearray(4096) for _ in range(10)]
    gc.collect()

    # native code debe seguir usando ptr de forma válida
```

Para APIs asíncronas:

1. crear buffer;
2. registrar puntero;
3. eliminar todas las referencias salvo el keepalive;
4. forzar `gc.collect()`;
5. ejecutar el callback;
6. completar;
7. liberar keepalive;
8. verificar que no hay acceso posterior.

Usar sanitizers donde sea posible:

- Application Verifier;
- PageHeap/GFlags;
- AddressSanitizer para la parte nativa;
- WinDbg;
- tests de stress multihilo;
- WER crash dumps.


## 15. Tests de handles y vistas

Comprobar:

- fallo de `CreateFileMapping`;
- `ERROR_ALREADY_EXISTS`;
- fallo de `MapViewOfFile`;
- doble `close`;
- `unmap` sin vista;
- `close` con vista activa;
- excepción durante el uso;
- destrucción por context manager;
- proceso que termina sin fugas;
- tamaño cero;
- tamaños de 32 y 64 bits;
- nombres Unicode;
- nombres nulos;
- mappings anónimos.

El wrapper debe hacer que estas secuencias sean seguras:

```python
m.close()
m.close()
```

```python
m.unmap()
m.close()
```

y debe rechazar:

```python
view.buffer[^10_0]  # después de unmap
```

con un estado controlado, no con memoria inválida silenciosa.

## 16. Verificación ABI

Construir un pequeño programa C de referencia:

```c
HANDLE make_mapping(const wchar_t *name, SIZE_T size);
```

y comparar:

- `sizeof(HANDLE)`;
- valores de retorno;
- offsets;
- calling convention;
- Unicode/ANSI;
- arquitectura x64/ARM64;
- error codes.

En Windows x64, la calling convention es uniforme en gran medida, pero no se debe asumir lo mismo para todas las arquitecturas o funciones auxiliares.

También revisar que `ctypes` no esté interpretando:

- `SIZE_T` como `c_uint32`;
- `HANDLE` como `c_int`;
- `DWORD` como `c_long`;
- punteros de 64 bits como enteros de 32 bits.


## 17. Política de seguridad

Un nombre de mapping global como:

```text
Global\MyMapping
```

puede tener implicaciones de seguridad y permisos. Si se usan atributos de seguridad:

```cpp
SECURITY_ATTRIBUTES
```

deben declararse con `ctypes.Structure` correcta y mantenerse vivos durante la llamada si se requiere.

También validar:

- input size;
- overflow al separar `high/low`;
- permisos;
- nombres controlados por usuario;
- colisiones de nombres;
- acceso entre sesiones;
- cierre de handles heredables.

El problema de lifetime no debe ocultar problemas de ACL o de namespace.

## 18. Mejor diseño: encapsular en una extensión RAII

Si el mapping vive mucho tiempo o se comparte con código C/C++, una extensión nativa suele ser más segura:

```text
Python object
    owns HANDLE
    owns mapped view
    owns name/storage
    tp_dealloc performs safe cleanup
```

En Rust/PyO3:

```text
struct Mapping {
    handle: OwnedHandle,
    view: NonNull<u8>,
    len: usize,
    name: Option<Vec<u16>>,
}
```

La ventaja es que el ownership queda expresado en el tipo y el destructor puede hacer:

```text
drop view
CloseHandle
drop name
```

Pero incluso allí hay que controlar objetos Python que exporten buffers: no se puede desmapear mientras exista un `memoryview` activo, salvo que se imponga una política de bloqueo de buffer.

## 19. Veredicto sobre v911

v911 es **insuficiente si solo cambió**:

```python
argtype = c_char_p
```

por:

```python
argtype = c_void_p
```

La solución correcta debe incluir:

1. firma ABI exacta;
2. preferencia por `CreateFileMappingW`;
3. buffer explícito cuando se requiera una dirección estable;
4. referencia keepalive al owner;
5. wrapper RAII/context manager;
6. `UnmapViewOfFile` antes de `CloseHandle`;
7. `use_last_error=True`;
8. tipos correctos para handles y tamaños;
9. pruebas de GC, callbacks y concurrencia;
10. política clara para vistas activas.

La arquitectura recomendada es:

$$
\boxed{
\text{tipo ABI correcto}
+
\text{owner explícito}
+
\text{keepalive}
+
\text{RAII}
+
\text{lifetime de vista}
+
\text{cierre determinista}
}
$$

El cambio a `c_void_p` puede ser útil para un puntero opaco, pero no constituye por sí mismo una corrección de memoria. En este caso, la mejora SOTA no es “congelar el puntero”: es **hacer que el puntero tenga un propietario verificable durante toda la vida que el código nativo pueda observarlo**.

<span style="display:none">[^10_10][^10_11][^10_12][^10_13][^10_14][^10_15][^10_5][^10_6][^10_7][^10_8][^10_9]</span>

<div align="center">⁂</div>

[^10_1]: https://docs.python.org/3/library/ctypes.html

[^10_2]: https://runebook.dev/en/articles/python/library/ctypes/ctypes.\_CData.\_objects

[^10_3]: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createfilemappinga

[^10_4]: https://cffi.readthedocs.io/en/latest/using.html

[^10_5]: https://docs.python.org/ja/3.7/library/ctypes.html

[^10_6]: https://docs.python.org/ja/3.6/library/ctypes.html

[^10_7]: https://www.labri.fr/perso/betrema/winnt/manamemo.html

[^10_8]: https://algomaster.io/learn/python/ctypes

[^10_9]: https://microsoft.github.io/windows-docs-rs/doc/windows/Win32/System/Memory/fn.CreateFileMappingA.html

[^10_10]: https://runebook.dev/en/articles/python/library/ctypes/ctypes.cast

[^10_11]: https://fossies.org/linux/Python/Modules/\_ctypes/callbacks.c

[^10_12]: http://fmgroup.polito.it/quer/teaching/sdp/lucidi/u04-windows/u04s07-memoryMapping.pdf

[^10_13]: https://documentation.help/Python-v2.7.2/ctypes.html

[^10_14]: https://flylib.com/books/en/4.419.1.116/1/

[^10_15]: https://wiki.python.org/python/ctypes.html


---

# Profundiza soluciones y mejoras sota

La brecha debe tratarse como un problema de **ownership y protocolo de vida útil**, no como un simple problema de `argtypes`. La mejora SOTA consiste en garantizar simultáneamente:

$$
\boxed{
\text{ABI correcto}
+
\text{owner explícito}
+
\text{lifetime del buffer}
+
\text{lifetime del HANDLE}
+
\text{lifetime de la vista}
+
\text{cierre determinista}
}
$$

La documentación de `ctypes` indica que las referencias a objetos usados por código extranjero deben durar tanto como su uso en C; también expone `_objects` como mecanismo interno para conservar objetos necesarios para mantener válido un bloque de memoria.[^11_1][^11_2]

## 1. Corrección del diagnóstico v911

La afirmación:

> “el Garbage Collector purga la cadena”

es demasiado simplificada para CPython. En una llamada síncrona normal, `ctypes` suele mantener vivos los temporales durante la invocación. El riesgo real aparece cuando:

- C almacena un puntero para usarlo después;
- Python guarda solo una dirección numérica;
- un buffer mapeado se desmapea mientras existe una vista;
- se cierra el `HANDLE` antes de liberar vistas;
- un callback queda sin referencia;
- una estructura contiene punteros a objetos temporales;
- un wrapper nativo no modela ownership.

Por tanto, cambiar:

```python
c_char_p
```

por:

```python
c_void_p
```

no es suficiente. Incluso puede empeorar la seguridad al eliminar comprobaciones semánticas de tipo.

Para `CreateFileMappingA`, el parámetro `lpName` es conceptualmente `LPCSTR`; el binding correcto debe conservar ese significado. Para código nuevo, `CreateFileMappingW` suele ser preferible por Unicode.

## 2. Regla de ownership

Cada puntero que atraviesa la frontera FFI debe clasificarse:


| Puntero | Propietario | Duración mínima |
| :-- | :-- | :-- |
| Nombre de mapping síncrono | Python temporal controlado | Durante la llamada |
| Nombre retenido por C | Wrapper Python | Hasta callback/finalización |
| Vista de `MapViewOfFile` | Mapping object | Hasta `UnmapViewOfFile` |
| `HANDLE` | Wrapper RAII | Hasta `CloseHandle` |
| Callback | Wrapper Python | Mientras C pueda invocarlo |
| Buffer exportado | Objeto exporter | Hasta `PyBuffer_Release` |

La regla fundamental es:

$$
\text{lifetime(owner)}\ge\text{lifetime(pointer observable por C)}
$$

## 3. API pública segura

No exponer punteros crudos como API principal:

```python
address = mapping.map()
```

Es mejor devolver un objeto `MappingView` que conserve al mapping:

```python
view = mapping.view()
```

Relación de ownership:

```text
MappingView
    └── fuerte referencia a FileMapping
          ├── HANDLE
          ├── nombre keepalive
          └── estado de cierre
```

Así, mientras exista `view`, el mapping no puede cerrarse accidentalmente.

### Invariante

```text
view exists => mapping handle valid
mapping closed => no active views
```

Si se necesita permitir `close()` explícito mientras hay vistas, debe:

- rechazar el cierre;
- diferirlo;
- o invalidar vistas de forma controlada.

La opción más segura es rechazar:

```python
if self._active_views:
    raise RuntimeError("active mapped views")
```


## 4. Máquina de estados

Implementar un estado explícito:

```python
from enum import Enum, auto

class State(Enum):
    OPEN = auto()
    MAPPED = auto()
    CLOSED = auto()
```

Transiciones válidas:

```text
OPEN   -> MAPPED
MAPPED -> OPEN
OPEN   -> CLOSED
```

Transiciones inválidas:

```text
CLOSED -> MAPPED
CLOSED -> OPEN
OPEN con vista activa -> CLOSED
```

Una implementación mínima:

```python
class FileMapping:
    def __init__(self, handle, size, name_keepalive=None):
        self._handle = handle
        self._size = size
        self._name_keepalive = name_keepalive
        self._views = 0
        self._closed = False

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("mapping is closed")

    def close(self):
        if self._closed:
            return

        if self._views:
            raise RuntimeError("active mapped views")

        if not kernel32.CloseHandle(self._handle):
            raise ctypes.WinError(ctypes.get_last_error())

        self._handle = None
        self._name_keepalive = None
        self._closed = True
```


## 5. Vista con ownership fuerte

```python
class MappingView:
    def __init__(self, owner, address, size):
        self._owner = owner
        self._address = address
        self._size = size
        self._closed = False
        self._buffer = (ctypes.c_ubyte * size).from_address(address)

        owner._views += 1

    @property
    def buffer(self):
        if self._closed:
            raise RuntimeError("view is closed")
        return self._buffer

    def close(self):
        if self._closed:
            return

        ok = kernel32.UnmapViewOfFile(
            ctypes.c_void_p(self._address)
        )

        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

        self._buffer = None
        self._address = None
        self._closed = True
        self._owner._views -= 1
        self._owner = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
```

El orden seguro es:

```text
view.close()
→ UnmapViewOfFile
→ liberar buffer Python
→ decrement active_views
→ mapping.close()
→ CloseHandle
```

Microsoft documenta que el objeto de mapping mantiene referencias internas mientras existan vistas; por eso no debe tratarse el `HANDLE` como único recurso.[^11_3]

## 6. Exportar a NumPy o `memoryview`

Aquí aparece una segunda capa de lifetime. Si se construye un `memoryview` sobre la vista mapeada:

```python
mv = memoryview(view.buffer)
```

no se debe permitir:

```python
view.close()
```

mientras `mv` siga activo.

El protocolo de buffers exige que el exporter mantenga válida la memoria hasta que el consumidor libere la vista. PEP 3118 establece que el exporter debe conservar la memoria hasta `bf_releasebuffer`; el consumidor debe llamar a `PyBuffer_Release` cuando termina.[^11_4][^11_5]

### Diseño robusto

```python
class MappingView:
    def __init__(...):
        self._exports = 0

    def acquire_buffer(self):
        if self._closed:
            raise RuntimeError("closed")
        self._exports += 1
        return BufferLease(self)

    def _release_buffer(self):
        self._exports -= 1

    def close(self):
        if self._exports:
            raise BufferError("active exported buffers")
        ...
```

Si se implementa un tipo C extension que exporta `Py_buffer`, su `bf_releasebuffer` debe liberar el lease. Un `memoryview` simple creado desde `ctypes` no siempre ofrece todo el control necesario para una política de cierre estricta; para garantías fuertes conviene una extensión nativa.

## 7. `ctypes.from_buffer` y referencias ocultas

`ctypes` puede conservar referencias internas cuando se construyen objetos mediante `from_buffer`; `_objects` puede contener un `memoryview` o referencias relacionadas. La documentación indica que `_objects` es interno y no debe modificarse manualmente.[^11_2][^11_6]

No usar:

```python
obj._objects["keepalive"] = owner
```

Eso es frágil y no forma parte de una API de ownership pública.

Usar campos explícitos:

```python
obj._owner = owner
obj._keepalive = buffer
```

o un wrapper dedicado que controle la vida útil.

## 8. Nombres: `W` frente a `A`

### Recomendado

```python
CreateFileMappingW.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPCWSTR,
]
```

Usar:

```python
name = "Global\\TensorMap"
```


### Si se mantiene `A`

```python
name_buf = ctypes.create_string_buffer(
    name.encode("ascii") + b"\0"
)

CreateFileMappingA(
    ...,
    ctypes.cast(name_buf, ctypes.c_char_p),
)
```

No pasar arbitrariamente:

```python
ctypes.c_void_p(id(name))
```

ni interpretar `id()` como una dirección C válida para una cadena. El objeto Python debe ser el owner real del almacenamiento.

## 9. Callbacks y operaciones asíncronas

Si el código nativo conserva un puntero o ejecuta un callback posteriormente, el wrapper debe tener un objeto de operación pendiente:

```python
class PendingMappingOp:
    def __init__(self, name):
        self.name_buf = ctypes.create_string_buffer(name)
        self.callback = CALLBACK(self._complete)
        self.done = False

    def _complete(self, status):
        self.done = True
        self.name_buf = None
        self.callback = None
```

El callback debe permanecer vivo mientras C pueda invocarlo. La documentación de `ctypes` exige conservar una referencia explícita al callback durante todo ese periodo.[^11_7][^11_8]

En concurrencia:

- proteger el cambio `pending → done`;
- no liberar el buffer en un hilo mientras C puede leerlo;
- tener un protocolo de cancelación;
- hacer `join` o esperar confirmación antes de liberar.

El GC de Python no conoce automáticamente la vida útil que una biblioteca C atribuye a un puntero.

## 10. Cancellation y shutdown seguro

La secuencia de apagado debe ser:

1. impedir nuevas operaciones;
2. cancelar o drenar operaciones pendientes;
3. esperar callbacks;
4. liberar buffers retenidos;
5. desmapear vistas;
6. cerrar handles;
7. destruir el wrapper.

Nunca cerrar el proceso o el mapping mientras una operación nativa pueda estar en vuelo.

Una máquina de estados más completa:

```text
NEW
OPEN
MAPPED
CLOSING
CLOSED
FAILED
```

La transición `CLOSING` evita carreras entre:

```text
close()
```

y:

```text
callback()
```


## 11. Handle duplicado y procesos

Si el mapping se comparte entre procesos:

- el nombre no sustituye la gestión de handles;
- cada proceso debe cerrar su propio handle;
- la vista de cada proceso debe desmapearse localmente;
- no enviar direcciones virtuales entre procesos;
- usar offsets y tamaños, no punteros.

Una dirección devuelta por `MapViewOfFile` en un proceso no es válida en otro. Solo el `HANDLE` duplicado o el nombre permite abrir el mismo objeto.

## 12. Validación ABI automatizada

Crear pruebas que comprueben:

```python
assert ctypes.sizeof(wintypes.HANDLE) == ctypes.sizeof(ctypes.c_void_p)
assert ctypes.sizeof(ctypes.c_size_t) == pointer_size
```

Además:

- probar Python de 32 y 64 bits;
- Windows x64 y ARM64 si aplica;
- comprobar `restype` de cada función;
- verificar `CreateFileMappingW` con tamaños mayores de 4 GiB;
- probar `dwMaximumSizeHigh/Low`.

Para un tamaño `size`:

```python
if size < 0 or size > 0xffffffffffffffff:
    raise ValueError("invalid size")

high = (size >> 32) & 0xffffffff
low  = size & 0xffffffff
```

No truncar silenciosamente a `DWORD`.

## 13. Tests de uso después de liberar

Añadir tests negativos explícitos:

```python
with FileMapping(...) as m:
    with m.view(...) as v:
        ...
    assert_raises(RuntimeError, lambda: v.buffer)
```

Y:

```python
v = m.view(...)
assert_raises(RuntimeError, m.close)
v.close()
m.close()
```

Para buffers exportados:

```python
v = m.view(...)
mv = v.memoryview()

assert_raises(BufferError, v.close)

mv.release()
v.close()
```

Si la implementación no puede detectar consumidores externos, debe documentar que `close()` requiere que el usuario libere primero los `memoryview`.

## 14. Stress de GC y memoria

El test debe someter a presión el ciclo de vida, no solo invocar una vez:

```python
for iteration in range(100_000):
    with FileMapping(...) as m:
        with m.view(...) as v:
            write_and_read(v)

    if iteration % 100 == 0:
        gc.collect()
```

Variantes:

- crear y destruir nombres;
- forzar excepciones;
- ejecutar varios hilos;
- lanzar callbacks retrasados;
- destruir referencias en orden aleatorio;
- abrir mappings existentes;
- mapear y desmapear repetidamente;
- usar tamaños pequeños y grandes.

Medir:

- handles abiertos antes/después;
- vistas activas;
- RSS;
- errores de `CloseHandle`;
- crashes;
- use-after-free con PageHeap/ASan.


## 15. Herramientas de detección

Para la parte nativa:

- Application Verifier;
- PageHeap mediante GFlags;
- WinDbg;
- AddressSanitizer compatible con MSVC/Clang;
- dumps de Windows Error Reporting.

Para Python:

- `faulthandler`;
- `tracemalloc` para fugas Python;
- contador explícito de handles/vistas;
- tests con `gc.collect()`;
- logging de estados y thread IDs.

`tracemalloc` no detecta una fuga de handles Win32, por lo que debe combinarse con instrumentación nativa o consultas del sistema.

## 16. Alternativa SOTA: extensión nativa con buffer protocol

Para exponer una vista mmap de larga duración a NumPy o Python, el diseño más fuerte es una extensión C/C++ o Rust que implemente:

- objeto owner;
- destructor seguro;
- `bf_getbuffer`;
- `bf_releasebuffer`;
- contador de exports;
- bloqueo de `unmap` mientras hay buffers activos;
- `close()` idempotente;
- excepción clara si se cierra con consumidores activos.

El contrato sería:

```text
getbuffer:
    increment exports
    keep mapping alive

releasebuffer:
    decrement exports

close:
    reject if exports > 0
    unmap
    close handle
```

Esto sigue el contrato del buffer protocol, que exige mantener válida la memoria hasta liberar el buffer.[^11_5][^11_4]

## 17. Seguridad frente a errores parciales

Cada paso debe tener rollback:

```python
handle = create_mapping()
try:
    address = map_view(handle)
except:
    close_handle(handle)
    raise
```

Si se construye un `memoryview` y falla una validación posterior:

```python
try:
    view = create_view(...)
    validate_layout(view)
except:
    release_view()
    raise
```

Nunca dejar un `HANDLE` parcialmente inicializado en un objeto que luego `__del__` no pueda distinguir de un handle válido.

Usar `None` como estado cerrado:

```python
self._handle = None
self._address = None
```

y validar antes de operar.

## 18. Política de `__del__`

`__del__` debe ser un último recurso:

```python
def __del__(self):
    try:
        self.close()
    except Exception:
        pass
```

Pero no se debe depender de él para sincronización. En intérpretes alternativos, ciclos, shutdown del proceso o callbacks pendientes, el comportamiento puede no ser el esperado.

El contrato público debe ser:

```python
with Mapping(...) as m:
    ...
```

o:

```python
m.close()
```

con `weakref.finalize` como respaldo adicional, no como mecanismo principal.

## 19. Diseño final recomendado

### Nivel mínimo

- mantener `c_char_p` para `LPCSTR` o usar `LPCWSTR` para `W`;
- `use_last_error=True`;
- `HANDLE` y `SIZE_T` correctos;
- keepalive explícito;
- `CloseHandle` e `UnmapViewOfFile`.


### Nivel producción

- wrapper RAII/context manager;
- `MappingView` que retenga al owner;
- máquina de estados;
- contador de vistas y exports;
- callbacks retenidos;
- tests de GC y errores parciales;
- no exponer punteros crudos.


### Nivel científico/SOTA

- extensión nativa con buffer protocol;
- lease de buffers;
- cierre bloqueado mientras existan exports;
- cancelación y shutdown coordinados;
- soporte 32/64-bit y Unicode;
- instrumentación de handles;
- stress con PageHeap/ASan;
- API que diferencia ownership, borrowing y transferencia.


## Veredicto

v911 es una dirección correcta solo si “puntero congelado” significa realmente:

```text
puntero opaco
+ buffer owner conservado
+ lifetime validado
+ handle/view RAII
```

Si solo se sustituyó `c_char_p` por `c_void_p`, la vulnerabilidad no queda demostrablemente cerrada.

La solución SOTA es:

$$
\boxed{
\text{binding ABI fiel}
+
\text{ownership explícito}
+
\text{keepalive verificable}
+
\text{buffer protocol correcto}
+
\text{lifetime de HANDLE/view}
+
\text{shutdown coordinado}
}
$$

La corrección esencial no es hacer el puntero “opaco”, sino impedir que exista cualquier dirección que sobreviva a su propietario o cualquier vista que sobreviva al mapping que la respalda.

<span style="display:none">[^11_10][^11_11][^11_12][^11_13][^11_14][^11_15][^11_16][^11_9]</span>

<div align="center">⁂</div>

[^11_1]: https://docs.python.org/zh-cn/3.12/library/ctypes.html

[^11_2]: https://github.com/python/cpython/blob/3.11/Doc/library/ctypes.rst

[^11_3]: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createfilemappinga

[^11_4]: https://docs.python.org/3/c-api/buffer.html

[^11_5]: https://github.com/python/peps/blob/main/peps/pep-3118.rst

[^11_6]: https://github.com/python/cpython/issues/132177

[^11_7]: https://docs.python.org/3/library/ctypes.html

[^11_8]: https://svn.python.org/projects/ctypes/branches/LoadLibrary_branch/ctypes/docs/manual/manual.html

[^11_9]: https://latest2all.com/tutorial/advanced-ebpf-xdp-packet-filtering-and-paxos-consensus-gil-memory-model.html

[^11_10]: https://latest2all.com/tutorial/advanced-csp-channel-buffers-and-fat-pointers-csp-channel-backpressure.html

[^11_11]: https://latest2all.com/tutorial/advanced-coroutine-state-machines-and-fat-pointers-coroutine-frame-layout.html

[^11_12]: https://latest2all.com/tutorial/advanced-linear-types-for-resource-management-and-region-core-concepts.html

[^11_13]: https://latest2all.com/tutorial/advanced-michael-scott-queues-and-backpressure-in-reactive-lock-free-queue.html

[^11_14]: https://wiki.python.org/moin/ctypes.html

[^11_15]: https://docs.python.org/ja/3.7/library/ctypes.html

[^11_16]: https://wiki.python.org/python/ctypes.html


---

# 6. Filtración de Telemetría Cruda en CliffordNet (Bug de Monitoreo)evalua soluciones y mejoras sota

Falla: En polydim_cpp_cliffordnet_bivector_interact, la telemetría acumulativa de total_energy sumaba la norma euclidiana del bivector antes del escalado restrictivo LASSQ. Esto no rompe el tensor interno pero devuelve al orquestador niveles de energía ilegales que no respetan el teorema de subvariedad SD−1S^{D-1}SD−1.
Estado (v911): Parche pendiente o aceptado como "Raw Metric Output" dependiendo de la convención de análisis del Swarm.

El problema no es simplemente “telemetría cruda”, sino una **inconsistencia de contrato métrico**: el tensor interno puede estar correctamente escalado, mientras `total_energy` reporta una magnitud calculada en otro espacio, otra escala o incluso otra convención de norma.

La solución SOTA es separar explícitamente:

$$
\boxed{
\text{magnitud interna}
\neq
\text{telemetría raw}
\neq
\text{telemetría métrica}
\neq
\text{invariante normalizada}
}
$$

y no permitir que un escalar ambiguo llamado `total_energy` atraviese el orquestador.

## 1. Evaluación del fallo v911

La secuencia actual parece ser:

```text
bivector
   ↓
norma euclidiana cruda
   ↓
total_energy += norm_raw
   ↓
escalado restrictivo LASSQ
   ↓
tensor interno válido
```

Esto genera dos resultados distintos:

$$
E_{\text{raw}}
=
\sum_t \|B_t\|_{\text{Euclidiana}}
$$

frente a:

$$
E_{\text{metric}}
=
\sum_t \|\mathcal{P}(B_t)\|_{g}
$$

donde $\mathcal{P}$ representa el escalado restrictivo y $g$ la métrica declarada.

Si el orquestador interpreta `total_energy` como energía de una subvariedad $S^{D-1}$, el valor crudo puede ser ilegal o incomparable entre iteraciones.

La documentación geométrica estándar define la norma de un vector tangente mediante la métrica riemanniana:

$$
\|v\|_x=\sqrt{g_x(v,v)}
$$

y la esfera unitaria hereda su métrica del embedding euclídeo.[^12_1][^12_2][^12_3]

Pero un bivector no debe normalizarse automáticamente con la norma de un vector. Su métrica depende de la convención exterior/Clifford adoptada.

## 2. Primer problema: “energía” no debe ser norma

Si:

$$
\|B\|
$$

es una norma, entonces la energía física o geométrica suele ser:

$$
E=\frac12\|B\|^2
$$

No son intercambiables:


| Nombre | Fórmula | Propiedad |
| :-- | :-- | :-- |
| Magnitud | $\|B\|$ | escala lineal |
| Energía | $\frac12\|B\|^2$ | escala cuadrática |
| Energía acumulada | $\sum_t \frac12\|B_t\|^2$ | suma de contribuciones |
| Norma acumulada | $\sum_t\|B_t\|$ | longitud/variación total |
| RMS | $\sqrt{\frac1N\sum_i B_i^2}$ | magnitud promedio |

Si el campo se llama `total_energy` pero suma normas:

```cpp
total_energy += norm;
```

hay una inconsistencia semántica aunque el cálculo numérico sea perfecto.

Debe decidirse una convención:

```cpp
metric_norm += norm;
metric_energy += 0.5 * norm * norm;
```

y reportar ambas con nombres inequívocos.

## 3. Segundo problema: qué significa $S^{D-1}$

La afirmación “respetar el teorema de subvariedad $S^{D-1}$” requiere precisión. Para un vector:

$$
x\in S^{D-1}
\iff
\|x\|_2=1
$$

Pero un bivector:

$$
B=\sum_{i<j}B_{ij}e_i\wedge e_j
$$

vive en el espacio exterior $\Lambda^2(\mathbb{R}^D)$, cuya dimensión es:

$$
\binom{D}{2}
$$

El conjunto de bivectores unitarios:

$$
\{B:\|B\|=1\}
$$

es una esfera en $\Lambda^2(\mathbb{R}^D)$, pero no necesariamente representa una subvariedad físicamente válida de bivectores simples. Los bivectores simples además cumplen:

$$
B\wedge B=0
$$

en el caso apropiado, y forman la variedad de Grassmann correspondiente, no simplemente una esfera.

Por tanto, hay que separar:

1. **norma unitaria del embedding**;
2. **bivector simple**;
3. **bivector generado por un rotor**;
4. **estado Clifford normalizado**;
5. **métrica restrictiva del modelo**.

El nombre $S^{D-1}$ no basta para definir la energía legal.

## 4. Tercer problema: métrica del bivector

Para una base ortonormal euclídea, la norma canónica de:

$$
B=\sum_{i<j} B_{ij}e_i\wedge e_j
$$

puede ser:

$$
\|B\|^2=\sum_{i<j}B_{ij}^2
$$

o, según la convención matricial antisymmetric:

$$
\|B\|^2
=
\frac12\sum_{i,j}B_{ij}^2
$$

El factor $1/2$ evita contar dos veces los pares $(i,j)$ y $(j,i)$.

Si CliffordNet utiliza una métrica $G$:

$$
\|B\|_G^2 = b^\top G b
$$

donde $b$ es el vector de coordenadas independientes del bivector. La telemetría debe usar la misma métrica que el tensor interno, no una norma euclídea implícita.

Una API robusta debe exigir una convención:

```cpp
enum class BivectorMetric {
    IndependentWedgeCoordinates,
    AntisymmetricMatrixHalfFrobenius,
    CliffordQuadraticForm
};
```


## 5. Solución principal: telemetría después de la proyección

Si el tensor interno se escala mediante una transformación restrictiva:

$$
\widetilde B=\mathcal{P}(B)
$$

la telemetría métrica debe calcularse sobre $\widetilde B$:

$$
E_{\text{metric}}
=
\frac12
\|\widetilde B\|_g^2
$$

No sobre $B$ antes de la proyección.

La secuencia correcta:

```text
raw bivector
    ↓
validación finita
    ↓
proyección/restricción
    ↓
normalización estable LASSQ
    ↓
tensor válido
    ↓
norma métrica
    ↓
energía métrica
    ↓
telemetría
```

La salida raw puede conservarse, pero debe etiquetarse:

```text
raw_norm
raw_energy
projected_norm
metric_energy
constraint_residual
```

No reutilizar `total_energy` para todas ellas.

## 6. Dos telemetrías compatibles

### Canal raw

Mide la magnitud antes de la restricción:

$$
E_{\text{raw}}
=
\frac12\|B\|_{\text{raw}}^2
$$

Útil para:

- detectar outliers;
- diagnosticar saturación;
- estudiar la intensidad de entrada;
- monitorizar distribución de activaciones.

No debe usarse como energía intrínseca.

### Canal métrico

Mide el estado válido:

$$
E_{\text{metric}}
=
\frac12\|\widetilde B\|_g^2
$$

Útil para:

- control del optimizador;
- invariantes;
- alarmas del orquestador;
- comparación entre ejecuciones;
- leyes de conservación.

La solución v911 puede aceptar ambos, pero con tipos y nombres distintos.

## 7. Tipos fuertes para impedir mezclas

En C++:

```cpp
struct RawNorm {
    double value;
};

struct ProjectedNorm {
    double value;
};

struct MetricEnergy {
    double value;
};

struct ConstraintResidual {
    double value;
};
```

No permitir:

```cpp
double total_energy;
```

como interfaz universal.

Mejor:

```cpp
struct Telemetry {
    RawNorm raw_norm;
    MetricEnergy metric_energy;
    ConstraintResidual sphere_residual;
    bool finite;
};
```

O usar unidades fuertes:

```cpp
struct Energy {
    double joules_or_model_units;
};

struct Norm {
    double value;
};
```

La ventaja es que el compilador impide sumar accidentalmente una norma a una energía.

## 8. LASSQ no debe confundirse con normalización

LASSQ representa una suma de cuadrados de forma escalada:

$$
(\text{scale})^2\cdot\text{sumsq}
=
\sum_i x_i^2
$$

y evita overflow/underflow durante la acumulación.[^12_4][^12_5]

Pero LASSQ no define por sí mismo:

- la métrica;
- la restricción;
- la energía;
- la proyección;
- la normalización final.

Una implementación correcta:

```cpp
LassqState s;
for (double x : bivector)
    s.update(x);

double norm = s.norm();
double scale = 1.0 / max(norm, eps);
```

Si el objeto debe pertenecer a una esfera unitaria:

```cpp
B_projected[i] *= scale;
```

Después:

```cpp
double constrained_norm = stable_metric_norm(B_projected);
double metric_energy = 0.5 * constrained_norm * constrained_norm;
```

El orden importa. El valor de `scale` no debe publicarse como energía.

## 9. Error de restricción como telemetría principal

Para una esfera:

$$
r_S=|\|x\|^2-1|
$$

Para un bivector normalizado:

$$
r_B=|\|B\|_G^2-1|
$$

Para una restricción de simplicidad:

$$
r_{\text{simple}}=\|B\wedge B\|
$$

Para una condición Clifford específica:

$$
r_{\text{Clifford}}
=
\|\Phi(B)\|
$$

El orquestador necesita estos residuos, no inferirlos indirectamente a partir de `total_energy`.

```cpp
struct ConstraintDiagnostics {
    double sphere_residual;
    double bivector_norm_residual;
    double simplicity_residual;
    double finite_mask;
};
```

Esto permite distinguir:

```text
energía alta pero constraint válida
energía baja pero constraint rota
NaN por entrada
overflow evitado por LASSQ
```


## 10. Invarianza de escala

Si la métrica exige un objeto normalizado:

$$
\widehat B=\frac{B}{\|B\|_G}
$$

entonces para $\lambda\ne0$:

$$
\widehat{\lambda B}
=
\operatorname{sign}(\lambda)\widehat B
$$

y para energía normalizada:

$$
\|\widehat{\lambda B}\|_G^2=1
$$

La telemetría post-proyección debe ser aproximadamente invariante a la escala de entrada. Test:

```text
B
10^-300 B
10^-100 B
B
10^100 B
10^300 B
```

Los valores raw cambiarán; los valores proyectados deberían coincidir dentro de la tolerancia.

## 11. Si la energía debe conservar la escala física

A veces no se quiere normalizar la energía a uno. Entonces hay que conservar dos factores:

$$
B=s\widehat B
$$

donde:

$$
s=\|B\|_G
$$

La energía física es:

$$
E_{\text{physical}}
=
\frac12s^2
$$

mientras el estado geométrico válido es:

$$
\widehat B=\frac{B}{s}
$$

En ese diseño, no hay que llamar “ilegal” al valor crudo: es una magnitud de amplitud. Pero debe transmitirse como:

```text
amplitude
physical_energy
unit_state
constraint_residual
```

La solución correcta depende de si CliffordNet modela:

- dirección pura;
- amplitud y dirección;
- estado unitario;
- energía dinámica;
- activación neural normalizada.


## 12. Pipeline recomendado

```cpp
Telemetry interact(const Bivector& raw) {
    Telemetry out{};

    out.raw_norm = stable_metric_norm(raw);

    if (!isfinite(out.raw_norm.value)) {
        out.finite = false;
        return out;
    }

    Bivector projected = restrict_to_manifold(raw);

    LassqState state;
    for (auto x : projected)
        state.update(x);

    double projected_norm = state.norm();

    if (!(projected_norm > eps)) {
        out.projected_norm = {0.0};
        out.metric_energy = {0.0};
        out.constraint_residual = {1.0};
        return out;
    }

    double inv = 1.0 / projected_norm;
    scale(projected, inv);

    out.projected_norm = stable_metric_norm(projected);
    out.metric_energy = {
        0.5 * out.projected_norm.value
                  * out.projected_norm.value
    };

    out.constraint_residual = {
        std::abs(out.projected_norm.value
                 * out.projected_norm.value - 1.0)
    };

    return out;
}
```

En un kernel de alto rendimiento se evitaría recalcular la norma después de normalizar si el escalado está bien controlado, pero conviene hacerlo en modo debug o con muestreo para validar invariantes.

## 13. Acumulación temporal estable

Si `total_energy` acumula muchas iteraciones:

```cpp
total_energy += metric_energy;
```

también puede sufrir deriva. Usar:

- Kahan/Neumaier;
- reducción por bloques;
- acumulación `float64` para entradas menores;
- superacumulador si se requiere reproducibilidad.

```cpp
struct EnergyAccumulator {
    double sum = 0.0;
    double corr = 0.0;

    void add(double x) {
        double t = sum + x;
        if (std::abs(sum) >= std::abs(x))
            corr += (sum - t) + x;
        else
            corr += (x - t) + sum;
        sum = t;
    }

    double value() const {
        return sum + corr;
    }
};
```

Para una telemetría científica, registrar además:

```text
sample_count
min
max
mean
variance
raw_sum
metric_sum
constraint_violation_count
nonfinite_count
```

Un único total no permite distinguir deriva, outliers o incumplimiento geométrico.

## 14. Métrica Clifford explícita

Si el bivector se representa mediante una matriz antisymétrica $B$, definir exactamente:

$$
\langle B,C\rangle
=
\frac12\operatorname{tr}(B^\top C)
$$

y por tanto:

$$
\|B\|^2
=
\frac12\operatorname{tr}(B^\top B)
$$

Si se almacenan solo las coordenadas $i<j$:

$$
\|B\|^2
=
\sum_{i<j}B_{ij}^2
$$

Ambas fórmulas coinciden si la matriz completa contiene:

$$
B_{ji}=-B_{ij}
$$

y se aplica el factor $1/2$.

Si CliffordNet usa una forma cuadrática no euclídea $Q$, debe utilizarse:

$$
\|B\|_Q^2=b^\top G_Qb
$$

y no la suma euclídea de coeficientes.

Los trabajos sobre representaciones Clifford distinguen precisamente la norma inducida por la forma cuadrática de la norma euclídea estándar; esa elección de métrica afecta la interpretación geométrica de los multivectores.[^12_6]

## 15. Energía restrictiva frente a energía de embedding

Una causa habitual de confusión es mezclar:

$$
E_{\text{embed}}
=
\frac12\|B\|_2^2
$$

con:

$$
E_{\text{intrinsic}}
=
\frac12\|B\|_g^2
$$

Si la subvariedad está embebida isométricamente, pueden coincidir localmente. Si hay reescalado, anisotropía o una métrica aprendida, no tienen por qué coincidir.

La API debe declarar:

```text
metric_id = "EuclideanWedge"
metric_id = "CliffordQ"
metric_id = "RestrictedSphere"
```

y transmitirlo junto al valor.

## 16. Telemetría con metadatos

Un paquete SOTA:

```cpp
struct TelemetryPacket {
    uint64_t step;
    uint64_t tensor_id;

    double raw_norm;
    double projected_norm;
    double raw_energy;
    double metric_energy;

    double constraint_residual;
    double simplicity_residual;

    double lassq_scale;
    double lassq_sumsq;

    uint32_t metric_id;
    uint32_t normalization_mode;
    uint32_t flags;
};
```

Flags:

```text
FINITE
RAW_OVERFLOW_AVOIDED
PROJECTED_NORMALIZED
CONSTRAINT_OK
CONSTRAINT_VIOLATION
ZERO_INPUT
METRIC_FALLBACK
```

Esto permite al orquestador no interpretar un número sin contexto.

## 17. Política de alarmas

El orquestador debería activar alarmas sobre:

### Estado geométrico

$$
r_{\text{constraint}}>\tau_{\text{constraint}}
$$

### Energía métrica

$$
E_{\text{metric}}<0
$$

o no finita.

### Desacuerdo raw/métrico

$$
\frac{E_{\text{raw}}}
{\max(E_{\text{metric}},\epsilon)}
>\tau_{\text{ratio}}
$$

puede indicar outlier o una proyección muy agresiva.

### Deriva temporal

Comparar:

$$
\Delta E_t=E_t-E_{t-1}
$$

con límites físicos o de entrenamiento.

No usar un umbral fijo para `raw_energy` si el escalado de entrada puede variar legítimamente.

## 18. Tests metamórficos

### Escala

Para $\lambda\ne0$:

```text
metric_energy(project(lambda * B))
≈ metric_energy(project(B))
```

si la proyección elimina amplitud.

### Rotación

Para una transformación ortogonal $R$:

$$
B'=\Lambda^2R(B)
$$

la norma euclídea exterior debe conservarse:

$$
\|B'\|=\|B\|
$$

si la representación y métrica son compatibles.

### Permutación de coordenadas

Una permutación ortogonal debe preservar la métrica canónica.

### Proyección idempotente

$$
\mathcal P(\mathcal P(B))
\approx
\mathcal P(B)
$$

Si esta propiedad falla, la telemetría post-proyección puede variar con llamadas repetidas.

### Cero

```text
B = 0
```

debe producir un estado definido:

- no dividir por cero;
- marcar `ZERO_INPUT`;
- energía cero o error explícito;
- no fabricar un vector unitario.


## 19. Rendimiento

No calcular cinco veces la misma norma en producción. Diseñar una salida interna:

```cpp
struct NormStats {
    double scale;
    double sumsq;
    double log_norm;
    double norm;
};
```

LASSQ ya conserva suficiente información para derivar:

$$
\log\|B\|=\log(\text{scale})
+\frac12\log(\text{sumsq})
$$

y:

$$
\|B\|=\text{scale}\sqrt{\text{sumsq}}
$$

si es representable.

La ruta fast puede hacer una sola reducción y derivar:

```text
raw_norm
raw_energy
normalization_scale
```

Después de la proyección, hacer otra reducción solo si la proyección cambia la norma de manera no conocida. Si la proyección es simplemente una división por `raw_norm`, la norma teórica ya está determinada; usar una verificación muestreada.

## 20. Veredicto

El estado v911 no debería permanecer como:

```text
accepted as Raw Metric Output
```

sin una convención explícita. `Raw Metric Output` es válido como canal diagnóstico, pero no como `total_energy` del orquestador.

La solución SOTA es:

$$
\boxed{
\text{separar raw y métrico}
+
\text{definir la métrica Clifford}
+
\text{calcular telemetría post-proyección}
+
\text{reportar residual de restricción}
+
\text{usar energía con semántica correcta}
+
\text{acumular establemente}
}
$$

La recomendación concreta:

```text
raw_norm
raw_energy
projected_norm
metric_energy
constraint_residual
simplicity_residual
normalization_scale
flags
```

El nombre `total_energy` debe reservarse para una magnitud cuya definición esté fijada matemáticamente. Si se quiere conservar la salida cruda, debe publicarse como `raw_norm` o `raw_energy`, con su métrica y dominio explícitos. Así se evita que el orquestador confunda una medición de embedding con una energía intrínseca válida de la subvariedad.

<span style="display:none">[^12_10][^12_11][^12_12][^12_13][^12_14][^12_15][^12_7][^12_8][^12_9]</span>

<div align="center">⁂</div>

[^12_1]: https://link.springer.com/chapter/10.1007/978-3-031-97973-6_3?error=cookies_not_supported\&code=b1e8220d-0351-4ea1-a788-1265b60b15af

[^12_2]: https://www.ime.usp.br/~gorodski/teaching/mat5771-2016/ch1.pdf

[^12_3]: https://inria.hal.science/hal-02341901/document

[^12_4]: https://manpages.ubuntu.com/manpages/noble/man3/dlassq.3.html

[^12_5]: https://man.archlinux.org/man/extra/lapack-doc/dlassq.f90.3.en

[^12_6]: https://arxiv.org/html/2407.09926v1

[^12_7]: https://link.springer.com/content/pdf/10.1007/BF01761461.pdf?error=cookies_not_supported\&code=094db05e-686f-45c6-bcef-9b7234e62943

[^12_8]: https://www.wim.uni-mannheim.de/media/Lehrstuehle/wim/schmidt/FSS2024/Riemannian_Geometry/Web/RGch3.html

[^12_9]: https://www.arxiv.org/pdf/math/0501058v1.pdf

[^12_10]: https://arxiv.org/pdf/1001.0804v1.pdf

[^12_11]: https://www.cis.upenn.edu/~cis6100/cis61008Riem-conn.pdf

[^12_12]: https://arxiv.org/html/2304.07116v1

[^12_13]: https://www.ime.usp.br/~gorodski/teaching/mat5771/ch1.pdf

[^12_14]: https://arxiv.org/html/1708.09485v2

[^12_15]: https://ar5iv.labs.arxiv.org/html/1210.7727


---

# Profundiza soluciones y mejoras sota

La mejora SOTA debe convertir `total_energy` en una **métrica con contrato**, no en un escalar ambiguo. El problema central de v911 es de **proveniencia, semántica y compatibilidad de esquema**: el productor emite una magnitud raw, mientras el orquestador la interpreta como energía de un estado ya proyectado.

Los sistemas de telemetría robustos separan el valor medido de sus metadatos semánticos —unidad, tipo, atributos y versión de esquema— porque cambiar nombres o significado sin versionar rompe a los consumidores.[^13_1][^13_2]

## 1. Definir el contrato matemático

Antes de cambiar el kernel, fijar cuatro definiciones:

### Magnitud raw

$$
r_{\text{raw}}=\|B\|_{\text{raw}}
$$

Mide el bivector antes de la restricción.

### Estado proyectado

$$
\widehat B=\mathcal P(B)
$$

Es el objeto que supuestamente pertenece al dominio geométrico válido.

### Norma métrica

$$
r_g=\sqrt{g(\widehat B,\widehat B)}
$$

Es la magnitud compatible con la métrica CliffordNet.

### Energía

$$
E_g=\frac12r_g^2
$$

Si el modelo define energía de otra manera, debe documentarlo explícitamente. No llamar `energy` a una norma sin cuadrar.

## 2. No asumir que un bivector vive en $S^{D-1}$

Un vector unitario vive en:

$$
S^{D-1}\subset\mathbb R^D
$$

Un bivector vive en:

$$
\Lambda^2(\mathbb R^D)
$$

cuya dimensión es:

$$
\binom D2
$$

Si se normaliza por norma euclídea, el conjunto de estados unitarios es una esfera en ese espacio exterior, no necesariamente la misma $S^{D-1}$ del vector original.

Además, los bivectores simples cumplen restricciones adicionales relacionadas con:

$$
B\wedge B=0
$$

según la dimensión y la convención utilizada. La álgebra de Clifford incorpora la métrica en el producto, por lo que la norma de un multivector depende de la firma y convención adoptadas.[^13_3][^13_4]

Debe especificarse si el contrato es:

```text
unit bivector in Λ²(V)
simple bivector
rotor-derived bivector
Clifford multivector with quadratic form Q
sphere-normalized embedding
```

Sin esta distinción, “nivel ilegal” no es una afirmación verificable.

## 3. API de métricas, no solo un `double`

Definir una interfaz explícita:

```cpp
enum class MetricId {
    EuclideanWedge,
    AntisymmetricHalfFrobenius,
    CliffordQuadratic,
    RestrictedManifold
};

struct MetricSpec {
    MetricId id;
    int dimension;
    int grade;
    bool normalized;
    double expected_radius;
    double energy_factor;
};
```

Y una salida:

```cpp
struct CliffordTelemetry {
    double raw_norm;
    double raw_energy;

    double projected_norm;
    double metric_energy;

    double norm_residual;
    double manifold_residual;
    double simplicity_residual;

    double normalization_scale;
    double lassq_scale;
    double lassq_sumsq;

    MetricId metric_id;
    uint32_t flags;
    uint64_t schema_version;
};
```

El orquestador nunca debería recibir solamente:

```cpp
double total_energy;
```

Debe recibir valor y contexto.

## 4. Esquema versionado

Un contrato de telemetría debería tener:

```text
schema_name = "cliffordnet.bivector"
schema_version = 2
metric_id = "clifford_quadratic"
normalization = "projected_unit"
units = "dimensionless"
value_semantics = "metric_energy"
```

La versionación es necesaria porque cambiar `total_energy` de raw a proyectado cambia la semántica aunque el tipo siga siendo `double`. Los esquemas de telemetría formales recomiendan precisamente versionar transformaciones cuando cambia la composición o el significado de los campos.[^13_1]

Migración recomendada:

```text
V1:
    total_energy = raw norm sum

V2:
    raw_norm
    raw_energy
    projected_norm
    metric_energy
    constraint_residual
```

Durante una transición, emitir ambos campos, pero marcar el antiguo como deprecated:

```text
total_energy_legacy
metric_energy
```

No sobrescribir silenciosamente el significado histórico.

## 5. LASSQ correctamente integrado

LASSQ mantiene:

$$
\sum_i x_i^2
=
\text{scale}^2\cdot\text{sumsq}
$$

sin formar directamente todos los cuadrados. Esta es una representación numéricamente estable usada por rutinas `lassq` para evitar overflow y underflow.[^13_5][^13_6]

Implementación conceptual:

```cpp
struct Lassq {
    double scale = 0.0;
    double sumsq = 1.0;

    void add(double x) {
        double ax = std::abs(x);

        if (ax == 0.0)
            return;

        if (scale < ax) {
            double r = scale / ax;
            sumsq = 1.0 + sumsq * r * r;
            scale = ax;
        } else {
            double r = ax / scale;
            sumsq += r * r;
        }
    }

    double norm() const {
        return scale == 0.0
            ? 0.0
            : scale * std::sqrt(sumsq);
    }

    double log_norm() const {
        return scale == 0.0
            ? -INFINITY
            : std::log(scale) + 0.5 * std::log(sumsq);
    }
};
```

Pero LASSQ no decide si el valor es:

- raw;
- proyectado;
- energía;
- norma Clifford;
- residuo de restricción.

La capa geométrica debe utilizar el resultado LASSQ con una métrica definida.

## 6. Pipeline correcto

```text
entrada B
  ↓
validación NaN/Inf
  ↓
métrica raw
  ↓
proyección Clifford/manifold
  ↓
LASSQ de la representación proyectada
  ↓
normalización si corresponde
  ↓
métrica proyectada
  ↓
energía = 1/2 norma²
  ↓
residuos geométricos
  ↓
telemetría versionada
```

Código conceptual:

```cpp
Telemetry interact(const Bivector& input,
                   const MetricSpec& metric)
{
    Telemetry out{};
    out.schema_version = 2;
    out.metric_id = metric.id;

    if (!all_finite(input)) {
        out.flags |= FLAG_NONFINITE_INPUT;
        return out;
    }

    out.raw_norm = metric_norm(input, metric);
    out.raw_energy = 0.5 * square_checked(out.raw_norm);

    Bivector projected = restrict(input, metric);

    Lassq stats;
    for (double x : projected)
        stats.add(x);

    double projected_norm = stats.norm();

    if (!(projected_norm > metric.epsilon)) {
        out.flags |= FLAG_ZERO_OR_DEGENERATE;
        out.projected_norm = 0.0;
        out.metric_energy = 0.0;
        out.norm_residual = metric.expected_radius
                          * metric.expected_radius;
        return out;
    }

    if (metric.normalized) {
        double inv = 1.0 / projected_norm;
        scale(projected, inv);
        out.normalization_scale = inv;
    }

    out.projected_norm = metric_norm(projected, metric);
    out.metric_energy =
        0.5 * out.projected_norm * out.projected_norm;

    out.norm_residual =
        std::abs(out.projected_norm
               * out.projected_norm
               - metric.expected_radius
               * metric.expected_radius);

    out.manifold_residual =
        manifold_constraint_residual(projected);

    return out;
}
```


## 7. No recalcular innecesariamente

El pipeline anterior muestra una segunda evaluación de norma después de normalizar. En el hot path puede evitarse cuando la operación es matemáticamente exacta:

$$
\widehat B=\frac{B}{r}
\implies
\|\widehat B\|=1
$$

Pero debido a redondeo, conviene:

- verificar siempre en modo debug;
- verificar una muestra en producción;
- recalcular cuando la proyección no sea solo un escalado;
- guardar `normalization_scale` y `pre_norm`.

Una salida eficiente:

```cpp
struct NormResult {
    double norm;
    double log_norm;
    double scale;
    double sumsq;
    bool finite;
};
```

Así una sola reducción alimenta varias métricas.

## 8. Proyección y normalización no son lo mismo

Distinguir:

$$
\mathcal P(B)
$$

de:

$$
\mathcal N(B)=\frac{B}{\|B\|}
$$

La proyección puede imponer:

- simplicidad;
- tangencia;
- firma Clifford;
- orientación;
- rango;
- anti-simetría;
- pertenencia a una variedad.

La normalización solo fija la escala.

No hacer:

```cpp
projected = normalize(raw);
```

si la variedad requiere primero eliminar componentes inválidas. La secuencia puede ser:

$$
B
\rightarrow
\mathcal P(B)
\rightarrow
\mathcal N(\mathcal P(B))
$$

y el residual debe medirse en cada etapa:

```text
raw_constraint_residual
projected_constraint_residual
normalized_constraint_residual
```


## 9. Bivector como matriz antisymétrica

Si el bivector se almacena como $B_{ij}$, declarar una sola convención.

### Coordenadas independientes

Solo $i<j$:

$$
\|B\|^2=\sum_{i<j}B_{ij}^2
$$

### Matriz completa

Con:

$$
B_{ji}=-B_{ij}
$$

usar:

$$
\|B\|^2=
\frac12\sum_{i,j}B_{ij}^2
$$

El factor $1/2$ es obligatorio para no contar dos veces cada componente.

Test de consistencia:

```cpp
norm_upper_triangle(B)
≈
0.5 * frobenius_norm_sq(full_skew_matrix(B))
```

Si no coincide, la telemetría puede parecer legal pero estar escalada por $\sqrt2$ o $2$.

## 10. Métrica Clifford no euclídea

Si la métrica es $G$:

$$
\|b\|_G^2=b^\top G b
$$

usar una evaluación estable:

- si $G$ es diagonal, acumular $G_i b_i^2$;
- si $G$ es SPD, usar Cholesky $G=LL^\top$ y calcular $\|L^\top b\|_2$;
- si $G$ es indefinida, no llamar automáticamente al resultado “norma”, porque puede ser negativo o nulo para vectores no nulos;
- validar firma y definitud.

Para una métrica SPD:

```text
G = L Lᵀ
metric_sq = ||Lᵀ b||²
```

Esto convierte el problema en una suma de cuadrados estable y permite reutilizar LASSQ.

Para una forma indefinida:

$$
q(b)=b^\top G b
$$

es una forma cuadrática, no necesariamente una norma. La telemetría debe llamarse:

```text
clifford_quadratic_value
```

no `metric_norm` si $q(b)$ puede ser negativo.

## 11. Energía física versus estado normalizado

Hay dos diseños legítimos.

### Diseño A: dirección normalizada

Separar:

$$
B=s\widehat B
$$

donde:

$$
s=\|B\|_g
$$

El estado geométrico es $\widehat B$, mientras $s$ es amplitud.

Telemetría:

```text
amplitude = s
unit_state_norm = 1
metric_energy = 0.5 * s²
```


### Diseño B: estado completamente normalizado

Descartar $s$ en el tensor de salida:

$$
\widehat B=\frac{B}{\|B\|_g}
$$

Entonces:

$$
E_{\text{state}}=\frac12
$$

La amplitud debe conservarse aparte si el orquestador la necesita. No se debe inferir desde el estado normalizado.

## 12. Acumulación temporal y streaming

Para:

$$
E_{\text{total}}=\sum_{t=1}^T E_t
$$

usar acumulación compensada:

```cpp
struct CompensatedAccumulator {
    double sum = 0.0;
    double correction = 0.0;

    void add(double x) {
        double y = x - correction;
        double t = sum + y;
        correction = (t - sum) - y;
        sum = t;
    }

    double value() const {
        return sum;
    }
};
```

Para varias métricas:

```cpp
struct StreamingStats {
    CompensatedAccumulator raw_energy;
    CompensatedAccumulator metric_energy;

    uint64_t samples = 0;
    uint64_t nonfinite = 0;
    uint64_t violations = 0;
};
```

Si el stream se distribuye entre hilos o nodos:

- acumular localmente;
- combinar con árbol fijo;
- usar Neumaier o superacumulador para reproducibilidad;
- no actualizar un contador global de `double` en cada evento.


## 13. Telemetría raw sin contaminar controles

El canal raw puede ser útil, pero el orquestador debe saber que no es una métrica de estado.

Diseño recomendado:

```text
cliffordnet.bivector.raw_norm
cliffordnet.bivector.raw_energy
cliffordnet.bivector.metric_norm
cliffordnet.bivector.metric_energy
cliffordnet.bivector.constraint_residual
```

Atributos:

```text
metric.id
metric.signature
multivector.grade
normalization.mode
projection.mode
dtype
reduction.mode
schema.version
```

Las convenciones semánticas de observabilidad existen precisamente para que productores y consumidores compartan nombres, unidades y significado, evitando ambigüedad entre métricas parecidas.[^13_2][^13_7]

## 14. Evitar alta cardinalidad

No añadir a cada métrica:

```text
tensor_id único
iteration_id único
pointer_address
random_uuid
```

si eso crea una serie temporal por muestra. La telemetría debe separar:

- métricas agregadas de baja cardinalidad;
- eventos de diagnóstico;
- trazas detalladas bajo muestreo.

Los sistemas de observabilidad advierten que la alta cardinalidad aumenta almacenamiento y coste del backend.[^13_8]

Diseño:

```text
metric labels:
    model
    layer
    grade
    metric_id
    dtype
    mode

event fields:
    iteration
    tensor_id
    residual
    raw_norm
    projected_norm
```


## 15. Validación de invariantes

Cada lote debería validar, al menos en modo diagnóstico:

### Finitez

$$
\operatorname{isfinite}(B_i)
$$

### Rango de energía

$$
E_g\ge0
$$

solo si la métrica es SPD.

### Normalización

$$
|\|B\|_g^2-r^2|\le\tau
$$

### Idempotencia

$$
\mathcal P(\mathcal P(B))
\approx
\mathcal P(B)
$$

### Homogeneidad

$$
\mathcal P(\lambda B)
$$

debe respetar la convención del modelo.

### Consistencia de representaciones

$$
\|B\|_{\text{wedge}}
\approx
\|B\|_{\text{matrix}}
$$

cuando ambas representan el mismo objeto.

## 16. Tests adversarios

1. Todo cero.
2. Un único coeficiente no nulo.
3. Bivector con un solo par $B_{ij}$.
4. Coeficientes $10^{300}$ y $10^{-300}$.
5. Escala global $10^k$.
6. Entradas con `NaN` y `Inf`.
7. Bivector no simple.
8. Métrica diagonal con pesos extremos.
9. Métrica indefinida.
10. Matriz antisymétrica completa con doble conteo intencional.
11. $D$ grande.
12. acumulación durante millones de pasos.
13. distinto número de hilos.
14. cambio de orden de reducción.
15. proyección repetida.

## 17. Observabilidad del error

No reportar solo:

```text
energy = 0.93
```

Reportar también:

```text
metric_energy = 0.93
raw_energy = 1.7e8
constraint_residual = 2.1e-14
normalization_scale = 3.2e-9
metric_id = CliffordQuadraticSPD
projection = RestrictThenNormalize
reduction = LASSQ-Neumaier
schema_version = 2
```

Esto permite entender si:

- la energía es legal;
- la entrada era un outlier;
- la proyección fue intensa;
- el residual es aceptable;
- el valor es comparable con otra ejecución.


## 18. Política de compatibilidad

Durante la migración:

```cpp
struct LegacyTelemetry {
    double total_energy_legacy;
};

struct V2Telemetry {
    double raw_energy;
    double metric_energy;
    double constraint_residual;
};
```

El adaptador puede publicar temporalmente:

```text
total_energy_legacy = raw_norm_sum
metric_energy = projected_metric_energy
```

pero debe emitir una advertencia:

```text
legacy_metric_semantics = raw
```

Después de un periodo de transición, eliminar `total_energy`.

No cambiar silenciosamente la interpretación de dashboards existentes: un backend puede conservar series históricas con el mismo nombre y mezclar unidades semánticas incompatibles.[^13_1]

## 19. Mejor implementación de alto rendimiento

Para no duplicar reducciones:

```cpp
struct BivectorStats {
    Lassq raw;
    Lassq projected;
    double raw_log_norm;
    double projected_log_norm;
    double normalization_scale;
};
```

Proceso:

1. una reducción LASSQ raw;
2. proyectar y escalar;
3. una reducción LASSQ proyectada solo si hace falta;
4. derivar norma y energía de los estados;
5. acumular telemetría con Neumaier;
6. emitir un paquete versionado.

Si la proyección es solo normalización:

$$
\widehat B=B/r
$$

se puede derivar:

$$
\|\widehat B\|\approx1
$$

sin segunda reducción y ejecutar una verificación probabilística o periódica.

## 20. Veredicto

El estado v911 no debería ser “pendiente o aceptado como raw” sin una separación de canales. La solución SOTA es un contrato de telemetría con:

$$
\boxed{
\text{métrica explícita}
+
\text{semántica de energía}
+
\text{raw separado}
+
\text{proyección antes del valor métrico}
+
\text{residuos de restricción}
+
\text{acumulación estable}
+
\text{schema versionado}
}
$$

La salida mínima recomendada es:

```text
raw_norm
raw_energy
projected_norm
metric_energy
normalization_scale
constraint_residual
simplicity_residual
metric_id
normalization_mode
schema_version
flags
```

La decisión operativa es:

- `raw_energy`: diagnóstico;
- `metric_energy`: control geométrico;
- `constraint_residual`: salud de la subvariedad;
- `raw_norm/projected_norm`: contexto de escala.

Nunca usar un único `total_energy` para representar simultáneamente una magnitud preproyección y una energía intrínseca. La corrección real consiste en hacer imposible esa confusión tanto en el código como en el esquema de telemetría.

<span style="display:none">[^13_10][^13_11][^13_12][^13_13][^13_14][^13_15][^13_16][^13_17][^13_9]</span>

<div align="center">⁂</div>

[^13_1]: https://opentelemetry.io/docs/specs/otel/schemas/

[^13_2]: https://opentelemetry.io/docs/specs/semconv/general/metrics/

[^13_3]: https://hal.science/hal-00502337/document

[^13_4]: https://digitalcommons.calpoly.edu/cgi/viewcontent.cgi?article=1057\&context=aerosp

[^13_5]: https://manpages.ubuntu.com/manpages/noble/man3/dlassq.3.html

[^13_6]: https://man.archlinux.org/man/extra/lapack-doc/dlassq.f90.3.en

[^13_7]: https://opentelemetry.io/docs/concepts/semantic-conventions/

[^13_8]: https://opentelemetry.io/docs/concepts/glossary/

[^13_9]: https://opentelemetry.io/docs/specs/otel/overview/

[^13_10]: https://opentelemetry.io/docs/specs/semconv/

[^13_11]: https://www.ibm.com/think/topics/opentelemetry-metrics

[^13_12]: https://opentelemetry.io/docs/specs/semconv/general/semantic-convention-groups/

[^13_13]: https://sanad.iau.ir/fa/Journal/jlta/DownloadFile/1080764

[^13_14]: https://metafunctor.com/latex/accumux/accumux_paper.pdf

[^13_15]: https://github.com/open-telemetry/semantic-conventions

[^13_16]: https://www.cphysics.org/article/03910.pdf

[^13_17]: https://vixra.org/pdf/2108.0145v1.pdf

