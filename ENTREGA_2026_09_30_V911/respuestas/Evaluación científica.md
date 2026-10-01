<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## Evaluación científica

La solución v911 es **matemáticamente correcta** si `log_rms` representa:

$$
\log(\mathrm{RMS})=
\frac{1}{2}\log\left(\frac{1}{n}\sum_i x_i^2\right)
$$

y el denominador semántico requerido es:

$$
\sqrt{\mathrm{RMS}^2+\epsilon}.
$$

En el dominio logarítmico, la forma exacta es:

$$
\log\left(\sqrt{\mathrm{RMS}^2+\epsilon}\right)
=
\frac{1}{2}\log\left(e^{2\log\mathrm{RMS}}+\epsilon\right)
$$

o, de manera estable:

$$
\boxed{
\log\_rms\_\epsilon
=
\frac{1}{2}\operatorname{logaddexp}
\left(2\log\_rms,\log\epsilon\right)
}
$$

Por tanto, la expresión indicada:

$$
\log\_rms+
\log\left(1+\exp(\log\epsilon-\log\_rms)\right)
$$

**no es exacta para el RMS convencional** si `log_rms` significa $\log(\mathrm{RMS})$. Esa fórmula calcula:

$$
\log(\mathrm{RMS}+\epsilon),
$$

no:

$$
\frac{1}{2}\log(\mathrm{RMS}^2+\epsilon).
$$

La diferencia es semánticamente importante: en RMSNorm, $\epsilon$ se suma normalmente al **cuadrado del RMS**, antes de aplicar la raíz. La definición de referencia es $\sqrt{\epsilon+\operatorname{mean}(x^2)}$.[^1_1]

## Corrección recomendada

Si `log_rms` es $\log(\mathrm{RMS})$, implementar:

```python
log_rms_eps = 0.5 * torch.logaddexp(
    2.0 * log_rms,
    torch.log(torch.as_tensor(eps, dtype=log_rms.dtype, device=log_rms.device)),
)
```

Equivalentemente, si `log_mean_sq` representa:

$$
\log\left(\operatorname{mean}(x^2)\right),
$$

usar:

```python
log_rms_eps = 0.5 * torch.logaddexp(
    log_mean_sq,
    log_eps,
)
```

Para calcular la normalización directamente:

```python
log_inv_rms = -log_rms_eps
y = x * torch.exp(log_inv_rms)
```

Esta formulación evita materializar valores potencialmente infinitos y conserva correctamente el término $\epsilon$.

## Condición crítica: dónde se calcula `log_rms`

El cálculo de `log_rms` también debe ser estable. No conviene hacer:

```python
log_rms = 0.5 * torch.log(torch.mean(x * x))
```

si `x * x` puede desbordar en `float16`, `bfloat16` o incluso `float32`.

Una alternativa log-space robusta es:

$$
\log\operatorname{mean}(x^2)
=
2m+\log\left(\frac{1}{n}\sum_i e^{2\log|x_i|-2m}\right),
$$

donde:

$$
m=\max_i\log|x_i|.
$$

Pseudocódigo:

```python
x_acc = x.float()
log_abs = torch.log(torch.abs(x_acc))
m = torch.amax(log_abs, dim=dim, keepdim=True)

scaled = torch.exp(2.0 * (log_abs - m))
log_mean_sq = (
    2.0 * m
    + torch.log(torch.mean(scaled, dim=dim, keepdim=True))
)

log_eps = torch.log(
    torch.as_tensor(eps, dtype=log_mean_sq.dtype, device=log_mean_sq.device)
)

log_rms_eps = 0.5 * torch.logaddexp(log_mean_sq, log_eps)
y = x_acc * torch.exp(-log_rms_eps)
```

Debe tratarse explícitamente el caso $x_i=0$, porque $\log(0)=-\infty$. Una implementación más eficiente puede usar `logsumexp` directamente sobre $2\log|x|$, con acumulación en `float32` o `float64`.

## Análisis de precisión

v911 mejora claramente al parche V907 en tres aspectos:


| Propiedad | V907 | v911 propuesto | Forma recomendada |
| :-- | --: | --: | --: |
| Evita overflow del exponente | Sí | Sí | Sí |
| Conserva $\epsilon$ | Parcial o incorrectamente | Depende de la fórmula | Sí |
| Coincide con RMSNorm estándar | No garantizado | No si usa $\log(\mathrm{RMS}+\epsilon)$ | Sí |
| Estable ante escalas extremas | Sí | Sí | Sí |
| Semántica exacta | No | No en general | Sí |

El uso de `logaddexp` es una técnica numéricamente apropiada porque evita evaluar directamente una suma de exponentes con escalas muy distintas. Sin embargo, **la estabilidad numérica no corrige una discrepancia algebraica**: primero debe elegirse la cantidad correcta que se suma con $\epsilon$.

## Recomendaciones SOTA

- **Acumulación superior:** realizar las reducciones en `float32` para entradas `float16` o `bfloat16`; para pruebas de referencia, usar `float64`.
- **Promoción de `eps`:** convertir `eps` al mismo tipo y dispositivo que el acumulador, evitando conversiones silenciosas.
- **Referencia de validación:** comparar contra:

```python
ref = x.float() / torch.sqrt(torch.mean(x.float() ** 2, dim=dim, keepdim=True) + eps)
```

- **Pruebas extremas:** incluir entradas cero, subnormales, valores cercanos a overflow, vectores constantes y escalas desde aproximadamente $10^{-30}$ hasta $10^{30}$.
- **Pruebas de gradiente:** verificar `gradcheck` en `float64`, especialmente cerca de $x=0$.
- **Prueba de equivalencia:** comprobar que:

```python
torch.exp(log_rms_eps)
```

coincide con:

```python
torch.sqrt(torch.mean(x.float() ** 2, dim=dim, keepdim=True) + eps)
```

dentro del error esperado del tipo numérico.
- **Consistencia de contrato:** documentar si `eps` significa $\epsilon$ añadido a la media de cuadrados o una cantidad añadida después de la raíz. Ambas variantes existen, pero no son intercambiables.


## Veredicto

v911 emplea una herramienta SOTA adecuada —`logaddexp`—, pero la fórmula debe corregirse a:

$$
\boxed{
\log\_rms\_\epsilon
=
\frac{1}{2}\operatorname{logaddexp}
\left(2\log\_rms,\log\epsilon\right)
}
$$

si el objetivo es reproducir RMSNorm estándar. La versión sin el factor $2$ y sin el factor externo $1/2$ preserva $\epsilon$ de forma estable, pero cambia la operación a $\mathrm{RMS}+\epsilon$; por ello no debe considerarse semánticamente exacta para la definición convencional.

<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_2][^1_3][^1_4][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://docs.pytorch.org/docs/main/generated/torch.nn.RMSNorm.html

[^1_2]: https://docs.pytorch.org/docs/2.14/generated/torch.nn.RMSNorm.html

[^1_3]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html

[^1_4]: https://docs.pytorch.org/docs/2.9/generated/torch.nn.RMSNorm.html

[^1_5]: https://docs.pytorch.org/docs/2.8/generated/torch.nn.modules.normalization.RMSNorm.html

[^1_6]: https://docs.pytorch.org/docs/2.12/generated/torch.nn.RMSNorm.html

[^1_7]: https://docs.vllm.ai/en/stable/api/vllm/model_executor/layers/layernorm/

[^1_8]: https://meta-pytorch.org/torchtune/stable/\_modules/torchtune/modules/rms_norm.html

[^1_9]: https://docs.vllm.ai/en/v0.15.0/api/vllm/model_executor/layers/layernorm/

[^1_10]: https://huggingface.co/Hazan-Lab/Mamba_546M/resolve/383d55e6ea8aaef314f7b7afe30cc4d643ab58c6/norms.py?download=true

[^1_11]: https://github.com/agostini01/rms-norm-exercise

[^1_12]: https://huggingface.co/logos-flux/gb10-rmsnorm

[^1_13]: https://deepwiki.com/pszemraj/decoder-pytorch-template/3.4.4-normalization-(rmsnorm)

[^1_14]: https://huggingface.co/Hazan-Lab/Mamba_546M/blob/main/norms.py

[^1_15]: https://precisit.com/en/blog/where-rmsnorm-rounds/


---

## Conclusión principal

La corrección v911 va en la dirección adecuada al usar `logaddexp`, pero la fórmula debe alinearse con la semántica exacta de RMSNorm. Para la definición estándar:

$$
\operatorname{RMS}_\epsilon(x)
=
\sqrt{\frac{1}{n}\sum_{i=1}^{n}x_i^2+\epsilon},
$$

la forma logarítmica correcta es:

$$
\boxed{
\log \operatorname{RMS}_\epsilon
=
\frac{1}{2}\operatorname{logaddexp}
\left(
\log\left(\frac{1}{n}\sum_i x_i^2\right),
\log\epsilon
\right)
}
$$

Si `log_rms = log(RMS)`, entonces:

$$
\boxed{
\log\operatorname{RMS}_\epsilon
=
\frac{1}{2}\operatorname{logaddexp}
(2\log\_rms,\log\epsilon)
}
$$

La expresión anterior de v911,

$$
\log\_rms+\log(1+\exp(\log\epsilon-\log\_rms)),
$$

es estable, pero representa:

$$
\log(\operatorname{RMS}+\epsilon),
$$

no la semántica estándar:

$$
\log\left(\sqrt{\operatorname{RMS}^2+\epsilon}\right).
$$

Las implementaciones de PyTorch, NVIDIA Transformer Engine, vLLM y MLX documentan la variante con $\epsilon$ dentro de la raíz cuadrada.[^2_1][^2_2][^2_3][^2_4]

## 1. Derivación exacta

Definamos:

$$
q=\frac{1}{n}\sum_i x_i^2.
$$

Entonces:

$$
\operatorname{RMS}_\epsilon=\sqrt{q+\epsilon}.
$$

Si conocemos:

$$
\ell_q=\log q,
\qquad
\ell_\epsilon=\log\epsilon,
$$

obtenemos:

$$
\log\operatorname{RMS}_\epsilon
=
\frac{1}{2}\log(q+\epsilon)
=
\frac{1}{2}\log(e^{\ell_q}+e^{\ell_\epsilon}).
$$

Usando `logaddexp`:

```python
log_rms_eps = 0.5 * torch.logaddexp(log_mean_sq, log_eps)
```

Si se parte de:

```python
log_rms = 0.5 * log_mean_sq
```

la implementación equivalente es:

```python
log_rms_eps = 0.5 * torch.logaddexp(
    2.0 * log_rms,
    log_eps,
)
```

La transformación es algebraicamente exacta en aritmética real. En aritmética de punto flotante, su error queda limitado principalmente por la reducción, el tipo de acumulación y la evaluación de `logaddexp`.

## 2. Qué resolvió V907 y qué no

El desplazamiento del exponente usado en V907 probablemente tenía una estructura de este tipo:

```python
m = max(log_abs_x)
scaled = exp(log_abs_x - m)
log_rms = m + correction
```

Eso resuelve el problema de overflow en:

$$
\exp(2\log|x_i|),
$$

porque los exponentes desplazados son no positivos. La técnica es una aplicación del algoritmo estable de log-sum-exp; la literatura numérica confirma que el desplazamiento por el máximo evita los overflow que aparecen en la forma directa.[^2_5][^2_6]

Pero ese desplazamiento no incorpora automáticamente $\epsilon$. Hay dos operaciones separadas:

1. calcular de forma estable $q=\operatorname{mean}(x^2)$;
2. combinar exactamente $q$ con $\epsilon$.

v911 mejora el segundo paso, pero solo es correcto si usa la escala adecuada:

```python
0.5 * logaddexp(log_mean_sq, log_eps)
```

o:

```python
0.5 * logaddexp(2 * log_rms, log_eps)
```


## 3. Algoritmos recomendados

### Variante de producción convencional

Para la mayoría de modelos, la solución preferible no es trabajar completamente en log-space, sino calcular la reducción en `float32` y usar `rsqrt`:

```python
def rms_norm_stable(x, weight=None, eps=1e-6, dim=-1):
    x_acc = x.float()
    mean_sq = torch.mean(x_acc * x_acc, dim=dim, keepdim=True)
    inv_rms = torch.rsqrt(mean_sq + float(eps))
    y = x_acc * inv_rms

    if weight is not None:
        y = y * weight.float()

    return y.to(dtype=x.dtype)
```

Esta forma coincide con la definición de RMSNorm utilizada por implementaciones de referencia y kernels de producción. NVIDIA documenta explícitamente la fórmula $\sqrt{\operatorname{mean}(x^2)+\epsilon}$, mientras que MLX especifica que la media se acumula en precisión de 32 bits.[^2_2][^2_4]

Ventajas:

- menor coste que la ruta logarítmica;
- menor consumo de memoria y latencia;
- buena precisión para entradas fp16/bf16;
- compatibilidad con kernels fusionados;
- mejor comportamiento de gradiente que una cadena larga de `log` y `exp`.


### Variante log-space robusta

Para rangos dinámicos extremos, usar:

```python
def rms_norm_logspace(x, weight=None, eps=1e-6, dim=-1):
    x_acc = x.float()
    tiny = torch.finfo(x_acc.dtype).tiny

    log_abs = torch.log(torch.abs(x_acc).clamp_min(tiny))
    log_sq = 2.0 * log_abs

    log_mean_sq = torch.logsumexp(log_sq, dim=dim, keepdim=True)
    n = x_acc.shape[dim]
    log_mean_sq = log_mean_sq - math.log(n)

    log_eps = torch.as_tensor(
        eps,
        dtype=log_mean_sq.dtype,
        device=log_mean_sq.device,
    ).log()

    log_rms_eps = 0.5 * torch.logaddexp(log_mean_sq, log_eps)
    y = x_acc * torch.exp(-log_rms_eps)

    if weight is not None:
        y = y * weight.float()

    return y.to(dtype=x.dtype)
```

Esta versión evita calcular $x^2$ directamente. Sin embargo, el `clamp_min(tiny)` introduce una aproximación para valores subnormales o ceros. Para semántica exacta en cero, conviene tratar el caso explícitamente:

```python
nonzero = x_acc != 0
log_abs = torch.where(
    nonzero,
    torch.log(torch.abs(x_acc)),
    torch.full_like(x_acc, -torch.inf),
)
```

Así, un vector completamente nulo produce:

$$
\log\operatorname{RMS}_\epsilon=\frac{1}{2}\log\epsilon,
$$

y la salida sigue siendo exactamente cero.

### Variante híbrida recomendada

La mejor solución práctica suele ser híbrida:

1. entrada almacenada en fp16/bf16;
2. conversión a fp32;
3. reducción de cuadrados en fp32;
4. uso de `logaddexp` solo cuando el rango dinámico lo requiere;
5. `rsqrt` o `exp(-log_rms_eps)` para la escala;
6. conversión final al dtype original.
```python
def rms_norm_hybrid(x, weight=None, eps=1e-6, dim=-1):
    x_acc = x.float()
    mean_sq = torch.mean(x_acc.square(), dim=dim, keepdim=True)

    log_mean_sq = torch.log(mean_sq)
    log_eps = torch.log(
        torch.as_tensor(eps, dtype=x_acc.dtype, device=x_acc.device)
    )

    log_denom = 0.5 * torch.logaddexp(log_mean_sq, log_eps)
    y = x_acc * torch.exp(-log_denom)

    if weight is not None:
        y = y * weight.float()

    return y.to(x.dtype)
```

Esta variante no evita el overflow de `x_acc.square()` si `x_acc` está fuera del rango de fp32; para activaciones normales de Transformers suele bastar. Para un rango arbitrariamente extremo, debe usarse la variante completamente log-space.

## 4. Elección de `epsilon`

`epsilon` no es solo un protector contra división por cero. También define una regularización efectiva:

$$
\frac{x}{\sqrt{q+\epsilon}}.
$$

Cuando $q\ll\epsilon$, la salida queda aproximadamente:

$$
\frac{x}{\sqrt{\epsilon}}.
$$

Por ello, aumentar `eps` limita la ganancia sobre activaciones muy pequeñas, pero también cambia el modelo.

Consideraciones:


| Caso | Recomendación |
| :-- | :-- |
| fp32 | `1e-6` o el valor definido por el modelo |
| bf16 | normalmente conservar el `eps` original y acumular en fp32 |
| fp16 | evaluar `1e-5` si aparecen inestabilidades; no cambiar sin validación |
| fp8 | normalmente requiere calibración y un `eps` mayor, según el kernel |
| checkpoint existente | preservar exactamente el `eps` usado durante entrenamiento |

PyTorch indica que su valor por defecto depende de la precisión de cálculo, usando la precisión de operación correspondiente. Por tanto, no es recomendable reemplazar automáticamente el `eps` del checkpoint por una constante universal.[^2_1]

Una observación importante: algunos textos describen `eps` fuera de la raíz, como $\mathrm{RMS}(x)+\epsilon$, pero eso es otra función. Las implementaciones deben documentar explícitamente la convención para evitar incompatibilidades entre frameworks.[^2_7]

## 5. Precisión de la reducción

Incluso con una fórmula correcta, el resultado puede variar por el orden de suma. En GPU, diferentes tamaños de bloque, árboles de reducción y kernels fusionados producen ligeras diferencias de redondeo. Estas diferencias pueden propagarse porque un único escalar RMS reescala todos los elementos de la fila.[^2_8]

Recomendaciones:

- acumular `mean(x²)` en fp32;
- usar fp64 para pruebas de referencia;
- aplicar reducción determinista si se necesita reproducibilidad;
- evitar acumular directamente en fp16;
- hacer el cast a fp16/bf16 una sola vez, al final;
- comparar tolerancias relativas y absolutas, no igualdad exacta entre kernels distintos.

Para una referencia de alta precisión:

```python
def rms_reference(x, eps):
    x64 = x.to(torch.float64)
    return x64 / torch.sqrt(
        torch.mean(x64.square(), dim=-1, keepdim=True)
        + torch.tensor(eps, dtype=torch.float64)
    )
```


## 6. Backward y estabilidad del gradiente

Sea:

$$
y_i=\frac{x_i}{\sqrt{q+\epsilon}},
\qquad
q=\frac{1}{n}\sum_jx_j^2.
$$

La derivada contiene el factor:

$$
(q+\epsilon)^{-1/2}
$$

y un término de acoplamiento proporcional a:

$$
\frac{x_i x_j}{n(q+\epsilon)^{3/2}}.
$$

Por eso, aunque $\epsilon$ evita una singularidad, un `eps` demasiado pequeño puede producir gradientes muy grandes cuando $q$ es pequeño. La validación debe incluir:

- $x=0$;
- entradas con una sola componente no nula;
- valores homogéneos;
- $q\approx\epsilon$;
- $q\gg\epsilon$;
- escalas subnormales;
- `gradcheck` en fp64.

También conviene distinguir entre estabilidad hacia adelante y hacia atrás: que el denominador no sea `Inf` o `NaN` no garantiza que el gradiente sea preciso.

## 7. Fusión y kernels SOTA

En producción, la ruta más eficiente suele ser un kernel fusionado que realiza:

1. carga de `x`;
2. conversión o acumulación en fp32;
3. reducción de $\sum x_i^2$;
4. suma de `eps`;
5. `rsqrt`;
6. escalado por `x`;
7. multiplicación por `weight`.

Los kernels de NVIDIA Transformer Engine exponen explícitamente el cálculo de RMSNorm y reciben `epsilon` como parámetro del kernel. cuDNN también documenta kernels fusionados RMSNorm + SiLU con cálculo interno en fp32 para estabilidad.[^2_9][^2_10][^2_2]

FlashNorm propone una optimización algebraicamente exacta para RMSNorm seguida de una capa lineal: puede diferir la normalización escalar y fusionarla conceptualmente con la proyección posterior. La ventaja es de rendimiento, no una modificación de la semántica de $\epsilon$.[^2_11]

La ruta log-space completa rara vez es la opción más rápida en hardware convencional, porque introduce `log`, `exp` y `logaddexp`. Debe reservarse para:

- activaciones con rango dinámico excepcional;
- cómputo científico;
- validación de referencia;
- detección y prevención de overflow;
- modelos o kernels que operan directamente en dominios logarítmicos.


## 8. Protocolo de validación SOTA

### Equivalencia funcional

Comparar:

```python
ref = x.float() / torch.sqrt(
    torch.mean(x.float().square(), dim=-1, keepdim=True) + eps
)
```

contra:

```python
test = x.float() * torch.exp(-log_rms_eps)
```

Métricas:

$$
\text{abs\_err}=\max_i |y_i-\hat y_i|,
$$

$$
\text{rel\_err}
=
\max_i
\frac{|y_i-\hat y_i|}
{\max(|y_i|,\text{tiny})}.
$$

### Distribución de pruebas

Usar entradas:

$$
x=s\cdot z,
$$

donde $z\sim\mathcal N(0,1)$ y:

$$
s\in
\{0,10^{-30},10^{-20},10^{-10},10^{-5},1,10^5,10^{10},10^{20},10^{30}\}.
$$

Añadir casos estructurados:

- vector completamente cero;
- vector constante;
- una sola componente grande;
- alternancia de signos;
- mezcla de ceros y subnormales;
- longitudes pequeñas y grandes;
- dimensiones no múltiplos del tamaño de warp.


### Criterios

- cero `NaN` e `Inf`;
- monotonía razonable al variar `eps`;
- coincidencia con la referencia en fp64;
- error acotado al cambiar el orden de reducción;
- gradientes finitos;
- paridad entrenamiento-inferencia;
- ausencia de regresión en pérdida, perplexity o métricas downstream.


## Veredicto final sobre v911

v911 debe considerarse una **mejora parcial**:

- `logaddexp` es la herramienta correcta para combinar términos en log-space;
- conserva mejor el término $\epsilon$ que el parche V907;
- evita overflow y underflow en la suma logarítmica;
- pero la fórmula propuesta no es semánticamente RMSNorm si usa `log_rms` sin duplicarlo;
- la corrección rigurosa es:

```python
log_rms_eps = 0.5 * torch.logaddexp(
    2 * log_rms,
    log_eps,
)
```


Para producción, la recomendación SOTA es usar acumulación fp32, `mean(x²) + eps` dentro de la raíz, `rsqrt`, y un kernel fusionado. Para rangos extremos o validación científica, usar la formulación log-space completa con `logsumexp` para la reducción y `logaddexp` para incorporar $\epsilon$.

<span style="display:none">[^2_12][^2_13][^2_14][^2_15][^2_16][^2_17][^2_18][^2_19][^2_20][^2_21][^2_22][^2_23][^2_24][^2_25][^2_26][^2_27][^2_28][^2_29][^2_30]</span>

<div align="center">⁂</div>

[^2_1]: https://docs.pytorch.org/docs/2.14/generated/torch.nn.modules.normalization.RMSNorm.html

[^2_2]: https://docs.nvidia.com/deeplearning/transformer-engine-releases/release-1.4/user-guide/api/c/rmsnorm.html

[^2_3]: https://docs.vllm.ai/en/v0.20.1/api/vllm/model_executor/layers/layernorm/

[^2_4]: https://ml-explore.github.io/mlx/build/html/python/nn/\_autosummary/mlx.nn.RMSNorm.html

[^2_5]: https://academic.oup.com/imajna/article/41/4/2311/5893596

[^2_6]: https://arxiv.org/pdf/1909.03469v1.pdf

[^2_7]: https://mbrenndoerfer.com/writing/rmsnorm-efficient-normalization-modern-llms

[^2_8]: https://fireworks.ai/blog/when-faster-not-identical-moe-numerics

[^2_9]: https://docs.nvidia.com/deeplearning/transformer-engine-releases/release-1.2.0/user-guide/api/c/rmsnorm.html

[^2_10]: https://docs.nvidia.com/deeplearning/cudnn/latest/fe-oss-apis/rmsnorm_silu.html

[^2_11]: https://arxiv.org/html/2407.09577v5

[^2_12]: https://docs.modular.com/max/api/python/nn/norm/rms_norm/

[^2_13]: https://www.itechguides.com/using-normalization-layers-to-improve-deep-learning-models/

[^2_14]: https://theorempath.com/topics/numerical-stability

[^2_15]: https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.rms_norm.html

[^2_16]: https://docs.vllm.ai/en/latest/api/vllm/model_executor/layers/layernorm/

[^2_17]: https://arxiv.org/html/2601.03324v1

[^2_18]: https://lizeman.github.io/llm-arch-kb/normalization/rmsnorm/

[^2_19]: https://yobitel.com/knowledge-base/rmsnorm

[^2_20]: https://github.com/bassrehab/triton-kernels

[^2_21]: https://deepwiki.com/Dao-AILab/quack/6.2-normalization-testing

[^2_22]: https://github.com/NVIDIA/TransformerEngine/issues/1132

[^2_23]: https://github.com/NVIDIA/apex/issues/1271

[^2_24]: https://www.alphaxiv.org/abs/2407.09577

[^2_25]: https://docs.pytorch.org/docs/main/generated/torch.nn.RMSNorm.html

[^2_26]: https://docs.pytorch.org/docs/2.13/generated/torch.nn.modules.normalization.RMSNorm.html

[^2_27]: https://docs.pytorch.org/docs/2.12/generated/torch.nn.RMSNorm.html

[^2_28]: https://docs.pytorch.org/docs/2.8/generated/torch.nn.modules.normalization.RMSNorm.html

[^2_29]: https://docs.vllm.ai/en/stable/api/vllm/model_executor/layers/layernorm/

[^2_30]: https://precisit.com/en/blog/where-rmsnorm-rounds/


---

## Evaluación del problema

La migración de Kahan a Neumaier en v911 es una **mejora correcta y científicamente justificada**, especialmente cuando la suma contiene términos de signos alternantes y magnitudes similares. La condición:

```cpp
if (std::abs(local) >= std::abs(term))
```

es precisamente la decisión que permite escoger qué operando domina y calcular correctamente el error de redondeo asociado a la suma. Neumaier suele ser más robusto que Kahan cuando el nuevo término es mayor que el acumulador parcial.

Pero hay una precisión conceptual importante: Neumaier no garantiza una suma “exacta” en sentido absoluto. Garantiza una compensación significativamente mejor dentro del formato utilizado. Para exactitud redondeada o reproducibilidad bit a bit, las soluciones SOTA son expansiones flotantes, sumas por bins y superacumuladores de Kulisch.

## 1. Por qué Kahan puede degradarse

Kahan mantiene:

```cpp
sum += term;
correction += ...
```

Su ventaja es reducir el error acumulado cuando los términos tienen una distribución relativamente favorable. Sin embargo, con alternancia extrema de signos pueden aparecer situaciones donde:

$$
|term|>|sum|,
$$

y el modelo de error implícito en Kahan deja de ser óptimo. En particular, si el acumulador cambia repetidamente de signo o pasa cerca de cero, los términos de compensación pueden quedar redondeados, sobrescritos o reutilizados en un contexto para el que ya no representan correctamente el error anterior.

La condición numéricamente mal condicionada de una suma puede expresarse mediante:

$$
\kappa_{\mathrm{sum}}
=
\frac{\sum_i |x_i|}
{\left|\sum_i x_i\right|}.
$$

En tensores antipodales o casi antipodales, el denominador puede ser muy pequeño aunque cada término sea grande. Entonces $\kappa_{\mathrm{sum}}$ se dispara: pequeñas perturbaciones de redondeo pueden producir cambios relativos enormes en la suma final.

La mejora de Neumaier es especialmente relevante en ese régimen, pero no elimina el mal condicionamiento matemático de la operación.

## 2. Neumaier correctamente implementado

La forma escalar estándar es:

```cpp
double sum = 0.0;
double correction = 0.0;

for (double term : values) {
    double t = sum + term;

    if (std::abs(sum) >= std::abs(term)) {
        correction += (sum - t) + term;
    } else {
        correction += (term - t) + sum;
    }

    sum = t;
}

double result = sum + correction;
```

La rama condicional no es una optimización menor. Es el componente que permite reconstruir el redondeo cuando `term` domina a `sum`.

Una variante más compacta es:

```cpp
double t = sum + term;
correction +=
    (std::abs(sum) >= std::abs(term))
        ? (sum - t) + term
        : (term - t) + sum;
sum = t;
```

Debe evitarse una implementación que calcule siempre:

```cpp
correction += (sum - t) + term;
```

porque esa forma solo es apropiada bajo la hipótesis de que `sum` domina al nuevo término.

## 3. Qué garantiza realmente v911

v911 mejora las siguientes propiedades:


| Propiedad | Kahan | Neumaier | Superacumulador |
| :-- | --: | --: | --: |
| Bajo coste | Alto | Alto | Medio o alto |
| Signos alternantes | Vulnerable en casos extremos | Mejor | Robusto |
| Compensación local | Sí | Sí | No necesaria en igual sentido |
| Exactitud de la suma | Aproximada | Muy buena | Exacta antes del redondeo final |
| Reproducibilidad paralela | No automática | No automática | Sí, si se diseña así |
| Overflow del acumulador | Posible | Posible | Diseñado para evitarlo |
| Idoneidad GPU | Buena | Buena | Más compleja |

La afirmación “garantizando contabilidad exacta de los bits descartados” debe matizarse. Neumaier recupera el error de una suma binaria elemental bajo condiciones de redondeo habituales, pero el término de compensación también se acumula con redondeo. Después de muchas iteraciones, todavía puede perder información.

Por ello, una formulación más precisa sería:

> v911 realiza una compensación de primer orden más robusta frente a cancelación severa, pero no proporciona exactitud arbitraria ni suma reproducible por sí sola.

## 4. Mejoras SOTA por nivel de exigencia

### Nivel 1: Neumaier secuencial

Adecuado cuando:

- se necesita una mejora inmediata sobre Kahan;
- el vector no es gigantesco;
- la reproducibilidad exacta no es requisito;
- el coste de dos sumas adicionales por elemento es aceptable.

Debe utilizarse el tipo de acumulación más amplio posible:

```cpp
float input;
double sum = 0.0;
double correction = 0.0;
```

Para entradas `float`, acumular en `double` suele dar una mejora sustancial. Para entradas `double`, Neumaier en `long double` puede ayudar, aunque la disponibilidad y precisión real de `long double` dependen de la plataforma.

### Nivel 2: suma por pares

La suma por pares reduce el error de $O(nu)$ hacia un comportamiento cercano a:

$$
O(u\log n),
$$

donde $u$ es la unidad de redondeo. Es preferible a una suma lineal cuando los términos tienen escalas muy distintas.

```cpp
double pairwise_sum(const double* x, std::size_t n) {
    if (n == 0) return 0.0;
    if (n == 1) return x[^3_0];

    std::size_t mid = n / 2;
    return pairwise_sum(x, mid)
         + pairwise_sum(x + mid, n - mid);
}
```

En producción, la versión recursiva debe transformarse en una reducción iterativa o por bloques para evitar overhead y mejorar localidad de memoria.

Una estrategia sólida es:

1. sumar cada bloque con Neumaier;
2. combinar los resultados parciales mediante suma por pares;
3. usar un último paso compensado.

Esto suele ser más rápido y más estable que Neumaier completamente secuencial.

### Nivel 3: expansiones flotantes

Una expansión representa un número como:

$$
x=e_0+e_1+\cdots+e_k,
$$

donde cada componente conserva bits que se perderían en una suma ordinaria. Las transformaciones `TwoSum` y `FastTwoSum` permiten separar el resultado redondeado del error exacto de una suma elemental:

```cpp
inline void two_sum(double a, double b, double& s, double& e) {
    s = a + b;
    double z = s - a;
    e = (a - (s - z)) + (b - z);
}
```

Luego puede acumularse el residuo en una expansión:

```cpp
struct Expansion2 {
    double hi;
    double lo;
};

Expansion2 add_expansion(Expansion2 a, double b) {
    double s, e;
    two_sum(a.hi, b, s, e);

    double t, f;
    two_sum(a.lo, e, t, f);

    double hi, lo;
    two_sum(s, t, hi, lo);

    return {hi, lo + f};
}
```

Las expansiones son una alternativa intermedia entre Neumaier y un superacumulador: ofrecen mucha más precisión sin necesitar miles de bits fijos, aunque su coste y complejidad crecen con el número de componentes.

## 5. Superacumuladores y exactitud redondeada

Si se necesita una suma exacta de valores de punto flotante antes del redondeo final, la solución de referencia es un superacumulador.

La idea es convertir cada número en una representación entera escalada y acumularlo en una estructura suficientemente ancha para cubrir todo el rango de exponentes. En binary64, un acumulador fijo de varios miles de bits puede representar exactamente la suma de valores flotantes sin perder bits intermedios. Los trabajos sobre superacumuladores describen precisamente este enfoque y muestran cómo obtener sumas deterministas y bit-perfect en grandes reducciones.[^3_1][^3_2][^3_3]

Las ventajas son:

- exactitud de la suma;
- redondeo correcto solo al final;
- reproducibilidad independiente del orden;
- robustez ante cancelación catastrófica;
- control explícito del overflow.

Las desventajas son:

- mayor consumo de registros o memoria;
- propagación de carries;
- dificultad de vectorización;
- coste más alto en GPU;
- implementación más compleja.

Para tensores antipodales, el superacumulador es la opción científicamente más fuerte si la métrica debe ser reproducible y auditable.

## 6. Suma reproducible en paralelo

Neumaier por hilo no garantiza que dos ejecuciones paralelas produzcan el mismo resultado. La razón es que el orden de reducción puede variar:

$$
(a+b)+c\ne a+(b+c).
$$

Una arquitectura recomendable para CPU/GPU es:

1. reducir cada bloque en una expansión o acumulador por bins;
2. almacenar resultados parciales en una representación canónica;
3. combinar los bloques con un árbol determinista;
4. redondear únicamente al final.

El algoritmo ExBLAS es un ejemplo de esta familia: combina filtrado rápido, expansiones y superacumuladores para obtener sumas paralelas reproducibles con alta precisión.[^3_2][^3_1]

Para una métrica geodésica en producción, conviene separar dos modos:

- **modo rápido:** reducción por pares o Neumaier por bloque;
- **modo exacto:** superacumulador reproducible activable para validación, auditoría y casos degenerados.


## 7. El problema no es solo la suma

En una métrica geodésica sobre $S^{D-1}$, hay que distinguir entre:

1. la precisión del producto punto;
2. la estabilidad de la transformación del producto punto en ángulo;
3. la propagación del error al resultado geodésico.

Si $u$ y $v$ son vectores normalizados:

$$
\theta=\arccos(u\cdot v).
$$

Esta fórmula es problemática en dos extremos:

- cerca de $u\cdot v=1$, para puntos casi coincidentes;
- cerca de $u\cdot v=-1$, para puntos casi antipodales.

La derivada:

$$
\frac{d}{dz}\arccos(z)
=
-\frac{1}{\sqrt{1-z^2}}
$$

crece sin límite cerca de $\pm1$. Por ello, mejorar únicamente el sumador no resuelve toda la inestabilidad.

En la esfera tridimensional, una alternativa robusta es:

$$
\theta
=
\operatorname{atan2}
\left(
\|u\times v\|,
u\cdot v
\right).
$$

Para vectores de dimensión arbitraria:

$$
\theta
=
\operatorname{atan2}
\left(
\sqrt{\max(0,1-c^2)},
c
\right),
\qquad
c=u\cdot v.
$$

Esto evita llamar directamente a `acos`, aunque cerca de los extremos todavía depende de la precisión con que se calcule $c$.

Otra forma equivalente es:

$$
\theta
=
2\operatorname{atan2}
\left(
\frac{\|u-v\|}{2},
\frac{\|u+v\|}{2}
\right).
$$

Esta representación es especialmente útil porque:

- $\|u-v\|$ es pequeña cerca de coincidencia;
- $\|u+v\|$ es pequeña cerca de antipodalidad;
- `atan2` conserva mejor la relación entre numerador y denominador.

La fórmula haversine también es conocida por ser estable para separaciones pequeñas, pero puede sufrir pérdida de exactitud cerca de antipodalidad debido a la saturación de su variable interna.[^3_4][^3_5][^3_6]

## 8. Solución geodésica recomendada

Para vectores unitarios, calcular simultáneamente:

$$
d_-^2=\|u-v\|^2,
\qquad
d_+^2=\|u+v\|^2.
$$

Para vectores idealmente normalizados:

$$
\theta
=
2\operatorname{atan2}
\left(
\sqrt{d_-^2},
\sqrt{d_+^2}
\right).
$$

Si las normas no son exactamente uno, usar:

$$
a=\frac{\|u-v\|}{\|u\|+\|v\|},
\qquad
b=\frac{\|u+v\|}{\|u\|+\|v\|},
$$

y normalizar con cuidado antes de aplicar `atan2`.

Pseudocódigo:

```cpp
double geodesic_angle(const Vec& u, const Vec& v) {
    double d_minus_sq = stable_squared_distance(u, v);
    double d_plus_sq  = stable_squared_sum(u, v);

    d_minus_sq = std::max(0.0, d_minus_sq);
    d_plus_sq  = std::max(0.0, d_plus_sq);

    return 2.0 * std::atan2(
        std::sqrt(d_minus_sq),
        std::sqrt(d_plus_sq)
    );
}
```

Sin embargo, `stable_squared_distance` y `stable_squared_sum` no deberían construir primero cada componente de forma peligrosa si hay grandes diferencias de escala. Usar una reducción estable sobre:

$$
(u_i-v_i)^2
\quad\text{y}\quad
(u_i+v_i)^2
$$

con acumulación fp64, Neumaier, expansión o superacumulador según el nivel requerido.

## 9. Clamping: necesario, pero no suficiente

Si se usa:

```cpp
c = std::clamp(dot, -1.0, 1.0);
theta = std::acos(c);
```

el `clamp` evita un `NaN` causado por un resultado como $1+2u$ o $-1-2u$. Pero no recupera los bits perdidos antes del clamp.

Por tanto:

- `clamp` es una barrera de seguridad;
- no sustituye a una reducción precisa;
- puede ocultar una degradación sistemática;
- debe registrarse o medirse cuántas veces se activó.

Una métrica de calidad útil es:

```cpp
if (dot < -1.0 || dot > 1.0) {
    clamp_counter.fetch_add(1, std::memory_order_relaxed);
}
```

Si el contador crece en datos normales, existe un problema de normalización, reducción o rango dinámico.

## 10. Recomendación concreta para v911

La arquitectura recomendada es:

### Modo rápido

- entrada `float` o `half`;
- acumulación fp32 o fp64;
- suma por pares por bloque;
- Neumaier dentro de cada bloque;
- reducción determinista de bloques;
- fórmula angular basada en `atan2`;
- `clamp` final solo como protección.


### Modo preciso

- productos calculados con FMA cuando estén disponibles;
- expansión flotante para cada producto y suma;
- superacumulador para casos de cancelación extrema;
- resultado redondeado una sola vez;
- cálculo angular mediante `atan2`, no `acos` directo;
- comparación contra referencia multiprecisión.


### Modo científico

- entradas convertidas a `long double`, double-double o precisión arbitraria;
- superacumulador o suma exacta;
- control de normas y condición;
- intervalos de error;
- pruebas de invariancia bajo permutación;
- medición de error angular absoluto, no solo error relativo.


## Veredicto

La solución v911 con Neumaier es una mejora sólida frente a Kahan para signos alternantes, pero la descripción debe evitar afirmar exactitud completa. Neumaier corrige mejor el error local cuando el término nuevo domina al acumulador, aunque sigue siendo una técnica de precisión finita y no garantiza reproducibilidad paralela.

La solución SOTA completa consta de tres capas:

1. **sumador:** Neumaier, suma por pares o expansión flotante;
2. **casos extremos:** superacumulador de Kulisch/ExBLAS;
3. **geometría:** representación angular con `atan2` y distancias $\|u-v\|$, $\|u+v\|$, evitando depender exclusivamente de `acos`.

Para v911, la recomendación más rigurosa sería reemplazar la afirmación de “contabilidad exacta” por:

> “Compensación robusta de primer orden frente a cancelación y alternancia de signos, con ruta opcional de expansión o superacumulador para exactitud redondeada y reproducibilidad determinista.”

<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_7][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://hal.science/hal-00949355v1/preview/superaccumulator.pdf

[^3_2]: https://hal.science/hal-00949355v1/document

[^3_3]: https://hal.science/hal-00949355v2/file/superaccumulator.pdf

[^3_4]: https://en.wikipedia.org/wiki/Haversine_formula

[^3_5]: https://www.coordinately.org/learn/great-circle-distance

[^3_6]: https://id3es.com/math/distance-measures

[^3_7]: https://www.tuhh.de/ti3/paper/rump/RuOgOi07I.pdf

[^3_8]: https://arxiv.org/html/2312.10247v1

[^3_9]: https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf

[^3_10]: http://arxiv.org/pdf/1505.05571.pdf

[^3_11]: https://en.wikipedia.org/wiki/Summation_algorithm

[^3_12]: https://perso.ens-lyon.fr/elisa.riccietti/doc/slides_M2/summation.pdf

[^3_13]: https://thelinuxcode.com/spherical-trigonometry-for-developers-from-intuition-to-production-ready-geometry/

[^3_14]: https://people.eecs.berkeley.edu/~demmel/AccurateSummation.pdf

[^3_15]: https://www.4rknova.com/blog/2026/04/19/haversine-distance


---

## Objetivo científico

Para una métrica geodésica en $S^{D-1}$, el problema debe separarse en tres capas:

1. cálculo preciso de productos $u_i v_i$;
2. reducción estable y reproducible de esos productos;
3. transformación del resultado algebraico en un ángulo bien condicionado.

La sustitución de Kahan por Neumaier en v911 mejora la primera versión del sumador, pero no alcanza por sí sola el estado del arte. En presencia de cancelación extrema, la solución más sólida es una reducción jerárquica con FMA, expansiones flotantes y, cuando se exige exactitud redondeada, superacumuladores o acumuladores binned reproducibles.

## 1. Neumaier: mejora correcta, garantía limitada

Para sumar $x_1,\dots,x_n$, Neumaier mantiene:

$$
s_{k+1}=\operatorname{fl}(s_k+x_{k+1})
$$

y acumula el residuo elemental según cuál de los operandos tenga mayor magnitud:

$$
c_{k+1}=
\begin{cases}
(s_k-s_{k+1})+x_{k+1}, & |s_k|\ge |x_{k+1}|,\\
(x_{k+1}-s_{k+1})+s_k, & |s_k|<|x_{k+1}|.
\end{cases}
$$

La condición de v911 es la correcta:

```cpp
double t = sum + term;

if (std::abs(sum) >= std::abs(term)) {
    compensation += (sum - t) + term;
} else {
    compensation += (term - t) + sum;
}

sum = t;
```

Pero la frase “contabilidad exacta de los bits descartados” debe restringirse a la suma elemental bajo el modelo de redondeo. La compensación `compensation` también se redondea en cada iteración. Por tanto:

- Neumaier recupera mejor los residuos locales;
- no representa exactamente toda la suma en un formato finito;
- no hace asociativa una reducción paralela;
- no garantiza el mismo resultado si cambia el árbol de reducción.

En vectores antipodales, el problema central es la mala condición:

$$
\kappa
=
\frac{\sum_i |u_i v_i|}
{\left|\sum_i u_i v_i\right|}.
$$

Cuando $u\cdot v\approx -1$ o cuando los términos se cancelan casi por completo, $\kappa$ puede ser enorme. Ningún sumador de precisión fija puede evitar totalmente la amplificación de perturbaciones inherente a esa condición.

## 2. Mejorar el producto antes de sumar

Si la métrica usa un producto punto:

$$
c=\sum_i u_i v_i,
$$

no basta con mejorar la suma. También debe reducirse el error de cada producto $u_i v_i$.

### FMA

La operación FMA calcula:

$$
\operatorname{fma}(u_i,v_i,s)
=
\operatorname{round}(u_i v_i+s)
$$

con un único redondeo, en lugar de redondear primero el producto y después la suma. Esto conserva más información durante la acumulación y es especialmente útil bajo cancelación.[^4_1][^4_2]

Versión rápida:

```cpp
double dot_fma(const double* a, const double* b, std::size_t n) {
    double s = 0.0;

    for (std::size_t i = 0; i < n; ++i) {
        s = std::fma(a[i], b[i], s);
    }

    return s;
}
```

FMA no produce una suma exacta: solo elimina el redondeo intermedio del producto. Tampoco garantiza por sí sola el mejor resultado cuando el sumatorio está muy mal condicionado.

### `TwoProd` con FMA

Para preservar también el error del producto:

```cpp
struct Two {
    double hi;
    double lo;
};

Two two_prod(double a, double b) {
    double hi = a * b;
    double lo = std::fma(a, b, -hi);
    return {hi, lo};
}
```

Idealmente:

$$
hi+lo=a b
$$

exactamente, salvo overflow, underflow o limitaciones del entorno. Los pares `(hi, lo)` pueden acumularse en una expansión flotante. Esta técnica es un componente central de los algoritmos de producto punto exacto o casi exacto.[^4_3]

## 3. Arquitectura recomendada por niveles

### Nivel A: producción de baja latencia

Adecuado para inferencia masiva:

```cpp
float dot_fp32(const half* a, const half* b, std::size_t n) {
    float s = 0.0f;

    for (std::size_t i = 0; i < n; ++i) {
        s = std::fma(static_cast<float>(a[i]),
                     static_cast<float>(b[i]),
                     s);
    }

    return s;
}
```

Mejoras:

- entradas fp16/bf16;
- productos y acumulación en fp32;
- reducción por pares en GPU;
- árbol de reducción fijo si se necesita reproducibilidad aproximada;
- normalización previa de los vectores;
- evaluación angular con `atan2`.


### Nivel B: alta precisión

- productos `TwoProd`;
- expansión de 2–4 componentes;
- suma por pares de expansiones;
- resultado final en fp64;
- FMA en cada combinación.

Este nivel ofrece una mejora grande frente a Neumaier con coste moderado.

### Nivel C: reproducibilidad estricta

Usar un acumulador binned o un superacumulador:

- todos los summands se depositan en bins definidos por exponente;
- el resultado no depende del orden;
- la reducción paralela puede ser asociativa a nivel de la representación;
- el redondeo se realiza al final.

ReproBLAS utiliza una representación reproducible de pocos números de punto flotante y garantiza resultados independientes del orden de suma bajo sus supuestos de rango. ExBLAS combina expansiones, filtrado y superacumuladores de Kulisch para obtener operaciones BLAS reproducibles y precisas, incluido el producto punto.[^4_4][^4_5][^4_6][^4_7][^4_8]

### Nivel D: exactitud redondeada

Para resultados auditables:

1. representar cada producto exactamente mediante `TwoProd`;
2. insertar el resultado y el error en una expansión;
3. transferir expansiones a un superacumulador;
4. realizar la reducción paralela;
5. redondear una sola vez al formato solicitado.

Este es el nivel apropiado si la distancia se usa en:

- validación científica;
- generación de datos de referencia;
- pruebas de regresión numérica;
- decisiones discretas cerca de umbrales;
- comparación bit a bit entre hardware.

Los superacumuladores están diseñados precisamente para representar la suma exacta de números flotantes antes del redondeo final.[^4_9][^4_10][^4_11]

## 4. El producto punto no debe convertirse directamente con `acos`

Después de calcular:

$$
c=u\cdot v,
$$

la fórmula:

$$
\theta=\arccos(c)
$$

está mal condicionada cerca de $c=\pm1$, porque:

$$
|\arccos'(c)|
=
\frac{1}{\sqrt{1-c^2}}.
$$

La estabilidad del sumador no elimina esta singularidad de la función posterior.

### Representación con `atan2`

Para vectores unitarios:

$$
\theta
=
\operatorname{atan2}
\left(
\sqrt{1-c^2},
c
\right).
$$

En dimensión 3 puede usarse:

$$
\theta=
\operatorname{atan2}(\|u\times v\|,u\cdot v).
$$

Una representación más robusta en $S^{D-1}$ es:

$$
\boxed{
\theta
=
2\operatorname{atan2}
\left(
\frac{\|u-v\|}{2},
\frac{\|u+v\|}{2}
\right)
}
$$

para $u$ y $v$ normalizados.

Su ventaja es geométrica:

- cerca de $u=v$, $\|u-v\|$ es pequeña y la fórmula conserva la separación;
- cerca de $u=-v$, $\|u+v\|$ es pequeña y evita restar dos números cercanos en $1-c$;
- `atan2` trata conjuntamente ambos argumentos y evita la división explícita.

Implementación conceptual:

```cpp
double spherical_angle(const Vec& u, const Vec& v) {
    double dm2 = stable_norm2(u - v);
    double dp2 = stable_norm2(u + v);

    dm2 = std::max(dm2, 0.0);
    dp2 = std::max(dp2, 0.0);

    return 2.0 * std::atan2(std::sqrt(dm2), std::sqrt(dp2));
}
```

Para vectores no perfectamente normalizados, usar:

$$
\theta =
2\operatorname{atan2}
\left(
\|u/\|u\|-v/\|v\|\|,
\|u/\|u\|+v/\|v\||
\right).
$$

La normalización también debe calcularse de manera estable.

## 5. Distancias $\|u-v\|$ y $\|u+v\|$

Calcular directamente:

```cpp
sum += (u[i] - v[i]) * (u[i] - v[i]);
```

puede fallar si `u[i]` y `v[i]` tienen escalas extremas. Una versión robusta combina escalado por máximo y suma compensada:

$$
\|w\|^2
=
m^2\sum_i \left(\frac{w_i}{m}\right)^2,
\qquad
m=\max_i |w_i|.
$$

Pseudocódigo:

```cpp
double stable_norm2(const Vec& w) {
    double m = 0.0;

    for (double x : w) {
        m = std::max(m, std::abs(x));
    }

    if (m == 0.0) {
        return 0.0;
    }

    NeumaierAccumulator acc;

    for (double x : w) {
        double z = x / m;
        acc.add(z * z);
    }

    return (m * m) * acc.value();
}
```

Si $m^2$ puede desbordar, mantener la norma en forma escalada o logarítmica:

$$
\log\|w\|
=
\log m+
\frac12\log\left(\sum_i(w_i/m)^2\right).
$$

Para vectores unitarios habituales, la ruta fp64 normal suele ser suficiente; para el modo científico, se recomienda una versión escalada con expansión o superacumulador.

## 6. Cuidado con la normalización

Antes del producto punto, es frecuente realizar:

$$
\hat u=\frac{u}{\|u\|},
\qquad
\hat v=\frac{v}{\|v\|}.
$$

Si la norma se calcula con error, incluso un producto punto exacto posterior puede quedar fuera del intervalo $[-1,1]$.

La norma debe calcularse mediante:

- `hypot` escalado;
- `norm` estable de BLAS;
- reducción fp32/fp64;
- sumador compensado para dimensiones grandes;
- rechazo explícito de vectores de norma cero o no finitos.

No conviene normalizar con:

```cpp
sqrt(dot(u, u))
```

si `dot` se ejecuta en una precisión inferior o con cuadrados que pueden desbordar.

## 7. Clamping y diagnóstico

El `clamp` final es obligatorio como defensa:

```cpp
c = std::clamp(c, -1.0, 1.0);
```

Pero debe interpretarse como un indicador de fallo potencial, no como solución primaria. Registrar:

- cuántas veces $c>1$;
- cuántas veces $c<-1$;
- máximo exceso sobre el intervalo;
- norma de $u$ y $v$;
- condición estimada del producto punto.

Si el producto punto excede sistemáticamente el intervalo, las causas probables son:

- vectores no normalizados;
- acumulación fp16/bf16;
- reducción no determinista;
- overflow intermedio;
- error acumulado en el cálculo de normas;
- uso de una fórmula angular inadecuada.


## 8. Algoritmo SOTA propuesto

### Ruta rápida

```text
1. Convertir entradas a fp32.
2. Calcular normas con reducción estable.
3. Normalizar.
4. Calcular:
      dm2 = ||u - v||²
      dp2 = ||u + v||²
   mediante FMA y suma por pares.
5. Evaluar:
      theta = 2 atan2(sqrt(dm2), sqrt(dp2)).
6. Aplicar clamp a dm2 y dp2 antes de sqrt.
```


### Ruta precisa

```text
1. Convertir a fp64.
2. Calcular normas con Neumaier o expansión.
3. Normalizar.
4. Calcular cada cuadrado mediante FMA o TwoProd.
5. Acumular en expansión flotante.
6. Combinar por árbol determinista.
7. Evaluar atan2.
8. Comparar contra una referencia fp128 o multiprecisión.
```


### Ruta exacta/reproducible

```text
1. Convertir cada producto a una representación exacta.
2. Insertarlo en un acumulador binned/superacumulador.
3. Reducir acumuladores de forma asociativa.
4. Redondear una única vez.
5. Evaluar la transformación angular con argumentos no negativos y escalados.
6. Emitir también un intervalo o cota de error.
```


## 9. Cotas y pruebas científicas

### Prueba de permutación

Para un mismo vector de términos, permutar aleatoriamente el orden $10^3$ veces:

- Kahan suele producir dispersión apreciable en casos mal condicionados;
- Neumaier reduce la dispersión;
- una suma por pares fija reduce aún más la variabilidad;
- ReproBLAS/ExBLAS debe producir exactamente el mismo resultado.


### Prueba antipodal

Construir:

$$
v=-u+\delta,
$$

renormalizar y variar:

$$
\|\delta\|\in
\{10^{-2},10^{-4},10^{-8},10^{-12},10^{-16}\}.
$$

Medir:

$$
|\theta_{\mathrm{alg}}-\theta_{\mathrm{ref}}|.
$$

La métrica relevante cerca de $\pi$ es el error angular absoluto. El error relativo deja de ser informativo porque $\theta$ no se aproxima a cero.

### Prueba de escala

Usar:

$$
u=s\hat u,\qquad v=t\hat v
$$

con $s,t$ desde subnormales hasta valores cercanos al overflow. Verificar que la normalización y el resultado angular sean invariantes respecto a escala.

### Prueba de reproducibilidad

Ejecutar:

- CPU scalar;
- CPU SIMD;
- GPU;
- diferentes tamaños de bloque;
- distintas semillas de ordenamiento.

Comparar el resultado bit a bit en modo reproducible y mediante tolerancias en modo rápido.

### Referencia

Usar precisión extendida:

- `long double`, si ofrece precisión real superior;
- double-double;
- MPFR o equivalente;
- superacumulador exacto para productos y sumas.

La referencia no debe ser otra implementación con el mismo árbol de errores.

## 10. Propuesta v911

Una especificación científicamente sólida para la siguiente versión sería:

> v911 reemplaza la reducción lineal compensada por una arquitectura jerárquica configurable: FMA y acumulación fp32/fp64 para el modo rápido; suma por pares con Neumaier por bloque para alta estabilidad; expansiones `TwoProd/TwoSum` para alta precisión; y acumulación binned o superacumulador para reproducibilidad bit a bit. La distancia sobre $S^{D-1}$ se evalúa mediante $2\operatorname{atan2}(\|u-v\|,\|u+v\|)$, evitando la dependencia singular de `acos` cerca de configuraciones coincidentes y antipodales.

## Veredicto

v911 es correcta como corrección local de Kahan, pero no debe considerarse la solución definitiva para tensores antipodales. La mejora SOTA exige resolver simultáneamente:

- error del producto;
- error de la reducción;
- orden de reducción paralelo;
- mala condición geométrica;
- estabilidad de la conversión a ángulo.

La mejor relación precisión/rendimiento suele ser:

$$
\boxed{
\text{FMA}
+
\text{reducción por pares}
+
\text{Neumaier por bloque}
+
\operatorname{atan2}
}
$$

Para exactitud científica y reproducibilidad:

$$
\boxed{
\text{TwoProd/TwoSum}
+
\text{expansión}
+
\text{superacumulador binned}
+
\operatorname{atan2}
}
$$

ReproBLAS y ExBLAS proporcionan referencias relevantes para construir reducciones reproducibles y precisas independientes del orden de suma.[^4_5][^4_7][^4_4]

<span style="display:none">[^4_12][^4_13][^4_14][^4_15][^4_16][^4_17][^4_18][^4_19][^4_20][^4_21][^4_22][^4_23][^4_24][^4_25][^4_26][^4_27][^4_28][^4_29][^4_30][^4_31][^4_32][^4_33]</span>

<div align="center">⁂</div>

[^4_1]: https://docs.nvidia.com/cuda/floating-point/index.html

[^4_2]: https://docs.nvidia.com/cuda/archive/12.3.0/floating-point/index.html

[^4_3]: https://web.stanford.edu/group/SOL/software/qdotdd/IC2012.pdf

[^4_4]: https://www.siam.org/publications/siam-news/articles/reproducible-blas-make-addition-associative-again/

[^4_5]: https://bebop.cs.berkeley.edu/reproblas/

[^4_6]: https://www.nist.gov/system/files/documents/itl/ssd/is/NRE-2015-04-iakymchuk.pdf

[^4_7]: https://hal.science/hal-01202396v3/document

[^4_8]: https://hal.science/hal-01456307/document

[^4_9]: https://hal.science/hal-00949355v1/preview/superaccumulator.pdf

[^4_10]: https://arxiv.org/html/2312.10247v1

[^4_11]: http://arxiv.org/pdf/1505.05571.pdf

[^4_12]: https://www2.eecs.berkeley.edu/Pubs/TechRpts/2015/Archive/EECS-2015-229.pdf

[^4_13]: https://www.netlib.org/utk/people/JackDongarra/WEB-PAGES/Batched-BLAS-2016/Day1/10_Demmel_ReproBLAS.pdf

[^4_14]: https://hal.science/hal-01539180/document

[^4_15]: https://riunet.upv.es/bitstreams/275bedd3-1c58-4020-b73e-fbe7ac85cb30/download

[^4_16]: https://github.com/willow-ahrens/ReproBLAS

[^4_17]: https://bebop.cs.berkeley.edu/reproblas/docs/talks/SIAM_AN13.pdf

[^4_18]: https://bebop.cs.berkeley.edu/reproblas/docs/talks/SC13.pdf

[^4_19]: https://people.eecs.berkeley.edu/~demmel/ma221_Fall23/Lectures/Lecture_02.txt

[^4_20]: https://www.diva-portal.org/smash/get/diva2:1990191/FULLTEXT01.pdf

[^4_21]: https://inria.hal.science/hal-00695333/document

[^4_22]: https://www.computer.org/csdl/journal/tc/2024/06/10454250/1UVOtO916Te

[^4_23]: https://docs.nvidia.com/cuda/pdf/Floating_Point_on_NVIDIA_GPU.pdf

[^4_24]: https://docs.nvidia.com/cuda/archive/12.9.0/pdf/Floating_Point_on_NVIDIA_GPU.pdf

[^4_25]: https://ieeexplore.ieee.org/document/10461456

[^4_26]: https://docs.nvidia.com/cuda/archive/12.9.2/pdf/Floating_Point_on_NVIDIA_GPU.pdf

[^4_27]: https://indico.cern.ch/event/626147/attachments/1456066/2247140/FloatingPoint.Handout.pdf

[^4_28]: https://en.wikipedia.org/wiki/Multiply–accumulate_operation

[^4_29]: https://indico.cern.ch/event/166141/sessions/125684/attachments/201414/282782/Arnold-FPWorkshop-Print.pdf

[^4_30]: https://members.loria.fr/PZimmermann/talks/module1.pdf

[^4_31]: https://www-users.cse.umn.edu/~vinals/tspot_files/phys4041/2020/IEEE%20Standard%20754-2019.pdf

[^4_32]: https://accurate-algorithms.readthedocs.io/en/latest/ch03fma.html

[^4_33]: https://hal.science/hal-00949355v2/file/superaccumulator.pdf


---

## Evaluación de v911

La migración desde un array fijo de $256\times384$ hacia un `thread_local std::vector<double>` persistente elimina un problema real: el límite artificial $K\le128$ y las reasignaciones repetidas en la ruta caliente. Como optimización de CPU, es una mejora razonable; sin embargo, hay dos correcciones conceptuales importantes:

1. `thread_local` evita normalmente la realocación por hilo, pero **no elimina necesariamente toda interacción con el allocator**: la primera ampliación puede asignar memoria y un crecimiento posterior puede volver a realocar.
2. Una llamada a `malloc/free` del host no “satura el bus PCIe” por sí misma. El impacto típico es latencia de allocator, sincronización, presión sobre el runtime y posibles stalls de lanzamiento; PCIe solo entra directamente si se realizan transferencias host-device o si la gestión de memoria induce sincronizaciones.

Los allocators thread-local reducen la contención porque satisfacen muchas peticiones desde cachés locales, pero no sustituyen a un arena/pool explícito cuando la ruta es paralela, heterogénea o GPU-residente.[^5_1]

## 1. Limitaciones de `thread_local std::vector`

La solución:

```cpp
thread_local std::vector<double> workspace;
workspace.resize(required_size);
```

es segura solo bajo determinadas condiciones.

### Ventajas

- persistencia durante la vida del hilo;
- amortización de la primera reserva;
- ausencia de `free` por iteración;
- aislamiento entre hilos;
- eliminación del límite fijo de $K$;
- implementación sencilla.


### Riesgos

#### Crecimiento repetido

Si `required_size` aumenta gradualmente, `resize` puede provocar varias realocaciones. Aunque `std::vector` conserva capacidad cuando el nuevo tamaño es menor o igual que `capacity()`, la capacidad no está garantizada para cubrir los futuros tamaños.

Debe usarse:

```cpp
if (workspace.capacity() < required_size) {
    workspace.reserve(required_size);
}
workspace.resize(required_size);
```

Mejor aún, aplicar crecimiento geométrico:

```cpp
if (workspace.capacity() < required_size) {
    std::size_t new_cap = workspace.capacity() ? workspace.capacity() : 1024;

    while (new_cap < required_size) {
        new_cap = new_cap + new_cap / 2;
    }

    workspace.reserve(new_cap);
}

workspace.resize(required_size);
```

Esto reduce las ampliaciones, aunque aumenta el consumo máximo de memoria.

#### Retención indefinida

El buffer permanece asociado al hilo hasta que termina. En un pool de hilos persistente, un único caso extremo puede hacer que la memoria quede retenida durante toda la ejecución.

Opciones:

- mantener capacidad alta si el patrón es estable;
- liberar explícitamente después de una fase:

```cpp
std::vector<double>().swap(workspace);
```

- usar un límite de retención;
- devolver buffers a un pool global por tamaño.


#### Contención y afinidad

`thread_local` evita compartir el buffer, pero puede ser costoso si:

- se crean y destruyen muchos hilos;
- el runtime migra trabajo entre hilos;
- el número de hilos cambia;
- una tarea usa un hilo distinto en cada iteración.

En estos casos, un workspace asociado a la tarea o a un contexto de ejecución puede ser más estable que uno asociado al hilo físico.

#### Reentrada

Si una función puede invocarse recursivamente o ejecutarse de forma reentrante en el mismo hilo, un único buffer `thread_local` puede ser sobrescrito. Para código reentrante conviene usar:

- un objeto workspace pasado explícitamente;
- un stack de arenas;
- buffers con niveles de nesting;
- una política de préstamo con ownership claro.


## 2. Mejora inmediata: workspace explícito

La primera evolución recomendada es separar la propiedad del buffer de la función numérica:

```cpp
struct Workspace {
    std::vector<double> data;

    void ensure(std::size_t n) {
        if (data.capacity() < n) {
            data.reserve(n);
        }
        data.resize(n);
    }
};
```

Luego:

```cpp
void cayley_smw(const Matrix& X, Workspace& ws) {
    const std::size_t required = compute_workspace_size(X);
    ws.ensure(required);

    // Usar ws.data.data()
}
```

Ventajas:

- permite instrumentar memoria;
- facilita pruebas;
- permite reutilización entre varias operaciones;
- evita dependencias ocultas;
- hace explícita la concurrencia;
- permite elegir allocator por backend.

Se puede conservar una fachada thread-local:

```cpp
Workspace& default_workspace() {
    thread_local Workspace ws;
    return ws;
}
```

Así se obtiene comodidad sin ocultar la abstracción.

## 3. Mejor opción CPU: arena monotónica

Para la ruta caliente, una arena monotónica evita muchas asignaciones pequeñas y permite liberar todo de una sola vez:

```cpp
class Arena {
public:
    explicit Arena(std::size_t initial)
        : buffer_(initial), offset_(0) {}

    void reset() noexcept {
        offset_ = 0;
    }

    double* allocate_doubles(std::size_t n) {
        const std::size_t alignment = alignof(double);
        std::size_t start = (offset_ + alignment - 1) &
                            ~(alignment - 1);
        std::size_t bytes = n * sizeof(double);

        if (start + bytes > buffer_.size()) {
            grow(start + bytes);
        }

        auto* ptr = reinterpret_cast<double*>(buffer_.data() + start);
        offset_ = start + bytes;
        return ptr;
    }

private:
    std::vector<std::byte> buffer_;
    std::size_t offset_;

    void grow(std::size_t required) {
        std::size_t next = buffer_.size() ? buffer_.size() : 4096;
        while (next < required) {
            next += next / 2;
        }
        buffer_.resize(next);
    }
};
```

Uso:

```cpp
thread_local Arena arena{1 << 20};

arena.reset();

double* dyn_aug = arena.allocate_doubles(required_size);
double* temp = arena.allocate_doubles(other_size);
```

Esta estrategia es adecuada cuando:

- los temporales viven hasta el final de una iteración;
- se pueden liberar colectivamente;
- no se necesita liberar objetos individuales;
- el patrón de vida es tipo stack/arena.

Debe prestarse atención a la alineación, al overflow de `n * sizeof(double)` y a la invalidación de punteros si la arena crece.

## 4. Pool por clases de tamaño

Si los buffers tienen vidas distintas, una arena monotónica puede desperdiciar memoria. En ese caso, usar clases de tamaño:

$$
2^k,\;2^{k+1},\;2^{k+2},\ldots
$$

Ejemplo conceptual:

```cpp
class BufferPool {
public:
    double* acquire(std::size_t n);
    void release(double* ptr, std::size_t capacity);
};
```

Cada solicitud se redondea a una clase:

```cpp
std::size_t bucket(std::size_t n) {
    std::size_t p = 1;
    while (p < n) p <<= 1;
    return p;
}
```

Ventajas:

- reutilización rápida;
- pocas realocaciones;
- control del crecimiento;
- menor fragmentación externa.

Desventaja:

- fragmentación interna: un buffer de 129 elementos puede recibir capacidad 256;
- requiere ownership y sincronización;
- debe limitarse la retención de buffers raros o gigantes.

Para reducir fragmentación, usar bins geométricos más finos, por ejemplo:

$$
1.125^k
\quad\text{o}\quad
1.25^k,
$$

en lugar de potencias de dos estrictas.

## 5. CPU moderna: allocator y afinidad

Para muchas tareas concurrentes:

- `std::pmr::monotonic_buffer_resource` puede centralizar la política;
- `unsynchronized_pool_resource` sirve si cada pool pertenece a un solo hilo;
- `synchronized_pool_resource` permite compartir, pero añade contención;
- `jemalloc`, `mimalloc` o `tcmalloc` pueden mejorar el comportamiento general, aunque deben medirse en el workload real.

La regla es:

- **un propietario por hilo:** arena no sincronizada;
- **buffers reutilizados entre hilos:** pool sincronizado o ownership transferido;
- **reducir al mínimo el sharing:** preferible al allocator global con locks.

La afinidad importa: si el hilo que reserva el buffer no es el que lo reutiliza, se pierde parte de la ventaja de `thread_local`.

## 6. Si el cuello está en GPU, v911 no es suficiente

Si la retracción Cayley-SMW se ejecuta en GPU o tiene temporales residentes en device, un `thread_local std::vector<double>` es un mecanismo de memoria host y no resuelve el allocator de device.

Para CUDA, la solución moderna es usar memoria preasignada o un memory pool. `cudaMallocAsync` y `cudaFreeAsync` son operaciones ordenadas por stream; los memory pools permiten reutilizar bloques, evitar sincronizaciones globales y reducir fragmentación.[^5_2][^5_3][^5_4]

Patrón:

```cpp
cudaMemPool_t pool;
cudaDeviceGetDefaultMemPool(&pool, device);

cudaStream_t stream;
cudaStreamCreate(&stream);

double* ptr = nullptr;
cudaMallocAsync(&ptr, bytes, stream);

// kernels que usan ptr

cudaFreeAsync(ptr, stream);
```

Pero no debe llamarse a `cudaMallocAsync` por elemento o por micro-operación. Lo recomendable es:

1. reservar un pool o arena por iteración/stream;
2. subasignar internamente;
3. reutilizar durante toda la época;
4. liberar o reciclar solo al finalizar el stream correspondiente.

CUDA documenta que los pools reducen el coste de asignación y deallocación y mejoran la reutilización; además, la desfragmentación virtual puede reorganizar páginas del pool sin cambiar las direcciones virtuales observadas por el kernel.[^5_5][^5_2]

## 7. Diferenciar CPU, GPU y PCIe

La descripción de V907 mezcla tres cuellos potenciales:


| Fenómeno | Causa | Síntoma |
| :-- | :-- | :-- |
| Fragmentación | Muchos tamaños y ciclos de vida | RSS/VRAM creciente, fallos de reserva |
| Latencia del allocator | `malloc/free`, locks, syscalls | jitter en iteraciones |
| Transferencia PCIe | Copias host-device | bajo ancho de banda, stalls de stream |
| Sincronización | `cudaFree`, `cudaMemcpy`, fences | kernels esperando al host |
| Presión de caché/TLB | muchos buffers dispersos | más fallos de caché y page walks |

Un `malloc/free` de host no implica automáticamente tráfico PCIe. Para diagnosticarlo, medir por separado:

- tiempo de asignación;
- tiempo de kernel;
- tiempo de `memcpy`;
- sincronizaciones host-device;
- bytes transferidos por PCIe;
- page faults;
- actividad del allocator;
- memoria residente y fragmentación.

Herramientas recomendadas:

- CPU: `perf`, VTune, heaptrack, Massif, allocator statistics;
- CUDA: Nsight Systems, Nsight Compute, CUPTI;
- memoria: métricas de pool, `cudaMemPoolGetAttribute`, RSS, `/proc`;
- trazas: rangos NVTX alrededor de reserva, copia y kernel.


## 8. Geometría del workspace SMW

La retracción de Cayley con Sherman–Morrison–Woodbury suele trabajar con matrices pequeñas asociadas al rango o a la dimensión de la actualización. En forma abstracta, el coste puede contener términos como:

$$
O(nK^2+K^3),
$$

dependiendo de la variante y de cómo se factorice la matriz pequeña. La literatura sobre actualizaciones que preservan restricciones de Stiefel analiza precisamente costes del tipo $np^2$ y $p^3$ para formar la actualización.[^5_6]

Esto significa que eliminar `malloc/free` puede no ser el cuello dominante cuando $K$ crece: el coste algebraico $O(K^3)$, las cargas de memoria y la factorización pueden dominar.

Por ello, la optimización debe separar:

1. coste de asignación;
2. bytes movidos;
3. FLOPs de SMW;
4. ocupación y registros;
5. coste de sincronización;
6. coste de la factorización $K\times K$.

Un workspace ilimitado puede eliminar el jitter, pero también producir:

- presión de caché;
- más tráfico DRAM;
- spills de registros;
- menor ocupación GPU;
- mayor tiempo de inicialización;
- retención de memoria de casos excepcionales.


## 9. Estructura de workspace recomendada

En lugar de un único vector monolítico, describir las regiones por offsets:

```cpp
struct CayleyWorkspace {
    std::vector<double> storage;
    std::size_t aug_offset = 0;
    std::size_t rhs_offset = 0;
    std::size_t factor_offset = 0;
    std::size_t temp_offset = 0;

    void ensure(std::size_t total) {
        if (storage.capacity() < total) {
            storage.reserve(total);
        }
        storage.resize(total);
    }

    double* aug() {
        return storage.data() + aug_offset;
    }

    double* rhs() {
        return storage.data() + rhs_offset;
    }
};
```

Ventajas:

- una sola reserva;
- regiones contiguas;
- menos metadatos;
- mejor localidad;
- facilidad para reutilizar buffers con vidas no solapadas.

Si dos temporales nunca están vivos simultáneamente, pueden compartir la misma región. Esta técnica de análisis de vidas puede reducir el pico de memoria sustancialmente.

## 10. Dimensionamiento adaptativo

No conviene simplemente hacer `resize(required_size)` sin política de capacidad. Usar:

$$
C_{\text{nuevo}}
=
\max\left(
C_{\text{mínimo}},
\left\lceil \alpha\,R\right\rceil
\right),
$$

donde:

- $R$ es el requerimiento actual;
- $C$ es la capacidad;
- $\alpha\in[1.1,2]$ es el margen;
- $C_{\text{mínimo}}$ evita pequeñas reservas sucesivas.

Ejemplo:

```cpp
void ensure(std::size_t required) {
    if (required <= data.capacity()) {
        data.resize(required);
        return;
    }

    constexpr double growth = 1.5;
    std::size_t target = static_cast<std::size_t>(
        std::ceil(growth * static_cast<double>(required))
    );

    data.reserve(target);
    data.resize(required);
}
```

Para un swarm donde $K$ cambia con frecuencia, puede usarse una tabla de capacidades por clase de $K$, en vez de crecer para cada valor.

## 11. Manejo de excepciones y límites

La eliminación del límite artificial $K\le128$ no implica que todo $K$ deba aceptarse.

Antes de multiplicar tamaños:

```cpp
if (K > std::numeric_limits<std::size_t>::max() / K) {
    throw std::overflow_error("K^2 overflow");
}
```

Y para $nK^2$:

```cpp
bool checked_mul(std::size_t a, std::size_t b, std::size_t& out) {
    if (a != 0 && b > std::numeric_limits<std::size_t>::max() / a) {
        return false;
    }
    out = a * b;
    return true;
}
```

También conviene establecer:

- límite máximo de memoria por worker;
- fallback a procesamiento por bloques;
- rechazo explícito de `K` que no quepa en presupuesto;
- telemetría de la capacidad máxima observada.

La solución correcta no es convertir un límite estático en una posible reserva ilimitada.

## 12. Fallback por bloques para $K$ grande

Si $K$ excede la memoria local, procesar la operación por bloques:

$$
K=K_1+K_2+\cdots+K_m.
$$

Esto puede evitar un workspace $O(K^2)$ completo, aunque depende de si la fórmula SMW permite particionar la actualización sin cambiar la semántica.

Alternativas:

- factorizar por paneles;
- usar una representación low-rank comprimida;
- recomputar temporales baratos en vez de almacenarlos;
- separar workspace de lectura y escritura;
- usar out-of-core solo como último recurso.

El criterio debe ser comparar:

$$
T_{\text{recompute}}
\quad\text{vs}\quad
T_{\text{memory}}.
$$

En arquitecturas modernas, recomputar una operación pequeña puede ser más barato que mover un buffer grande por memoria o PCIe.

## 13. Estrategia SOTA para CPU

### Configuración recomendada

- un `Workspace` por worker;
- arena monotónica para temporales de una iteración;
- una reserva geométrica inicial;
- alineación de 64 bytes para SIMD;
- memoria contigua;
- sin `malloc/free` en la ruta caliente;
- pinning o afinidad de hilos si el runtime lo permite;
- métricas de capacidad, crecimiento y tiempo de reserva.

```cpp
struct alignas(64) WorkerWorkspace {
    std::pmr::monotonic_buffer_resource arena;
    std::pmr::vector<double> buffers;

    WorkerWorkspace(void* initial, std::size_t bytes)
        : arena(initial, bytes),
          buffers(&arena) {}
};
```

Si se desea reutilización sin reconstruir el objeto:

```cpp
arena.release();
```

La arena puede conservar o no el almacenamiento inicial, según el recurso upstream.

## 14. Estrategia SOTA para GPU

- preasignar workspace por stream;
- usar `cudaMemPool_t`;
- preferir `cudaMallocAsync`/`cudaFreeAsync` frente a asignaciones globales antiguas;
- subasignar buffers dentro de una región;
- mantener el `releaseThreshold` suficientemente alto para reutilización;
- evitar transferencias host-device de temporales;
- usar memoria unificada solo si el patrón de acceso está demostrado;
- medir fragmentación y sincronizaciones.

La documentación de CUDA especifica que la vida de la asignación debe respetar el orden del stream: todos los accesos deben quedar entre la asignación y la liberación correspondiente.[^5_4]

## 15. Benchmark científico

No basta con comparar el tiempo total de la época. Medir:

$$
T_{\text{total}}
=
T_{\text{alloc}}
+
T_{\text{copy}}
+
T_{\text{kernel}}
+
T_{\text{sync}}
+
T_{\text{other}}.
$$

Para cada configuración:

- V907: array fijo y fallback dinámico;
- v911: `thread_local vector`;
- v911-A: workspace explícito;
- v911-B: arena monotónica;
- v911-C: pool por clases;
- v911-D: memory pool CUDA, si aplica.

Recoger:

- media;
- p50;
- p95;
- p99;
- máximo;
- desviación estándar;
- número de realocaciones;
- bytes reservados;
- memoria retenida;
- throughput;
- tiempo de kernel;
- tiempo de transferencia;
- ocupación;
- fallos de caché/TLB.

El objetivo principal no es únicamente bajar la media: es reducir la cola p99 y el jitter, porque las reservas esporádicas suelen aparecer como outliers.

## Veredicto

v911 es una mejora válida para el caso CPU y elimina de forma efectiva la realocación repetida después del primer crecimiento, pero debe formalizarse mejor:

- `thread_local` no garantiza reserva única para tamaños crecientes;
- la capacidad puede quedar retenida indefinidamente;
- no es una solución universal para GPU;
- `malloc/free` no equivale automáticamente a saturación de PCIe;
- eliminar el límite $K\le128$ puede trasladar el cuello al coste $O(K^2)$, $O(K^3)$, caché o memoria.

La solución SOTA recomendada es jerárquica:

$$
\boxed{
\text{workspace explícito}
+
\text{arena/pool por worker}
+
\text{crecimiento geométrico}
+
\text{subasignación contigua}
}
$$

y, para GPU:

$$
\boxed{
\text{memory pool por stream}
+
\texttt{cudaMallocAsync}
+
\text{reutilización ordenada}
}
$$

La formulación más precisa para v911 sería:

> Se sustituye el almacenamiento fijo por un sistema de workspaces persistentes y dimensionamiento adaptativo. Cada worker obtiene una arena contigua reutilizable, con crecimiento geométrico, límites de memoria, detección de overflow y telemetría de realocaciones. En GPU se utiliza un pool ordenado por stream. Esto elimina asignaciones de la ruta caliente, reduce el jitter y evita el límite artificial de $K$, sin convertir el crecimiento dinámico en una reserva ilimitada.

<span style="display:none">[^5_10][^5_11][^5_12][^5_13][^5_14][^5_15][^5_7][^5_8][^5_9]</span>

<div align="center">⁂</div>

[^5_1]: https://www.cs.rochester.edu/u/scott/papers/2020_ISMM_Ralloc.pdf

[^5_2]: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^5_3]: https://docs.nvidia.com/cuda/archive/13.4.1/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^5_4]: https://docs.nvidia.com/cuda/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^5_5]: https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/

[^5_6]: https://link.springer.com/article/10.1007/s10107-014-0816-7?error=cookies_not_supported\&code=ce3d1e58-16c3-46fc-ad03-662d18a927d0

[^5_7]: https://docs.pytorch.org/docs/main/notes/cuda.html

[^5_8]: https://www.cs.utexas.edu/~witchel/pubs/ni26asplos-cxlalloc.pdf

[^5_9]: https://sigops.org/s/conferences/hotos/2023/papers/li.pdf

[^5_10]: https://research.nvidia.com/sites/default/files/pubs/2019-02_Throughput-oriented-GPU-memory/paper.pdf

[^5_11]: https://moldstud.com/articles/p-best-practices-for-effective-cuda-resource-management-optimize-performance-and-efficiency

[^5_12]: https://intro-to-cuda.readthedocs.io/en/latest/tutorial/mempool.html

[^5_13]: https://www.alphaxiv.org/abs/2002.01113v1

[^5_14]: https://deepwiki.com/NVlabs/tiny-cuda-nn/2.1-memory-management

[^5_15]: https://github.com/rapidsai/rmm/issues/1694


---

## Diagnóstico refinado

v911 elimina el síntoma principal —reservas repetidas durante la iteración—, pero la solución científicamente completa debe modelar el problema como una combinación de:

$$
\text{latencia de asignación}
+
\text{fragmentación}
+
\text{localidad}
+
\text{sincronización}
+
\text{presión de memoria}.
$$

Un `thread_local std::vector<double>` es una caché persistente, no un allocator especializado. Funciona bien si cada hilo ejecuta una secuencia estable de tamaños y si los temporales viven hasta el final de la iteración. No es necesariamente óptimo cuando hay múltiples fases con vidas solapadas, tamaños muy variables, GPU o ejecución asíncrona.

La investigación reciente sobre allocators regionales muestra precisamente que las arenas reducen la fragmentación porque colocan objetos contiguamente y liberan regiones completas, en vez de liberar objetos individuales.[^6_1]

## 1. Modelo de coste

Para una iteración $t$, modelar:

$$
T_t =
T_{\text{alloc},t}
+
T_{\text{init},t}
+
T_{\text{copy},t}
+
T_{\text{SMW},t}
+
T_{\text{sync},t}.
$$

El objetivo de v911 es reducir $T_{\text{alloc}}$, pero puede aumentar:

- $T_{\text{init}}$, si el workspace se sobredimensiona;
- $T_{\text{cache}}$, por buffers demasiado grandes;
- $T_{\text{memory}}$, por regiones no reutilizadas;
- $T_{\text{SMW}}$, si un layout peor reduce la localidad.

Además, la varianza importa. Para un swarm paralelo, una métrica más informativa que la media es:

$$
\mathrm{Jitter}
=
P_{99}(T_t)-P_{50}(T_t).
$$

Un allocator persistente suele mejorar mucho el p99 incluso cuando la media cambia poco.

## 2. Arquitectura recomendada: tres niveles

### Nivel 1: caché de workspace por worker

Mantener un buffer persistente por worker, pero con una interfaz explícita:

```cpp
class Workspace {
public:
    void ensure(std::size_t required) {
        if (required <= storage_.capacity()) {
            size_ = required;
            return;
        }

        std::size_t next = storage_.capacity();
        if (next == 0) next = 4096;

        while (next < required) {
            next = next + next / 2;
        }

        storage_.reserve(next);
        size_ = required;
    }

    double* data() noexcept {
        return storage_.data();
    }

    std::size_t size() const noexcept {
        return size_;
    }

    std::size_t capacity() const noexcept {
        return storage_.capacity();
    }

private:
    std::vector<double> storage_;
    std::size_t size_ = 0;
};
```

Uso:

```cpp
Workspace& workspace_for_worker() {
    thread_local Workspace ws;
    return ws;
}
```

Esto mejora v911 porque diferencia:

- tamaño lógico actual;
- capacidad reservada;
- política de crecimiento;
- telemetría;
- ownership.


### Nivel 2: arena por iteración

Si Cayley-SMW crea varios temporales, un único `vector` lógico no basta. Una arena permite subasignar regiones consecutivas y reiniciarlas con coste constante:

```cpp
class BumpArena {
public:
    explicit BumpArena(std::size_t initial)
        : storage_(initial), offset_(0) {}

    void reset() noexcept {
        offset_ = 0;
    }

    double* allocate(std::size_t count) {
        if (count > (std::numeric_limits<std::size_t>::max() /
                     sizeof(double))) {
            throw std::overflow_error("workspace size overflow");
        }

        std::size_t bytes = count * sizeof(double);
        std::size_t aligned =
            (offset_ + alignof(double) - 1) &
            ~(alignof(double) - 1);

        ensure_bytes(aligned + bytes);

        auto* result =
            reinterpret_cast<double*>(storage_.data() + aligned);

        offset_ = aligned + bytes;
        return result;
    }

private:
    std::vector<std::byte> storage_;
    std::size_t offset_;

    void ensure_bytes(std::size_t required) {
        if (required <= storage_.size()) return;

        std::size_t next = storage_.size();
        if (next == 0) next = 4096;

        while (next < required) {
            next += next / 2;
        }

        storage_.resize(next);
    }
};
```

Patrón de uso:

```cpp
thread_local BumpArena arena(1 << 20);

arena.reset();

double* aug    = arena.allocate(n_aug);
double* factor = arena.allocate(n_factor);
double* temp   = arena.allocate(n_temp);
```

La ventaja científica de la arena es que el coste de liberar $m$ objetos pasa aproximadamente de:

$$
O(m)
$$

a:

$$
O(1),
$$

porque basta restablecer `offset_`.

### Nivel 3: pool de arenas

Si hay tamaños y ciclos de vida heterogéneos, usar una arena por clase de tamaño:

```text
small:   hasta 64 KiB
medium:  hasta 1 MiB
large:   hasta 16 MiB
huge:    reserva dedicada
```

Los buffers pequeños se reciclan dentro del worker; los grandes pueden liberarse o devolverse a un pool global. Esta política evita que un caso excepcional de $K$ retenga permanentemente toda la memoria del hilo.

## 3. Eliminar fragmentación interna

El crecimiento geométrico reduce realocaciones, pero puede desperdiciar memoria. Si $R$ es el requerimiento y $C$ la capacidad:

$$
\text{fragmentación interna}=C-R.
$$

Con crecimiento de 1.5, el desperdicio máximo teórico puede ser sustancial. Para controlar el pico:

- usar crecimiento 1.25 para workloads con memoria limitada;
- usar crecimiento 2.0 si el coste de asignación domina;
- crear clases de tamaño para buffers pequeños;
- tratar tamaños enormes de forma dedicada;
- devolver capacidad si permanece inactiva durante muchas épocas.

Una política adaptativa:

```cpp
if (required > capacity) {
    if (required > 4 * capacity) {
        reserve(required);
    } else {
        reserve(capacity + capacity / 2);
    }
}
```

Así, un salto enorme evita una doble sobreasignación.

## 4. Lifetime analysis y reutilización de regiones

La mejora más importante puede no ser otro allocator, sino reducir el tamaño del workspace mediante análisis de vidas.

Si dos temporales no están vivos simultáneamente:

```text
A: [----]
B:       [----]
```

pueden compartir memoria:

```text
workspace region 0:
A y luego B
```

Si los temporales se solapan:

```text
A: [------]
B:   [----]
```

necesitan regiones distintas.

Para Cayley-SMW, identificar:

- buffers solo necesarios para formar $A$;
- buffers necesarios durante la factorización;
- RHS que puede sobrescribirse después de resolver;
- temporales de actualización que pueden recomputarse;
- matrices que pueden almacenarse en triangular o simétrica.

Esto puede reducir el pico de memoria de:

$$
O(nK^2)
$$

a una constante menor por delante del mismo orden asintótico, o incluso eliminar regiones completas mediante recomputación.

## 5. Layout de memoria para SMW

La memoria debe organizarse según el patrón de acceso, no solo según la conveniencia de los índices.

### CPU

Para operaciones vectorizadas:

- alinear a 64 bytes;
- usar layout contiguo;
- evitar punteros dispersos;
- separar campos accedidos conjuntamente;
- reservar capacidad suficiente para evitar realocaciones.


### GPU

Para coalescencia:

- usar layout compatible con warps;
- evitar una matriz pequeña dispersa entre buffers;
- alinear a 128 o 256 bytes cuando el backend lo aproveche;
- preferir almacenamiento column-major o row-major según la librería de factorización;
- fusionar kernels cuando el workspace intermedio solo se usa una vez.

La ocupación puede degradarse si un kernel usa demasiados registros para evitar memoria global. El óptimo no es “cero asignaciones”, sino minimizar:

$$
T_{\text{global memory}}
+
T_{\text{register spill}}
+
T_{\text{allocation}}
+
T_{\text{synchronization}}.
$$

## 6. GPU: pool por stream

Si la ruta se ejecuta en CUDA, la solución recomendada es un pool de memoria de device, no `thread_local vector`.

`cudaMallocAsync` y `cudaFreeAsync` incorporan asignación ordenada por stream y permiten reutilizar memoria sin las sincronizaciones globales asociadas al modelo tradicional. NVIDIA reporta mejoras de 2–5× en ciertos workloads al combinar allocator ordenado por stream y reutilización de pools.[^6_2]

El contrato esencial es:

$$
\text{allocation}
\prec
\text{all accesses}
\prec
\text{free}
$$

dentro del orden del stream. La documentación de CUDA exige que todos los accesos asíncronos ocurran entre la asignación y la liberación ordenada correspondiente.[^6_3][^6_4]

Patrón correcto:

```cpp
cudaMemPool_t pool;
cudaDeviceGetDefaultMemPool(&pool, device);

cudaStream_t stream;
cudaStreamCreate(&stream);

double* ptr = nullptr;
cudaMallocAsync(&ptr, bytes, stream);

launch_kernels(ptr, stream);

cudaFreeAsync(ptr, stream);
```

Para obtener el máximo rendimiento:

- reservar una arena grande por stream;
- subasignar internamente;
- evitar miles de operaciones `cudaMallocAsync`;
- configurar el límite de retención;
- controlar el número de streams;
- no reutilizar entre streams sin sincronización o eventos.

RAPIDS RMM ofrece precisamente recursos de tipo pool y arena para subasignación rápida; sus arenas por hilo reducen fragmentación en aplicaciones multihilo.[^6_5]

## 7. Memory pool y fragmentación GPU

Un pool no elimina toda fragmentación. Hay que distinguir:

### Fragmentación externa

Espacio libre total suficiente, pero dividido en bloques incompatibles.

### Fragmentación interna

Bloques asignados más grandes que el requerimiento.

### Fragmentación temporal

La memoria está libre lógicamente, pero no puede reutilizarse todavía porque un kernel de otro stream sigue usándola.

La tercera forma es especialmente importante en CUDA. Una asignación liberada en un stream puede requerir sincronización o eventos antes de reutilizarse en otro.[^6_6][^6_7]

Telemetría recomendada:

- memoria reservada;
- memoria activa;
- memoria inactiva;
- mayor bloque libre;
- número de bloques por clase;
- eventos pendientes;
- tiempo entre `free` y reutilización;
- p50/p99 de `cudaMallocAsync`.


## 8. Alternativa: workspace preasignado por época

Si el tamaño máximo de $K$ es conocido, reservar una vez al comienzo de la época puede ser mejor que crecer de forma incremental:

$$
W_{\max}
=
\max_{t\in\text{época}} W(K_t).
$$

```cpp
workspace.reserve(max_workspace_for_epoch);
```

Ventajas:

- cero realocaciones durante la época;
- comportamiento determinista;
- fácil de perfilar;
- menor jitter.

Desventajas:

- pico de memoria elevado;
- riesgo de reservar mucho para un caso raro;
- mala escalabilidad si los workers tienen máximos distintos.

Una política híbrida suele ser superior:

1. estimar un percentil alto, por ejemplo $P_{99}$, no el máximo absoluto;
2. reservar ese tamaño al inicio;
3. usar una ruta de expansión para outliers;
4. liberar o reciclar outliers al final.

## 9. Planificación por tamaño

En un swarm, mezclar tareas con $K$ muy pequeño y muy grande puede causar:

- reservas repetidas;
- mala ocupación;
- divergencia;
- pools fragmentados;
- picos de memoria.

Clasificar tareas por bins de $K$:

```text
K ∈ [1, 32]
K ∈ [33, 64]
K ∈ [65, 128]
K ∈ [129, 256]
K ∈ [257, 512]
...
```

y asignar cada grupo a un worker o pool compatible. Beneficios:

- workspaces más estables;
- menos crecimiento;
- mejor reutilización;
- kernels más homogéneos;
- menor variabilidad de duración.

Esto es una optimización de planificación, no solo de memoria.

## 10. Preasignar por lote

Si el algoritmo procesa $B$ individuos con el mismo $K$, usar un workspace batched:

$$
W_{\text{batch}}
=
B\cdot W(K)
$$

o un pool de buffers de igual capacidad.

Ventajas:

- menos llamadas al allocator;
- mejor vectorización;
- operaciones batched BLAS;
- mayor regularidad de acceso.

Pero si $B\cdot W(K)$ es muy grande, dividir en microbatches para controlar:

$$
\text{pico de memoria}
\quad\text{vs}\quad
\text{throughput}.
$$

La elección óptima debe medirse con un roofline: si el kernel es memory-bound, ampliar el batch puede no mejorar el rendimiento y sí aumentar el working set.

## 11. Recomputación frente a almacenamiento

Para cada temporal, comparar:

$$
T_{\mathrm{recompute}}
\quad\text{con}\quad
T_{\mathrm{store}}+T_{\mathrm{load}}.
$$

Si una matriz temporal se usa una sola vez y su cálculo es barato, recomputarla puede ser más eficiente que:

- reservarla;
- escribirla;
- leerla;
- mantenerla viva;
- aumentar presión de caché.

Esta estrategia es especialmente relevante en GPU, donde el ancho de banda y la ocupación pueden ser más limitantes que los FLOPs.

Una política SOTA suele ser:

- almacenar resultados caros y reutilizados;
- recomputar expresiones baratas;
- fusionar operaciones cuando el temporal tiene uso único;
- usar checkpointing si la memoria domina.


## 12. Seguridad y robustez del workspace

La eliminación del límite $K\le128$ debe acompañarse de límites explícitos:

```cpp
constexpr std::size_t MAX_WORKSPACE_BYTES = 8ull << 30;

if (required_bytes > MAX_WORKSPACE_BYTES) {
    throw std::runtime_error("workspace exceeds budget");
}
```

Validar:

- overflow en $K^2$, $nK^2$ y bytes;
- `K=0`;
- dimensiones inconsistentes;
- `NaN` en tamaños derivados;
- alineación;
- capacidad máxima por worker;
- número máximo de workers;
- suma total de reservas.

Debe existir un fallback:

- procesamiento por bloques;
- reducción del batch;
- ruta CPU/GPU alternativa;
- rechazo controlado con diagnóstico.

Un workspace dinámico sin presupuesto puede sustituir el cuello de allocator por un fallo catastrófico de memoria.

## 13. Diseño recomendado para v911

### CPU

```text
Workspace explícito por worker
        ↓
Arena monotónica por iteración
        ↓
Crecimiento geométrico 1.25–1.5×
        ↓
Subasignación por offsets
        ↓
Reutilización por análisis de vidas
        ↓
Límite y telemetría
```


### GPU

```text
Pool por device/stream
        ↓
Arena de subasignación
        ↓
cudaMallocAsync/cudaFreeAsync solo en fronteras
        ↓
Buffers batched por clases de K
        ↓
Reutilización stream-ordered
        ↓
Microbatching si falta memoria
```


### Política de outliers

```text
1. Reservar hasta el percentil operativo esperado.
2. En un outlier, crecer de forma controlada.
3. Registrar el evento.
4. No retener permanentemente el buffer gigante.
5. Volver a una capacidad objetivo después de la época.
```


## 14. Benchmark exigente

Medir al menos:


| Métrica | Significado |
| :-- | :-- |
| `alloc_count` | número de reservas |
| `realloc_count` | crecimientos del vector |
| `reserved_bytes` | capacidad retenida |
| `active_bytes` | memoria realmente usada |
| `peak_bytes` | pico |
| p50/p95/p99 | latencia típica y cola |
| `T_alloc` | coste de reserva |
| `T_kernel` | coste algebraico |
| `T_copy` | transferencias |
| cache/TLB misses | localidad |
| occupancy | utilización GPU |
| fragmentation ratio | memoria desperdiciada |

Comparar:

1. V907: array fijo + fallback dinámico;
2. v911: `thread_local vector`;
3. workspace explícito;
4. arena monotónica;
5. pool por clases;
6. pool CUDA stream-ordered;
7. batch/microbatch;
8. recomputación de temporales.

No declarar superioridad solo por el tiempo medio. El criterio debe incluir:

$$
\text{throughput}
+
\text{p99}
+
\text{pico de memoria}
+
\text{reproducibilidad}.
$$

## Veredicto

v911 es una buena mitigación, pero no una arquitectura de memoria completa. La mejora científicamente más sólida es reemplazar el `thread_local std::vector` monolítico por:

$$
\boxed{
\text{workspace persistente}
+
\text{arena monotónica}
+
\text{subasignación por regiones}
+
\text{análisis de vidas}
+
\text{política de outliers}
}
$$

Para GPU:

$$
\boxed{
\text{memory pool por stream}
+
\texttt{cudaMallocAsync}
+
\text{arena interna}
+
\text{reutilización ordenada}
}
$$

La redacción técnica recomendada para v911 sería:

> Se introduce un sistema jerárquico de gestión de workspaces. Cada worker utiliza una arena persistente con crecimiento geométrico, subasignación contigua, reutilización por intervalos de vida, límites de memoria y telemetría de fragmentación. Las tareas se agrupan por clases de $K$, y los casos grandes se procesan mediante microbatches o buffers dedicados. En GPU se utiliza un memory pool stream-ordered. La solución elimina asignaciones de la ruta caliente, reduce el p99 y el jitter, evita el límite fijo $K\le128$ y mantiene controlado el pico de memoria.

<span style="display:none">[^6_10][^6_11][^6_12][^6_13][^6_14][^6_15][^6_16][^6_17][^6_18][^6_19][^6_20][^6_8][^6_9]</span>

<div align="center">⁂</div>

[^6_1]: https://arxiv.org/html/2605.17119v1

[^6_2]: https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-2/

[^6_3]: https://docs.nvidia.com/cuda/cuda-runtime-api/cuda_runtime_api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^6_4]: https://docs.nvidia.com/cuda/archive/13.4.1/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^6_5]: https://developer.nvidia.com/blog/fast-flexible-allocation-for-cuda-with-rapids-memory-manager/

[^6_6]: https://docs.nvidia.com/cuda/archive/11.8.0/cuda-runtime-api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^6_7]: https://deepwiki.com/ananyakunisetty/pytorch/3.1-cuda-backend-and-memory-management

[^6_8]: https://docs.pytorch.org/docs/main/generated/torch.nn.RMSNorm.html

[^6_9]: https://fireworks.ai/blog/when-faster-not-identical-moe-numerics

[^6_10]: https://lizeman.github.io/llm-arch-kb/normalization/rmsnorm/

[^6_11]: https://github.com/willow-ahrens/ReproBLAS

[^6_12]: https://bebop.cs.berkeley.edu/reproblas/docs/talks/SIAM_AN13.pdf

[^6_13]: https://docs.nvidia.com/cuda/developer-preview/13.4/cuda-runtime-api/cuda_runtime_api/group\_\_CUDART\_\_MEMORY\_\_POOLS.html

[^6_14]: https://nvidia.github.io/warp/modules/allocators.html

[^6_15]: https://ai-infrastructure.net/cuda-stream-ordered-allocator/

[^6_16]: https://github.com/CNU-XU/memoryreuse

[^6_17]: https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/

[^6_18]: https://docs.nvidia.com/cuda/archive/13.4.1/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^6_19]: https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/stream-ordered-memory-allocation.html

[^6_20]: https://moldstud.com/articles/p-best-practices-for-effective-cuda-resource-management-optimize-performance-and-efficiency


---

## Evaluación de v911

La migración de `CreateFileMappingA` a `CreateFileMappingW` es correcta para Windows moderno y mejora la interoperabilidad Unicode, pero la explicación causal de V907 necesita corregirse:

> Un `.encode("utf-8")` temporal no debería ser liberado por el garbage collector mientras una llamada síncrona normal a `CreateFileMappingA` sigue ejecutándose.

Durante una llamada FFI síncrona, el argumento temporal debe permanecer vivo mientras `ctypes` invoca la función. El riesgo real aparece cuando:

- el puntero se almacena para uso posterior;
- una API nativa opera de forma asíncrona;
- se pasa `addressof()` sin conservar el objeto propietario;
- se usa una firma `argtypes` incorrecta;
- el handle o la vista mapeada se libera prematuramente;
- el hilo nativo continúa después de retornar a Python.

`c_wchar_p` mejora el contrato de tipos, pero no “delega el ownership” de forma general al puente FFI. `ctypes` puede conservar referencias internas para ciertos objetos, pero la validez durante operaciones asíncronas debe diseñarse explícitamente. La documentación de `ctypes` indica que `_objects` mantiene objetos Python necesarios para conservar válido un bloque de memoria y advierte que las referencias deben mantenerse mientras C las use.[^7_1][^7_2][^7_3]

## 1. Corrección del diagnóstico V907

### Lo que sí era problemático

La combinación siguiente es frágil:

```python
name = "shared_tensor".encode("utf-8")
handle = CreateFileMappingA(
    INVALID_HANDLE_VALUE,
    None,
    PAGE_READWRITE,
    high,
    low,
    name,
)
```

No por el GC durante la llamada síncrona en sí, sino porque:

- `bytes` es una codificación dependiente del contrato de la API;
- `CreateFileMappingA` interpreta el nombre según la code page ANSI del sistema;
- un puntero derivado puede quedar colgante si se almacena después;
- no se documenta claramente quién conserva el nombre;
- la firma FFI puede hacer conversiones implícitas peligrosas.


### Lo que v911 sí corrige

```python
name = ctypes.c_wchar_p("shared_tensor")
```

y:

```python
CreateFileMappingW(..., name)
```

corrigen el ancho de caracteres y evitan dependencias de la code page ANSI. `CreateFileMappingW` recibe un nombre UTF-16 de Windows y devuelve un handle al objeto de mapping si tiene éxito.[^7_4][^7_5]

### Lo que v911 no garantiza

`c_wchar_p` no resuelve automáticamente:

- vida útil de la vista de memoria;
- vida útil del handle;
- acceso posterior desde otro hilo;
- cierre ordenado de `MapViewOfFile`;
- sincronización entre procesos;
- ownership del buffer compartido;
- seguridad frente a procesos que terminan abruptamente.

Por tanto, v911 es una corrección de ABI y encoding, pero no una solución completa de lifetime.

## 2. Firma FFI correcta

Definir siempre `argtypes` y `restype` explícitamente. Por ejemplo:

```python
import ctypes as C
from ctypes import wintypes

kernel32 = C.WinDLL("kernel32", use_last_error=True)

kernel32.CreateFileMappingW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPCWSTR,
]
kernel32.CreateFileMappingW.restype = wintypes.HANDLE

kernel32.MapViewOfFile.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    C.c_size_t,
]
kernel32.MapViewOfFile.restype = wintypes.LPVOID

kernel32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
```

Sin `argtypes`, `ctypes` puede aceptar conversiones que ocultan errores de ABI. En Windows de 64 bits, declarar `restype` incorrectamente puede truncar handles o punteros.

Usar `use_last_error=True` y capturar el error inmediatamente:

```python
handle = kernel32.CreateFileMappingW(
    C.c_void_p(-1),
    None,
    PAGE_READWRITE,
    high,
    low,
    name,
)

if not handle:
    error = C.get_last_error()
    raise C.WinError(error)
```

No ejecutar otras llamadas entre la función fallida y `get_last_error()`.

## 3. Lifetime correcto del nombre

Para una llamada síncrona:

```python
name = C.c_wchar_p(mapping_name)
handle = kernel32.CreateFileMappingW(
    INVALID_HANDLE_VALUE,
    None,
    PAGE_READWRITE,
    high,
    low,
    name,
)
```

el objeto `name` permanece vivo al menos hasta el final de la expresión o del ámbito local. Es mejor mantenerlo como atributo si el wrapper conserva la identidad del mapping:

```python
class SharedMapping:
    def __init__(self, name: str, size: int):
        self._name = C.c_wchar_p(name)
        self._handle = self._create(size, self._name)
```

Pero no es necesario conservar el nombre para mantener vivo el mapping después de que `CreateFileMappingW` haya terminado. El kernel recibe y procesa el nombre durante la llamada; el recurso persistente es el handle y las vistas, no el puntero a la cadena.

El caso peligroso sería una API propia que almacena el `LPCWSTR` para usarlo después de retornar. En ese caso, una variable Python local no basta: el wrapper debe conservarla explícitamente o copiarla en memoria nativa propiedad del componente C.

## 4. Lifetime del handle y de la vista

La gestión correcta requiere dos recursos separados:

1. handle devuelto por `CreateFileMappingW`;
2. puntero devuelto por `MapViewOfFile`.
```python
class SharedMapping:
    def __init__(self, name: str, size: int):
        self.size = size
        self._name = C.c_wchar_p(name)
        self._handle = None
        self._view = None
        self._closed = False

        self._handle = self._create(size)
        self._view = self._map(size)

    def _create(self, size):
        high = (size >> 32) & 0xffffffff
        low = size & 0xffffffff

        handle = kernel32.CreateFileMappingW(
            C.c_void_p(-1),
            None,
            PAGE_READWRITE,
            high,
            low,
            self._name,
        )

        if not handle:
            raise C.WinError(C.get_last_error())

        return handle

    def _map(self, size):
        view = kernel32.MapViewOfFile(
            self._handle,
            FILE_MAP_ALL_ACCESS,
            0,
            0,
            size,
        )

        if not view:
            error = C.get_last_error()
            kernel32.CloseHandle(self._handle)
            self._handle = None
            raise C.WinError(error)

        return view
```

El cierre debe ser inverso a la adquisición:

```python
    def close(self):
        if self._closed:
            return

        self._closed = True

        if self._view:
            if not kernel32.UnmapViewOfFile(self._view):
                raise C.WinError(C.get_last_error())
            self._view = None

        if self._handle:
            if not kernel32.CloseHandle(self._handle):
                raise C.WinError(C.get_last_error())
            self._handle = None
```

Windows mantiene referencias internas de las vistas mapeadas. Cerrar solo el handle no destruye necesariamente el objeto si todavía existen vistas; para liberar completamente el mapping hay que desmapear todas las vistas y cerrar el handle.[^7_5][^7_6][^7_7]

## 5. RAII en Python

No depender de `__del__` para recursos Win32. El recolector no proporciona determinismo suficiente para handles del sistema.

Usar context manager:

```python
class SharedMapping:
    # ...

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
```

Uso:

```python
with SharedMapping("tensor_001", size) as mapping:
    consume(mapping)
```

Para robustez adicional:

```python
import weakref

self._finalizer = weakref.finalize(
    self,
    _cleanup_mapping,
    self._view,
    self._handle,
)
```

El finalizer es una red de seguridad, no el mecanismo primario. Debe evitar capturar `self`, porque eso puede crear un ciclo que impida la finalización.

## 6. Exponer la vista sin dangling pointers

El patrón peligroso es:

```python
ptr = mapping._view
mapping.close()
use_ptr(ptr)       # dangling pointer
```

La API debe devolver un objeto cuya vida esté vinculada al mapping:

```python
class SharedBuffer:
    def __init__(self, owner, address, size):
        self._owner = owner
        self.address = address
        self.size = size
```

Mientras `SharedBuffer` exista, conserva una referencia a `SharedMapping`.

Para crear un array NumPy sin copiar:

```python
import numpy as np

class SharedMapping:
    def as_array(self, shape, dtype):
        array_type = (C.c_byte * (self.size)).from_address(self._view)
        array = np.ctypeslib.as_array(array_type)
        array = array.view(dtype).reshape(shape)

        self._exported_views += 1
        weakref.finalize(array, self._release_view)

        return array
```

La implementación real debe controlar cuidadosamente:

- que el owner siga vivo;
- que el array no sobreviva al mapping;
- que no se llame `UnmapViewOfFile` mientras existan arrays exportados;
- que el shape y dtype no excedan el tamaño real;
- que los strides sean coherentes;
- que el puntero esté correctamente alineado.

Una opción más segura es implementar un objeto buffer/protocolo `__array_interface__` que conserve el owner:

```python
class SharedArray:
    def __init__(self, mapping, shape, dtype):
        self.mapping = mapping
        self.__array_interface__ = {
            "shape": tuple(shape),
            "typestr": np.dtype(dtype).str,
            "data": (mapping.address, False),
            "version": 3,
        }
```


## 7. Recuento de exports

El wrapper no debe permitir el cierre mientras hay consumidores activos. Usar un contador:

```python
class SharedMapping:
    def __init__(self, ...):
        self._exports = 0
        self._closing = False

    def acquire_view(self):
        if self._closing:
            raise RuntimeError("mapping is closing")
        self._exports += 1
        return SharedView(self)

    def release_view(self):
        self._exports -= 1
        self._try_close()

    def close(self):
        self._closing = True
        self._try_close()

    def _try_close(self):
        if self._closing and self._exports == 0:
            self._unmap_and_close()
```

Esto transforma un bug de use-after-free en una violación detectable del protocolo de ownership.

Si hay acceso entre procesos, el contador Python no basta: cada proceso tiene su propio estado. El acuerdo debe incluir:

- quién crea el mapping;
- quién abre el mapping;
- cuándo cada proceso termina;
- cómo se sincroniza el productor;
- cuándo se puede desmapear;
- cómo se maneja la terminación abrupta.


## 8. Sincronización de memoria compartida

Un file mapping comparte páginas, pero no proporciona automáticamente un protocolo de publicación.

Debe existir una disciplina como:

1. productor escribe el tensor;
2. productor ejecuta una barrera adecuada;
3. productor publica una secuencia o evento;
4. consumidor espera;
5. consumidor lee;
6. productor no reutiliza el slot hasta recibir confirmación.

Opciones:

- eventos con nombres;
- mutex/semaphore Win32;
- ring buffer con índices atómicos;
- secuencias de publicación;
- memoria interproceso con protocolo release/acquire.

Evitar asumir que `CloseHandle` o `MapViewOfFile` sincronizan los datos. El lifetime del objeto y la visibilidad de las escrituras son problemas distintos.

## 9. Unicode: `W` es correcto, pero hay más detalles

`CreateFileMappingW` es preferible cuando el nombre puede contener caracteres fuera de la code page ANSI. Pero el nombre debe respetar la semántica de namespaces de Windows:

- nombres globales pueden requerir privilegios;
- `Global\...` y `Local\...` tienen ámbitos distintos;
- nombres idénticos pueden abrir un mapping existente;
- una colisión de nombres debe distinguirse de una creación nueva;
- `ERROR_ALREADY_EXISTS` puede ser un resultado esperado, no necesariamente un fallo.

Después de una creación exitosa:

```python
last_error = C.get_last_error()
```

puede ser necesario comprobar si el mapping ya existía, dependiendo del contrato de la API. La aplicación debe diferenciar:

- handle inválido;
- mapping creado;
- mapping abierto previamente;
- tamaño incompatible;
- permisos insuficientes.


## 10. FFI más seguro que `ctypes`

Para una ruta crítica o de larga vida, `ctypes` puede no ser la mejor capa. Alternativas:

### Cython o extensión CPython

Ventajas:

- tipos nativos explícitos;
- RAII en C++;
- destructores deterministas;
- mejor control de buffer protocol;
- menor coste de conversión.


### pybind11

Adecuado para exponer un objeto C++ propietario:

```cpp
class SharedMapping {
public:
    py::buffer_info buffer_info();
    void close();
};
```

El objeto Python mantiene un `shared_ptr` al recurso nativo y el destructor C++ libera view y handle en orden correcto.

### cffi

Puede dar una separación más clara entre declaraciones ABI y ownership, aunque sigue siendo necesario diseñar el lifetime.

### Biblioteca Win32 especializada

Usar `mmap`/`multiprocessing.shared_memory` cuando el caso de uso encaja puede reducir la superficie de errores. Aun así, el cierre y la vida útil de los buffers deben documentarse.

La regla SOTA es mover la propiedad compleja a una capa RAII nativa y exponer a Python solo un handle/objeto de alto nivel.

## 11. Contratos de ownership recomendados

Documentar explícitamente:


| Recurso | Creador | Propietario | Liberación |
| :-- | :-- | :-- | :-- |
| Nombre UTF-16 | Python/ctypes | llamada síncrona | al retornar |
| Handle mapping | Win32 | wrapper | `CloseHandle` |
| Vista mapeada | Win32 | wrapper/export owner | `UnmapViewOfFile` |
| Array Python | NumPy/wrapper | consumidor | al destruir array |
| Sincronización | aplicación | protocolo IPC | cierre coordinado |

Evitar funciones que devuelvan un `void*` desnudo sin owner:

```python
return ctypes.c_void_p(address)
```

Preferir:

```python
return SharedView(mapping=self, address=address, size=size)
```


## 12. Testing científico de lifetime

### Pruebas de GC

Forzar recolección agresiva:

```python
for _ in range(10000):
    name = ctypes.c_wchar_p(make_name())
    handle = create_mapping(name)
    del name
    gc.collect()
```

Esto valida que la llamada síncrona no dependa de una referencia accidental.

### Pruebas asíncronas

- iniciar worker nativo;
- retornar inmediatamente a Python;
- eliminar la referencia del nombre;
- ejecutar `gc.collect()`;
- esperar la finalización;
- usar Application Verifier y PageHeap.

Si la API nativa almacena el puntero, esta prueba debe fallar con el wrapper incorrecto y pasar con ownership explícito.

### Pruebas de cierre

- cerrar dos veces;
- cerrar durante excepción;
- destruir el owner con arrays vivos;
- liberar el handle antes de la vista;
- desmapear una vista dos veces;
- terminar el proceso consumidor abruptamente.


### Herramientas Windows

- Application Verifier;
- PageHeap/GFlags;
- WinDbg;
- AddressSanitizer para componentes C/C++;
- ETW/WPR para fallos y sincronización;
- Process Explorer/VMMap para vistas y memoria;
- `GetLastError()` comprobado en cada API fallida.


## 13. Criterios de aceptación v911

Una implementación debería cumplir:

- `CreateFileMappingW` con `LPCWSTR` explícito;
- `argtypes/restype` declarados;
- `use_last_error=True`;
- handle encapsulado, no expuesto como entero sin owner;
- vista encapsulada con lifetime;
- `close()` idempotente;
- context manager;
- `UnmapViewOfFile` antes de `CloseHandle`;
- contador de consumidores/exportaciones;
- prohibición de cerrar con vistas activas;
- protocolo de sincronización interproceso;
- tests bajo GC agresivo;
- tests de acceso después de liberar;
- diagnóstico de `ERROR_ALREADY_EXISTS`;
- validación de tamaños y offsets;
- compatibilidad Unicode comprobada.


## Veredicto

v911 corrige correctamente la selección de API y el problema de codificación:

$$
\texttt{CreateFileMappingA}
\rightarrow
\texttt{CreateFileMappingW}.
$$

Pero no debe afirmarse que `c_wchar_p` por sí solo garantiza ownership nativo ni inmunidad a dangling pointers. La solución SOTA debe ser:

$$
\boxed{
\text{ABI explícito}
+
\text{ownership RAII}
+
\text{lifetime de vista}
+
\text{cierre determinista}
+
\text{sincronización IPC}
}
$$

La formulación técnica recomendada para v911 sería:

> Se sustituye la interfaz ANSI por `CreateFileMappingW` con firmas FFI explícitas y nombres UTF-16. El handle y cada vista mapeada se encapsulan en un objeto propietario con cierre determinista, context manager y finalizer de respaldo. Los buffers exportados conservan una referencia al owner y se contabilizan antes de permitir `UnmapViewOfFile`. El protocolo interproceso separa lifetime de recursos, visibilidad de escrituras y sincronización. Las pruebas incluyen GC agresivo, ejecución asíncrona, PageHeap, errores Win32 y accesos posteriores al cierre.

La mejora fundamental no es solo cambiar `A` por `W`, sino convertir el puente FFI en un sistema con ownership verificable y ausencia demostrable de use-after-free.

<span style="display:none">[^7_10][^7_11][^7_12][^7_13][^7_14][^7_15][^7_8][^7_9]</span>

<div align="center">⁂</div>

[^7_1]: https://docs.python.org/3/library/ctypes.html

[^7_2]: https://svn.python.org/projects/ctypes/branches/LoadLibrary_branch/ctypes/docs/manual/manual.html

[^7_3]: https://documentation.help/Python-3.6.8/ctypes.html

[^7_4]: https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw

[^7_5]: https://learn.microsoft.com/en-gb/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw?redirectedfrom=MSDN

[^7_6]: https://comcomponent.com/en/blog/windows-memory-internals-section-copy-on-write/

[^7_7]: https://ftp.zx.net.nz/pub/Patches/ftp.microsoft.com/MISC/KB/en-us/125/713.HTM

[^7_8]: https://docs.python.org/3/c-api/arg.html

[^7_9]: https://learn.microsoft.com/en-us/windows/win32/memory/creating-a-file-mapping-object

[^7_10]: https://devblogs.microsoft.com/oldnewthing/20240126-00/?p=109322/

[^7_11]: https://runebook.dev/en/articles/python/library/ctypes/ctypes.addressof

[^7_12]: https://runebook.dev/en/articles/python/library/ctypes/ctypes.\_CData.\_objects

[^7_13]: https://www.cosmiclearn.com/win32/file_mapping.php

[^7_14]: https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Memory/memory-management-functions.md

[^7_15]: https://runebook.dev/en/docs/python/library/ctypes/ctypes.c_wchar


---

## Tesis principal

v911 corrige la capa de codificación, pero el problema real es más amplio: un puente FFI seguro debe demostrar la validez de cuatro recursos independientes:

$$
\text{cadena}
\rightarrow
\text{handle}
\rightarrow
\text{vista}
\rightarrow
\text{consumidor}.
$$

`CreateFileMappingW` evita problemas de code page y `c_wchar_p` expresa mejor el ABI, pero no crea por sí mismo un sistema de ownership. La solución SOTA es encapsular el mapping en una capa RAII/nativa, exponer vistas con lifetime controlado, y separar claramente codificación, ownership, sincronización y seguridad.

Windows requiere desmapear todas las vistas y cerrar el handle para cerrar completamente un objeto de file mapping. Además, si varios procesos escriben en la región compartida, deben sincronizar explícitamente el acceso.[^8_1][^8_2]

## 1. Modelo formal de ownership

Definir los estados del recurso:

$$
\text{Detached}
\rightarrow
\text{HandleCreated}
\rightarrow
\text{ViewMapped}
\rightarrow
\text{Exported}
\rightarrow
\text{Closing}
\rightarrow
\text{Closed}.
$$

Transiciones válidas:

```text
Detached      --CreateFileMappingW--> HandleCreated
HandleCreated --MapViewOfFile------> ViewMapped
ViewMapped    --export()-----------> Exported
Exported      --release_view()-----> ViewMapped
ViewMapped    --close()------------> Closed
```

Transiciones inválidas:

- `UnmapViewOfFile` mientras existen exports;
- usar el puntero después de `close`;
- `CloseHandle` dos veces;
- mapear con tamaño incompatible;
- conservar `void*` sin referencia al owner;
- almacenar una cadena Python para uso nativo asíncrono sin copiarla.

Este modelo permite convertir un problema de memoria no determinista en errores de estado verificables.

## 2. Separar tres lifetimes

### Lifetime de la cadena

Para una llamada síncrona a `CreateFileMappingW`, la cadena solo necesita estar viva durante la invocación. La referencia debe conservarse explícitamente si una API nativa almacena el puntero para más tarde.

### Lifetime del handle

El handle es un recurso Win32 independiente. Debe almacenarse como `HANDLE` correctamente tipado, no como `c_void_p` sin contrato.

### Lifetime de la vista

El puntero de `MapViewOfFile` es válido hasta `UnmapViewOfFile`. Un objeto NumPy o buffer que lo use debe conservar al owner de la vista.

La documentación de `ctypes` insiste en mantener referencias Python mientras C pueda usarlas; esta obligación es especialmente importante para callbacks, punteros almacenados y operaciones asíncronas.[^8_3][^8_4]

## 3. Wrapper nativo recomendado

Para un sistema de producción, la opción más segura es trasladar la propiedad a C++:

```cpp
class SharedMapping {
public:
    SharedMapping(std::wstring name, std::size_t bytes);
    ~SharedMapping();

    SharedMapping(const SharedMapping&) = delete;
    SharedMapping& operator=(const SharedMapping&) = delete;

    SharedMapping(SharedMapping&&) noexcept;
    SharedMapping& operator=(SharedMapping&&) noexcept;

    void* data() const noexcept;
    std::size_t size() const noexcept;
    void close();

private:
    HANDLE mapping_ = nullptr;
    void* view_ = nullptr;
    std::size_t size_ = 0;
};
```

Constructor conceptual:

```cpp
SharedMapping::SharedMapping(std::wstring name,
                             std::size_t bytes)
    : size_(bytes) {
    DWORD high = static_cast<DWORD>(
        (static_cast<std::uint64_t>(bytes) >> 32) & 0xffffffff
    );
    DWORD low = static_cast<DWORD>(
        static_cast<std::uint64_t>(bytes) & 0xffffffff
    );

    mapping_ = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        high,
        low,
        name.c_str()
    );

    if (!mapping_) {
        throw_win32("CreateFileMappingW");
    }

    view_ = MapViewOfFile(
        mapping_,
        FILE_MAP_ALL_ACCESS,
        0,
        0,
        bytes
    );

    if (!view_) {
        DWORD error = GetLastError();
        CloseHandle(mapping_);
        mapping_ = nullptr;
        SetLastError(error);
        throw_win32("MapViewOfFile");
    }
}
```

Destructor:

```cpp
SharedMapping::~SharedMapping() {
    close();
}

void SharedMapping::close() {
    if (view_) {
        UnmapViewOfFile(view_);
        view_ = nullptr;
    }

    if (mapping_) {
        CloseHandle(mapping_);
        mapping_ = nullptr;
    }
}
```

La ventaja es que la liberación es determinista y la excepción durante `MapViewOfFile` no deja un handle filtrado.

## 4. Exposición con pybind11

Un wrapper pybind11 puede devolver un objeto que conserve el `shared_ptr` del mapping:

```cpp
class SharedView {
public:
    std::shared_ptr<SharedMapping> owner;
    std::size_t offset;
    std::size_t length;
};
```

Para exponer un buffer:

```cpp
py::buffer_info buffer_info(SharedMapping& m) {
    return py::buffer_info(
        m.data(),
        sizeof(std::byte),
        py::format_descriptor<std::byte>::format(),
        1,
        {static_cast<py::ssize_t>(m.size())},
        {1}
    );
}
```

El objeto Python debe retener el `SharedMapping` mientras exista el buffer. No conviene devolver solo la dirección numérica.

La interfaz ideal implementa:

- `__enter__`/`__exit__`;
- `close()`;
- `closed`;
- `size`;
- `address` solo para depuración;
- exportación de buffer con referencia al owner;
- bloqueo de cierre mientras existan vistas.


## 5. Si se mantiene `ctypes`

Una implementación robusta debe centralizar las definiciones Win32:

```python
import ctypes as C
from ctypes import wintypes

kernel32 = C.WinDLL("kernel32", use_last_error=True)

HANDLE = wintypes.HANDLE
LPVOID = wintypes.LPVOID
LPCVOID = wintypes.LPCVOID

kernel32.CreateFileMappingW.argtypes = [
    HANDLE,
    LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPCWSTR,
]
kernel32.CreateFileMappingW.restype = HANDLE

kernel32.MapViewOfFile.argtypes = [
    HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    C.c_size_t,
]
kernel32.MapViewOfFile.restype = LPVOID

kernel32.UnmapViewOfFile.argtypes = [LPCVOID]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
```

Constantes:

```python
INVALID_HANDLE_VALUE = C.c_void_p(-1).value

PAGE_READWRITE = 0x04
FILE_MAP_READ = 0x0004
FILE_MAP_WRITE = 0x0002
FILE_MAP_ALL_ACCESS = 0x000F001F
```

Wrapper mínimo:

```python
class MappingError(OSError):
    pass


def winerror(api):
    error = C.get_last_error()
    exc = C.WinError(error)
    return MappingError(f"{api} failed: {exc}")


class SharedMapping:
    def __init__(self, name: str, size: int):
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        if size <= 0:
            raise ValueError("size must be positive")

        self._name = C.c_wchar_p(name)
        self._size = int(size)
        self._handle = None
        self._view = None
        self._exports = 0
        self._closing = False

        high = (size >> 32) & 0xffffffff
        low = size & 0xffffffff

        handle = kernel32.CreateFileMappingW(
            C.c_void_p(-1),
            None,
            PAGE_READWRITE,
            high,
            low,
            self._name,
        )

        if not handle:
            raise winerror("CreateFileMappingW")

        self._handle = handle

        view = kernel32.MapViewOfFile(
            self._handle,
            FILE_MAP_ALL_ACCESS,
            0,
            0,
            size,
        )

        if not view:
            error = C.get_last_error()
            kernel32.CloseHandle(self._handle)
            self._handle = None
            C.set_last_error(error)
            raise winerror("MapViewOfFile")

        self._view = view
```


## 6. Exportación segura a NumPy

El patrón debe evitar que el array sobreviva al mapping:

```python
class SharedMapping:
    # ...

    def acquire_array(self, dtype, shape):
        import numpy as np

        dtype = np.dtype(dtype)
        expected = dtype.itemsize

        count = 1
        for dim in shape:
            if dim < 0:
                raise ValueError("negative dimension")
            count *= dim

        required = count * dtype.itemsize
        if required > self._size:
            raise ValueError("array exceeds mapping size")

        if self._closing:
            raise RuntimeError("mapping is closing")

        raw_type = C.c_ubyte * required
        raw = raw_type.from_address(
            C.addressof(C.c_ubyte.from_buffer(
                (C.c_ubyte * required).from_address(self._view)
            ))
        )

        array = np.frombuffer(raw, dtype=dtype).reshape(shape)
        self._exports += 1

        owner = self

        def release():
            owner._exports -= 1
            owner._try_close()

        weakref.finalize(array, release)
        return array
```

En producción, conviene encapsular la referencia de owner en una clase `SharedArray` en vez de depender solo de `weakref.finalize`, porque el usuario puede crear vistas derivadas con `.view()`, slicing o reshape. La propiedad debe propagarse correctamente.

Una alternativa más segura es retornar un wrapper que contenga:

```python
class SharedArray:
    def __init__(self, owner, array):
        self.owner = owner
        self.array = array
```

El usuario trabaja con `shared.array`, pero el owner siempre queda retenido.

## 7. Control de vistas derivadas

Este caso es peligroso:

```python
shared = mapping.acquire_array(...)
view = shared[::2]
del shared
mapping.close()
use(view)
```

Aunque `view` normalmente conserve al array base en NumPy, el wrapper debe probar que el owner no queda fuera de la cadena de referencias.

Pruebas obligatorias:

- slicing;
- `reshape`;
- `.view()`;
- `astype(copy=False)`;
- arrays no contiguos;
- exportación a otra librería;
- destrucción en orden inverso;
- cierre explícito mientras existen vistas derivadas.

El protocolo debe considerar que una exportación puede generar un grafo de vistas, no un único objeto.

## 8. Sincronización productor-consumidor

La memoria compartida resuelve el transporte, no la coordinación. Para un único productor y consumidor, usar un ring buffer:

```text
slot:
    sequence
    length
    dtype
    shape
    payload
```

Protocolo:

```text
1. Productor espera slot libre.
2. Productor escribe payload.
3. Productor publica metadata con release.
4. Consumidor observa sequence con acquire.
5. Consumidor lee payload.
6. Consumidor publica slot liberado.
```

En procesos distintos, los atomics deben estar respaldados por un protocolo compatible con el modelo de memoria y, cuando sea necesario, por eventos o semáforos Win32. Microsoft especifica que varios procesos con acceso de escritura deben sincronizar el acceso al área compartida.[^8_2]

No usar simplemente:

```python
ready = True
```

en memoria compartida sin una semántica de publicación definida.

## 9. Seguridad del mapping

`CreateFileMappingW(..., lpAttributes=NULL, ...)` usa un descriptor de seguridad predeterminado. Eso puede conceder acceso más amplio o más restringido de lo deseado según el contexto. Microsoft documenta que puede proporcionarse un `SECURITY_ATTRIBUTES` explícito para controlar la seguridad del objeto.[^8_5][^8_6]

Para procesos no confiables:

- no usar `FILE_MAP_ALL_ACCESS` innecesariamente;
- separar productor y consumidor con permisos mínimos;
- usar nombres no predecibles;
- considerar namespaces `Local\` y `Global\`;
- configurar DACL explícita;
- validar el tamaño y metadata del mapping;
- evitar ejecutar código desde memoria compartida;
- no usar `PAGE_EXECUTE_*` salvo necesidad estricta.

El namespace global puede requerir privilegios adicionales. Los errores de permisos deben distinguirse de errores de ABI.

## 10. Cierre ordenado y fallos abruptos

Si un proceso termina, Windows libera sus handles y vistas, pero los demás procesos deben tolerar:

- productor desaparecido;
- consumidor desaparecido;
- slot bloqueado;
- metadata parcialmente escrita;
- versión de protocolo incompatible;
- mapping existente con tamaño distinto.

Añadir a la cabecera:

```text
magic
version
header_size
payload_size
dtype_code
rank
shape[]
producer_pid
generation
checksum
```

El consumidor valida:

$$
\text{magic},
\text{version},
\text{payload\_size},
\text{generation},
\text{checksum}.
$$

Esto evita interpretar basura como un tensor válido después de una terminación inesperada.

## 11. Pruebas de estrés

### GC y llamadas síncronas

- crear miles de mappings;
- crear el nombre como temporal;
- ejecutar `gc.collect()` en cada vuelta;
- verificar que el handle y la vista sean válidos.


### Llamadas asíncronas

- pasar el nombre a un worker nativo;
- retornar inmediatamente;
- eliminar referencias Python;
- forzar GC;
- comprobar que el worker no use un puntero colgante.


### Errores inducidos

- nombres Unicode largos;
- nombres con caracteres no representables en ANSI;
- tamaño cero;
- tamaño mayor de 4 GiB;
- mapping ya existente;
- permisos insuficientes;
- `MapViewOfFile` fallido;
- doble cierre;
- cierre durante exportación;
- proceso productor terminado.


### Herramientas

- Application Verifier;
- PageHeap;
- WinDbg;
- AddressSanitizer en la DLL;
- ETW;
- stress tests multihilo;
- sanitizers de Python cuando estén disponibles.


## 12. Métricas de corrección

Medir:

- número de handles abiertos;
- vistas activas;
- exports activos;
- cierres retrasados;
- fallos de `CreateFileMappingW`;
- `ERROR_ALREADY_EXISTS`;
- fallos de `MapViewOfFile`;
- tamaño real frente al declarado;
- latencia de map/unmap;
- número de procesos consumidores;
- uso de memoria privada y compartida.

Un test de regresión debe verificar que al finalizar $N$ iteraciones:

$$
\Delta(\text{handles})=0,
\qquad
\Delta(\text{views})=0,
\qquad
\Delta(\text{RSS})\approx0.
$$

## Veredicto técnico

v911 es correcta como reparación de ABI y Unicode, pero insuficiente como solución completa de GC y dangling pointers. El diagnóstico SOTA es:

$$
\boxed{
\text{W API}
\neq
\text{ownership seguro}
}
$$

La implementación robusta debe combinar:

$$
\boxed{
\texttt{CreateFileMappingW}
+
\text{firmas FFI explícitas}
+
\text{RAII}
+
\text{owner de vistas}
+
\text{contador de exports}
+
\text{sincronización IPC}
+
\text{seguridad Win32}
}
$$

La redacción recomendada para v911 sería:

> Se reemplaza la API ANSI por `CreateFileMappingW` con tipado FFI explícito, pero la corrección se extiende a todo el ciclo de vida del recurso. El handle, la vista y los objetos exportados se encapsulan bajo ownership determinista; `UnmapViewOfFile` queda bloqueado mientras existan consumidores; el cierre se realiza mediante RAII/context manager; y el protocolo interproceso valida metadata, sincronización, versión y checksum. Las pruebas cubren GC agresivo, llamadas asíncronas, procesos terminados, errores Win32 y ausencia de fugas de handles o vistas.

<span style="display:none">[^8_10][^8_11][^8_12][^8_13][^8_14][^8_15][^8_7][^8_8][^8_9]</span>

<div align="center">⁂</div>

[^8_1]: https://learn.microsoft.com/en-us/previous-versions/ms959953(v=msdn.10)

[^8_2]: https://learn.microsoft.com/en-us/windows/win32/memory/scope-of-allocated-memory

[^8_3]: https://docs.python.org/3.9/library/ctypes.html

[^8_4]: https://academify.com.br/en/python-ctypes-call-c-libraries/

[^8_5]: https://learn.microsoft.com/en-us/windows/win32/dlls/using-shared-memory-in-a-dynamic-link-library

[^8_6]: https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Memory/file-mapping-security-and-access-rights.md

[^8_7]: https://learn.microsoft.com/tr-tr/previous-versions/aa914748(v=msdn.10)

[^8_8]: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createfilemappinga

[^8_9]: https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Memory/creating-a-file-view.md

[^8_10]: https://runebook.dev/en/articles/python/library/ctypes/ctypes.py_object

[^8_11]: http://ftp.zx.net.nz/pub/archive/ftp.microsoft.com/MISC/KB/en-us/188/535.HTM

[^8_12]: https://fossies.org/linux/Python/Modules/\_ctypes/callbacks.c

[^8_13]: https://docs.python.org/3/library/ctypes.html

[^8_14]: https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw

[^8_15]: https://ftp.zx.net.nz/pub/Patches/ftp.microsoft.com/MISC/KB/en-us/125/713.HTM


---

## Evaluación de v911

La separación entre `raw_energy_out` y `metric_energy_out` es una mejora **conceptualmente correcta y necesaria**, porque distingue dos magnitudes con semánticas diferentes:

$$
E_{\mathrm{raw}}=\|z_{\mathrm{ambient}}\|_2
$$

frente a:

$$
E_{\mathrm{metric}}=\|\Pi_{\mathcal M}(z)\|_{\mathcal M},
$$

donde $\Pi_{\mathcal M}$ representa la proyección, normalización o retracción hacia la variedad válida $\mathcal M$.

El error de V907 no era necesariamente numérico, sino **de contrato semántico**: una magnitud ambiental se exponía como si fuera una magnitud geométrica válida. La solución SOTA no consiste solo en añadir dos campos, sino en introducir tipos, procedencia, invariantes y estados de calidad que impidan que una medición raw entre accidentalmente en el canal métrico.

`LASSQ` es apropiado para calcular sumas de cuadrados evitando overflow y underflow porque mantiene una representación escalada del tipo:

$$
\text{scale}^2\cdot\text{sumsq}.
$$

[^9_1][^9_2]

## 1. Separar magnitud, estado y semántica

El diseño debe distinguir al menos cuatro conceptos:


| Campo | Significado |
| :-- | :-- |
| `raw_energy` | Magnitud del vector antes de proyección |
| `projected_energy` | Magnitud después de la transformación geométrica |
| `constraint_residual` | Violación de la restricción |
| `quality` | Validez y confiabilidad de la medición |

Una API robusta no debería devolver dos `double` anónimos:

```cpp
std::pair<double, double>
```

sino un registro con semántica explícita:

```cpp
struct CliffordTelemetry {
    double raw_energy;
    double metric_energy;
    double constraint_residual;

    double projection_scale;
    double projection_loss;

    std::uint64_t step;
    std::uint32_t schema_version;

    enum class Quality : std::uint8_t {
        Valid,
        Clamped,
        Projected,
        NonFinite,
        ConstraintViolation,
        OverflowRisk
    } quality;
};
```

Esto evita que un consumidor confunda el primer y segundo canal por posición.

## 2. La proyección no debe ocultar la violación

Un error común sería:

```cpp
metric_energy = norm(projected);
return metric_energy;
```

y descartar completamente el valor preproyección. Eso evita contaminar la telemetría principal, pero destruye información diagnóstica.

La solución correcta es conservar:

$$
E_{\mathrm{raw}},
\qquad
E_{\mathrm{metric}},
\qquad
r_{\mathrm{constraint}}.
$$

Por ejemplo, en $S^{D-1}$:

$$
r_{\mathrm{constraint}}
=
\left|\|x\|_2-1\right|
$$

o, si la representación usa la ecuación cuadrática:

$$
r_{\mathrm{constraint}}
=
\left|\|x\|_2^2-1\right|.
$$

Si la geometrización es:

$$
\hat x=\frac{x}{\|x\|_2},
$$

entonces `metric_energy` debe calcularse usando $\hat x$, mientras `raw_energy` conserva la magnitud de $x$ antes de modificarlo.

La documentación de optimización riemanniana distingue la geometría ambiente de las operaciones sobre la variedad y sus espacios tangentes; la proyección o retracción es una operación explícita, no una reinterpretación implícita del dato.[^9_3][^9_4]

## 3. Contrato de datos recomendado

Usar una estructura con unidades y origen:

```cpp
struct EnergyMeasurement {
    double value;
    enum class Domain : std::uint8_t {
        Ambient,
        Projected,
        Tangent,
        Geodesic
    } domain;

    enum class Status : std::uint8_t {
        Valid,
        Invalid,
        NonFinite,
        Clamped,
        ConstraintViolation
    } status;

    double abs_error_bound;
    double residual;
};
```

Entonces:

```cpp
struct CliffordTelemetry {
    EnergyMeasurement raw_energy;
    EnergyMeasurement metric_energy;
    EnergyMeasurement constraint_residual;

    std::uint64_t iteration;
    std::uint32_t schema_version;
};
```

La ventaja es que un consumidor puede verificar:

```cpp
if (event.metric_energy.domain != Domain::Projected) {
    reject(event);
}
```

En sistemas de telemetría, los esquemas son precisamente el mecanismo para validar estructura, tipos y valores ingeridos. La procedencia y el lineage son igualmente necesarios para saber qué transformación produjo cada medición.[^9_5][^9_6][^9_7]

## 4. Geometrización y energías no equivalentes

Es esencial definir qué significa `metric_energy`.

### Caso A: norma de la representación proyectada

$$
E_{\mathrm{metric}}=\|\Pi_{\mathcal M}(x)\|_2.
$$

Si $\Pi_{\mathcal M}(x)\in S^{D-1}$, entonces idealmente:

$$
E_{\mathrm{metric}}\approx1.
$$

En este caso, reportar una gran variación de `metric_energy` puede ser incorrecto: la métrica geométrica está diseñada para quedar normalizada. La información de amplitud debe quedar en `raw_energy` o en otro canal.

### Caso B: energía de una interacción proyectada

Si existe una interacción $F(x,y)$, entonces:

$$
E_{\mathrm{metric}}=
\|\Pi_{\mathcal M}(F(x,y))\|_2.
$$

Aquí sí puede variar, pero la proyección debe estar documentada.

### Caso C: energía riemanniana

La energía puede ser:

$$
E_{\mathrm{Riem}}=\langle v,v\rangle_x
$$

o una forma cuadrática dependiente del punto $x$. No es necesariamente igual a la norma euclidiana ambiental.

Por tanto, `metric_energy` no debe significar únicamente “norma después de llamar a LASSQ”. Debe documentarse como una función concreta:

$$
E_{\mathrm{metric}}=\mathcal E_{\mathcal M}(x,\text{contexto}).
$$

## 5. LASSQ: implementación y límites

La representación escalada de `LASSQ` mantiene:

```text
scale = max(|x_i|)
sumsq = Σ (x_i / scale)^2
norm  = scale * sqrt(sumsq)
```

Pseudocódigo:

```cpp
struct Lassq {
    double scale = 0.0;
    double sumsq = 1.0;

    void update(double x) {
        const double ax = std::abs(x);

        if (ax == 0.0) {
            return;
        }

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
        return scale == 0.0 ? 0.0 : scale * std::sqrt(sumsq);
    }
};
```

Para uso científico:

- acumular `sumsq` en precisión superior cuando sea posible;
- usar FMA para $r^2$ y la suma;
- controlar `NaN` e `Inf`;
- devolver una cota de error;
- distinguir vector cero de vector no finito;
- evitar convertir `scale * sqrt(sumsq)` si todavía puede desbordar.

LASSQ evita muchos overflow/underflow, pero no resuelve:

- cancelación en productos con signo;
- errores de proyección;
- pérdida de información al cuantizar la telemetría;
- violaciones geométricas;
- errores del algoritmo previo a la norma.


## 6. Pipeline de observabilidad en dos planos

Una arquitectura SOTA separa tres planos:

### Plano numérico

Contiene:

- `raw_energy`;
- `metric_energy`;
- residual geométrico;
- escala de proyección;
- cota de error;
- flags de finitud;
- condición estimada.


### Plano operacional

Contiene:

- tiempo de cálculo;
- latencia;
- memoria;
- número de iteración;
- worker;
- dispositivo;
- kernel;
- versión del modelo.


### Plano de procedencia

Contiene:

- versión de la fórmula;
- método de reducción;
- tipo numérico;
- backend;
- parámetros de `eps`;
- versión de schema;
- hash del estado o lote;
- timestamp monotónico.

No mezclar `raw_energy` con métricas de operación como latencia o memoria. Un sistema observable debe conservar el origen y las transformaciones de cada señal.

## 7. Validación en el productor y consumidor

### Productor

Antes de emitir:

```cpp
bool finite = std::isfinite(raw_energy)
           && std::isfinite(metric_energy)
           && std::isfinite(residual);

if (!finite) {
    quality = Quality::NonFinite;
}

if (residual > tolerance) {
    quality = Quality::ConstraintViolation;
}
```


### Consumidor

El orquestador debe validar:

```python
def validate_metric_event(event):
    if event["schema_version"] != EXPECTED_SCHEMA:
        raise ValueError("unknown telemetry schema")

    metric = event["metric_energy"]

    if metric["domain"] != "projected":
        raise ValueError("illegal metric domain")

    if metric["status"] not in {"valid", "projected", "clamped"}:
        raise ValueError("metric is not trustworthy")

    if not math.isfinite(metric["value"]):
        raise ValueError("non-finite metric")

    if metric["residual"] > RESIDUAL_TOL:
        quarantine(event)
```

La regla debe ser: **rechazar o poner en cuarentena**, no sustituir silenciosamente por cero.

## 8. Estados de calidad en vez de booleanos

Un único `valid=True/False` es insuficiente. Usar estados separados:

```text
finite
in_domain
constraint_satisfied
projection_applied
error_bound_known
provenance_complete
```

Por ejemplo:

```json
{
  "raw_energy": {
    "value": 12.4,
    "domain": "ambient",
    "finite": true
  },
  "metric_energy": {
    "value": 1.0,
    "domain": "projected",
    "finite": true,
    "projection_applied": true
  },
  "constraint": {
    "residual": 2.1e-13,
    "satisfied": true,
    "tolerance": 1e-10
  },
  "quality": {
    "usable_for_control": true,
    "usable_for_drift": true
  }
}
```

La telemetría raw puede ser válida para análisis de deriva pero inválida para control de la dinámica geométrica. La validez depende del uso.

## 9. No usar la métrica proyectada para ocultar drift

Una arquitectura peligrosa sería:

```text
raw_energy aumenta
        ↓
proyección normaliza
        ↓
metric_energy ≈ constante
        ↓
orquestador no detecta deriva
```

La separación v911 resuelve la contaminación, pero debe añadirse una alarma explícita:

$$
D_t
=
\frac{E_{\mathrm{raw},t}}
{E_{\mathrm{metric},t}+\delta}
$$

o, para una esfera normalizada:

$$
D_t=|E_{\mathrm{raw},t}-1|.
$$

Analizar:

- media móvil;
- pendiente;
- cambio de régimen;
- CUSUM;
- EWMA;
- detección de change points;
- ratio de muestras fuera de tolerancia.

La telemetría raw debe entrar en el canal de diagnóstico, no en el canal que decide el estado geométrico.

## 10. Invariantes geométricos como assertions

Para $x\in S^{D-1}$:

$$
\left|\|x\|_2^2-1\right|\le\tau.
$$

Para una matriz Stiefel $X\in\mathrm{St}(n,p)$:

$$
\|X^\top X-I\|_F\le\tau.
$$

Para una proyección idempotente ideal:

$$
\|\Pi(\Pi(x))-\Pi(x)\|\le\tau.
$$

Para una retracción:

$$
R_x(0)=x,
\qquad
D R_x(0)=\mathrm{Id}
$$

en el espacio tangente correspondiente.

Registrar estas invariantes como señales separadas:

```cpp
struct GeometryDiagnostics {
    double sphere_residual;
    double stiefel_residual;
    double projection_idempotence_error;
    double tangent_residual;
};
```

No inferir la validez geométrica solo a partir de `metric_energy`.

## 11. Error científico y cota de incertidumbre

Cada medición debería incluir una estimación de error:

$$
\widehat E \pm \Delta E.
$$

La cota puede combinar:

$$
\Delta E
\approx
\Delta_{\mathrm{reduction}}
+
\Delta_{\mathrm{projection}}
+
\Delta_{\mathrm{cast}}
+
\Delta_{\mathrm{algorithm}}.
$$

No todos los términos deben calcularse exactamente, pero el sistema debe indicar si la cota es:

- analítica;
- empírica;
- desconocida;
- estimada por precisión cruzada.

Una técnica práctica es shadow computation ocasional:

- calcular una pequeña muestra en fp64;
- comparar con fp32;
- estimar la distribución del error;
- activar modo preciso si el error supera el umbral.


## 12. Contrato de API recomendado

En C++:

```cpp
struct MetricEnergy {
    double value;
    double error_bound;
    double constraint_residual;

    enum class Domain {
        Ambient,
        Projected
    } domain;

    enum class Status {
        Valid,
        Projected,
        Invalid,
        NonFinite,
        ConstraintViolation
    } status;
};

struct CliffordNetTelemetry {
    MetricEnergy raw_energy;
    MetricEnergy metric_energy;

    std::uint64_t iteration;
    std::uint32_t schema_version;
    std::uint32_t algorithm_version;
};
```

API:

```cpp
CliffordNetTelemetry
polydim_cpp_cliffordnet_bivector_interact(
    const TensorView& input,
    const InteractionConfig& config
);
```

Evitar:

```cpp
double* energy_out
```

porque no expresa:

- unidad;
- dominio;
- validez;
- error;
- procedencia;
- ownership.


## 13. Compatibilidad hacia atrás

Si hay consumidores antiguos que esperan un único `energy_out`, introducir una versión de schema:

```text
schema_version = 1:
    energy_out = metric_energy

schema_version = 2:
    raw_energy
    metric_energy
    residual
    quality
```

Pero no reutilizar silenciosamente el nombre antiguo con semántica diferente. Opciones:

- deprecar `energy_out`;
- mapearlo explícitamente a `metric_energy`;
- emitir advertencia;
- exigir al consumidor declarar qué canal necesita.

La migración debe tener pruebas contractuales para evitar que el orquestador consuma `raw_energy` por posición.

## 14. Validación estadística del monitor

La telemetría no debe validarse solo con ejemplos normales. Crear una matriz de pruebas:


| Caso | Raw | Proyectada | Residual |
| :-- | --: | --: | --: |
| Vector unitario válido | finita | finita | bajo |
| Vector de norma grande | grande | válida | alto antes de proyectar |
| Vector cero | 0 | dependiente del contrato | especial |
| `NaN` | inválida | inválida | inválida |
| `Inf` | inválida | inválida | inválida |
| Casi subnormal | finita | finita | evaluada |
| Proyección fuerte | alta | válida | alta |
| Error de reducción | finita | finita | detectado por referencia |

Probar invariancia:

$$
\text{metric\_energy}(x)
\approx
\text{metric\_energy}(\Pi(x)).
$$

Y sensibilidad:

$$
\text{raw\_energy}(\alpha x)
=
|\alpha|\text{raw\_energy}(x),
$$

mientras que, para una normalización esférica:

$$
\text{metric\_energy}(\alpha x)
\approx
\text{metric\_energy}(x).
$$

Estas dos propiedades verifican que los canales no se hayan intercambiado.

## 15. Veredicto

v911 es una mejora fundamental porque evita que una magnitud ambiental se interprete como métrica geométrica. Sin embargo, la solución SOTA debe avanzar desde “dos doubles separados” hacia un contrato semántico completo:

$$
\boxed{
\text{dominio}
+
\text{invariante}
+
\text{residual}
+
\text{calidad}
+
\text{error}
+
\text{provenance}
}
$$

La formulación recomendada para v911 sería:

> La telemetría se divide en canales tipados de dominio ambiental y geométrico. `raw_energy` conserva la magnitud previa a la proyección para análisis de deriva; `metric_energy` se calcula exclusivamente después de la geometrización y solo se publica como métrica válida si satisface los invariantes de la subvariedad. Cada muestra incorpora residual de restricción, estado de calidad, cota de error, versión algorítmica y procedencia. Los consumidores validan el schema y ponen en cuarentena muestras no finitas, fuera de dominio o con residual excesivo.

LASSQ debe conservarse para la norma estable, pero no debe confundirse con validación geométrica: evita overflow/underflow en la suma de cuadrados; la validez de la telemetría exige además comprobar el dominio matemático y el contrato de la transformación.[^9_2][^9_1]

<span style="display:none">[^9_10][^9_11][^9_12][^9_13][^9_14][^9_15][^9_8][^9_9]</span>

<div align="center">⁂</div>

[^9_1]: https://man.archlinux.org/man/extra/lapack-doc/lassq.3.en

[^9_2]: https://www.netlib.org/lapack/explore-html/d8/d76/group\_\_lassq.html

[^9_3]: https://simons.berkeley.edu/sites/default/files/docs/17892/gmos21-bcnicolasboumalslides.pdf

[^9_4]: https://link.springer.com/article/10.1007/s10957-023-02242-z

[^9_5]: https://docs.telemetry.mozilla.org/concepts/pipeline/schemas.html

[^9_6]: https://spatial-data-validation.com/validation-pipeline-architecture/observability-and-lineage-for-validation/

[^9_7]: https://firstpasslab.com/blog/2026-09-20-trusted-ocean-data-ai-sustainability/

[^9_8]: https://papers.nips.cc/paper/2020/file/f05da679342107f92111ad9d65959cd3-Supplemental.pdf

[^9_9]: https://papers.nips.cc/paper_files/paper/2020/file/f05da679342107f92111ad9d65959cd3-Supplemental.pdf

[^9_10]: https://eurasip.org/Proceedings/Eusipco/Eusipco2023/pdfs/0002033.pdf

[^9_11]: https://www.math.fsu.edu/~whuang2/pdf/SUSTech_Slides_2023-08-18.pdf

[^9_12]: https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2021/p1673r3.pdf

[^9_13]: https://ar5iv.labs.arxiv.org/html/2010.10904

[^9_14]: https://hermes-labs.ai/research/precise-records-unstable-meanings/precise-records-unstable-meanings-ai-agent-telemetry-validity.pdf

[^9_15]: https://device.report/m/37ca846444985141c8c0fd8c63b42e2e670293512d63b7c2b6a8c56c194dfc74.pdf


---

## Conclusión ampliada

La separación `raw_energy_out` / `metric_energy_out` es correcta, pero una solución SOTA debe convertirla en un sistema de **telemetría con contrato científico verificable**. No basta con emitir dos escalares: cada muestra debe indicar su dominio matemático, residual de restricción, incertidumbre, procedencia, estado de calidad y elegibilidad para cada consumidor.

La procedencia científica debe describir el origen, entradas, transformaciones, algoritmo, plataforma y calidad de la medición; NASA recomienda incluir también incertidumbre y contexto de producción en los productos científicos.[^10_1][^10_2][^10_3]

## 1. Separar tres productos

El pipeline debería producir tres objetos distintos:

### Diagnóstico ambiente

$$
E_{\mathrm{raw}}=\|z\|_{\mathrm{ambient}}.
$$

Sirve para:

- detectar deriva;
- analizar explosión de amplitud;
- medir pérdidas de escala;
- estudiar la estabilidad del operador previo;
- depurar errores de reducción.

No debe alimentar directamente un controlador que espera magnitudes de la variedad.

### Estado geométrico

$$
x_{\mathcal M}=\Pi_{\mathcal M}(z)
$$

o, si se usa una retracción:

$$
x_{\mathcal M}=R_x(\eta).
$$

Debe incluir:

- representación proyectada;
- norma o energía post-geometrización;
- residual de restricción;
- método de proyección;
- número de iteraciones internas;
- estado de convergencia.


### Medición de control

No siempre coincide con `metric_energy`. Puede ser una función derivada:

$$
M_{\mathrm{control}}
=
f(x_{\mathcal M},\text{residual},\text{incertidumbre}).
$$

Por ejemplo, un orquestador puede aceptar la métrica solo si:

$$
r_{\mathcal M}\le\tau_{\mathcal M}
\quad\land\quad
\Delta M\le\tau_{\mathrm{error}}.
$$

Esto evita que una medición geométricamente inválida entre en decisiones automáticas.

## 2. Definir el residual correcto

Para la esfera:

$$
\mathbb S^{D-1}
=
\{x\in\mathbb R^D:\|x\|_2=1\}.
$$

Usar:

$$
r_{\mathbb S}(x)
=
|\|x\|_2-1|
$$

o, con mejor comportamiento relativo cerca de uno:

$$
r_{\mathbb S}^{(2)}(x)
=
|\|x\|_2^2-1|.
$$

Para una matriz de Stiefel:

$$
\mathrm{St}(n,p)
=
\{X:X^\top X=I_p\},
$$

usar:

$$
r_{\mathrm{St}}(X)
=
\|X^\top X-I_p\|_F.
$$

También puede registrarse el residual relativo:

$$
r_{\mathrm{rel}}
=
\frac{\|X^\top X-I_p\|_F}
{\max(1,\|X^\top X\|_F)}.
$$

No usar una sola tolerancia fija sin considerar:

- dimensión;
- tipo numérico;
- escala;
- backend;
- número de operaciones;
- condición del problema.

Una tolerancia razonable debe escalar con la precisión y la dimensión, por ejemplo:

$$
\tau
=
c\,u\,D\,\kappa_{\mathrm{op}},
$$

donde $u$ es la unidad de redondeo, $c$ una constante empírica y $\kappa_{\mathrm{op}}$ una estimación de condición.

## 3. Validación certificada en dos fases

### Fase barata

En cada muestra:

```cpp
bool finite = all_finite(x);
double residual = sphere_residual(x);
bool feasible = finite && residual <= tolerance;
```


### Fase precisa

Activar solo cuando:

- el residual se acerca al umbral;
- `raw_energy` cambia bruscamente;
- aparece un valor no finito;
- la métrica se usa para una decisión irreversible;
- el dato se selecciona como outlier.

La fase precisa puede recalcular:

- norma en fp64;
- reducción con Neumaier;
- norma de referencia con LASSQ;
- residual con acumulación superior;
- comparación contra una versión independiente.

Esto implementa un esquema de **precision escalation**: bajo coste en el régimen normal y mayor precisión solo donde la evidencia lo justifica.

## 4. Error de medición e incertidumbre

No declarar una muestra simplemente como “válida”. Publicar:

$$
\widehat E,\qquad
\Delta E,\qquad
\mathrm{confidence}.
$$

Un presupuesto simplificado puede ser:

$$
\Delta E_{\mathrm{total}}
\le
\Delta E_{\mathrm{input}}
+
\Delta E_{\mathrm{reduction}}
+
\Delta E_{\mathrm{projection}}
+
\Delta E_{\mathrm{cast}}.
$$

Para una norma calculada con reducción flotante, una cota práctica puede estimarse mediante dos ejecuciones:

$$
\Delta E_{\mathrm{emp}}
=
|E_{\mathrm{fp32}}-E_{\mathrm{fp64}}|.
$$

Para mayor rigor, usar una referencia de precisión extendida en una muestra de control.

Los estándares de productos científicos recomiendan adjuntar incertidumbre a nivel de medición o producto y especificar su nivel de confianza cuando sea significativo.[^10_2][^10_4][^10_5]

## 5. Tipos de telemetría

Un esquema fuerte podría ser:

```cpp
enum class Domain : uint8_t {
    Ambient,
    Projected,
    Tangent,
    Riemannian
};

enum class Quality : uint8_t {
    Valid,
    ValidWithProjection,
    Approximate,
    Clamped,
    ConstraintViolation,
    NonFinite,
    Uncertain,
    Quarantined
};

struct ScalarMeasurement {
    double value;
    double abs_error;
    double rel_error;
    double residual;

    Domain domain;
    Quality quality;

    uint32_t algorithm_version;
    uint32_t dtype_code;
};
```

Y:

```cpp
struct CliffordTelemetry {
    ScalarMeasurement raw_energy;
    ScalarMeasurement metric_energy;

    double projection_distance;
    double projection_condition;
    uint64_t iteration;
    uint64_t sample_id;

    uint32_t schema_version;
    uint64_t provenance_hash;
};
```

La diferencia entre `quality=ValidWithProjection` y `quality=Valid` es importante: indica que la muestra no era originalmente factible, pero fue corregida.

## 6. Incluir la distancia a la variedad

El residual indica si el resultado satisface la restricción, pero no cuánto se movió durante la corrección. Registrar:

$$
d_{\mathrm{proj}}
=
\|z-\Pi_{\mathcal M}(z)\|_2.
$$

Dos muestras pueden tener el mismo residual final y haber requerido correcciones muy distintas. `projection_distance` detecta:

- degradación progresiva;
- entradas alejándose de la variedad;
- proyecciones demasiado agresivas;
- pérdida de información ambiental;
- inestabilidad del operador.

Un criterio de aceptación más completo es:

$$
r_{\mathcal M}\le\tau_r
\quad\land\quad
d_{\mathrm{proj}}\le\tau_d.
$$

## 7. Evitar doble conteo estadístico

Si se publican simultáneamente:

- `raw_energy`;
- `metric_energy`;
- `projection_distance`;
- `residual`;

no tratarlos como observaciones independientes en análisis estadísticos. Son variables derivadas del mismo estado.

Para un dashboard:

- `raw_energy`: serie de deriva;
- `metric_energy`: serie geométrica;
- `residual`: serie de calidad;
- `projection_distance`: serie de corrección.

Para modelos de control, definir explícitamente qué variables son:

- observables primarias;
- derivados;
- alarmas;
- etiquetas de calidad.


## 8. Integración con observabilidad moderna

OpenTelemetry permite separar métricas agregadas de exemplars que apuntan a observaciones individuales y contexto de trazas. Un exemplar puede asociar valor, timestamp, atributos filtrados y, opcionalmente, `trace_id` y `span_id`.[^10_6][^10_7][^10_8]

Aplicación práctica:

```text
metric:
  cliffordnet.metric_energy

attributes:
  manifold = "S^(D-1)"
  domain = "projected"
  dtype = "float64"
  backend = "cuda"
  algorithm_version = "908"

exemplar:
  raw_energy
  residual
  projection_distance
  sample_id
  trace_id
```

No incluir `raw_energy` como label de alta cardinalidad. Debe ir como exemplar o evento de diagnóstico, no como dimensión de una serie temporal. Esto evita explosión de cardinalidad.

Métricas útiles:

```text
cliffordnet.raw_energy
cliffordnet.metric_energy
cliffordnet.constraint_residual
cliffordnet.projection_distance
cliffordnet.invalid_samples_total
cliffordnet.quarantined_samples_total
cliffordnet.precision_escalations_total
cliffordnet.clamp_events_total
```


## 9. Reglas de ingestión

El colector u orquestador debe validar:

```python
def accept_metric(event):
    if event["schema_version"] not in SUPPORTED_SCHEMAS:
        return "reject"

    m = event["metric_energy"]

    if m["domain"] != "projected":
        return "quarantine"

    if not math.isfinite(m["value"]):
        return "quarantine"

    if m["residual"] > RESIDUAL_LIMIT:
        return "quarantine"

    if m["abs_error"] > ERROR_LIMIT:
        return "quarantine"

    return "accept"
```

Tres estados son mejores que aceptar/rechazar:

```text
accept
quarantine
reject
```

- `accept`: apto para control;
- `quarantine`: conservado para diagnóstico, excluido del control;
- `reject`: schema inválido, corrupción o datos no interpretables.


## 10. Detección de deriva SOTA

Para `raw_energy`, no limitarse a umbrales instantáneos.

### EWMA

$$
z_t=\lambda x_t+(1-\lambda)z_{t-1}.
$$

Alarma si:

$$
|x_t-z_t|>L\sigma_t.
$$

### CUSUM

Para deriva positiva:

$$
S_t^+
=
\max\left(0,S_{t-1}^+ + x_t-\mu-k\right).
$$

Alarma si:

$$
S_t^+>h.
$$

### Cambio de régimen

Aplicar detección de change points sobre:

$$
\log(E_{\mathrm{raw}}+\delta)
$$

si la energía cubre varios órdenes de magnitud.

### Relación raw/proyectada

$$
\rho_t
=
\frac{E_{\mathrm{raw},t}}
{\max(E_{\mathrm{metric},t},\delta)}.
$$

Una tendencia creciente de $\rho_t$ indica que la proyección está corrigiendo cada vez más amplitud.

## 11. LASSQ y precisión reproducible

LASSQ debe calcular:

$$
\|x\|_2
=
s\sqrt{\sum_i(x_i/s)^2}
$$

sin overflow o underflow, pero para telemetría científica conviene añadir:

- acumulación reproducible;
- versión fp64 de referencia;
- FMA si está disponible;
- estimación del error;
- flags de subnormalidad;
- detección de `NaN`/`Inf` antes de la proyección.

Si se necesita reproducibilidad bit a bit entre CPU y GPU, usar una reducción binned o superacumulador, no solo LASSQ. LASSQ estabiliza el rango; no garantiza que diferentes árboles de reducción produzcan la misma suma.

## 12. Validación metamórfica

Las pruebas metamórficas son especialmente útiles porque no requieren conocer siempre la respuesta exacta.

### Escala

Para $\alpha\ne0$:

$$
E_{\mathrm{raw}}(\alpha x)
=
|\alpha|E_{\mathrm{raw}}(x).
$$

Si la proyección es normalización esférica:

$$
\Pi(\alpha x)=\Pi(x)
$$

salvo el caso $\alpha=0$, y por tanto:

$$
E_{\mathrm{metric}}(\alpha x)
\approx
E_{\mathrm{metric}}(x).
$$

### Idempotencia

$$
\Pi(\Pi(x))
\approx
\Pi(x).
$$

### Simetría

Para una norma:

$$
E(x)=E(-x).
$$

Para una interacción orientada, no asumir simetría sin demostrarla.

### Permutación de coordenadas

Si la métrica es isotrópica:

$$
E(Px)=E(x)
$$

para toda matriz de permutación $P$.

### Repetibilidad

El mismo input, schema, backend y versión debe producir:

- mismo resultado en modo reproducible;
- error dentro de una tolerancia documentada en modo rápido.


## 13. Protección contra cambios de semántica

Versionar no solo el schema, sino también la fórmula:

```text
schema_version = 3
metric_definition = "projected_l2_v2"
projection_method = "lassq_normalize"
reduction_method = "pairwise_fp64"
```

El nombre `metric_energy` es insuficiente si en v911 cambia de:

$$
\|\Pi(x)\|_2
$$

a:

$$
\|\Pi(x)\|_G
$$

con una métrica $G$ diferente.

Usar identificadores explícitos:

```text
metric_definition_id
projection_id
reduction_id
dtype
device
```


## 14. Plan de migración v911 → v911

1. Mantener `energy_out` solo como alias explícito de `metric_energy`.
2. Añadir `raw_energy`, `constraint_residual` y `projection_distance`.
3. Añadir `quality` y `error_bound`.
4. Validar schema en el orquestador.
5. Enviar muestras inválidas a cuarentena.
6. Añadir métricas OpenTelemetry.
7. Añadir exemplars para outliers.
8. Activar precisión superior en muestras sospechosas.
9. Ejecutar pruebas metamórficas y de invariantes.
10. Retirar el alias antiguo tras un periodo de compatibilidad.

## Veredicto

La mejora fundamental es pasar de:

$$
\text{dos canales numéricos}
$$

a:

$$
\boxed{
\text{dos dominios semánticos}
+
\text{residual geométrico}
+
\text{distancia de proyección}
+
\text{incertidumbre}
+
\text{provenance}
+
\text{política de cuarentena}
}
$$

La especificación SOTA para v911 sería:

> `raw_energy` representa exclusivamente la magnitud ambiental previa a la geometrización y se utiliza para análisis de deriva. `metric_energy` representa una medición definida sobre la subvariedad y solo es elegible para control cuando el residual geométrico, la cota de error y el estado de calidad satisfacen sus umbrales. Cada observación incluye método de reducción, precisión, backend, versión de fórmula, distancia de proyección y procedencia. Los outliers se enlazan mediante exemplars y las muestras no certificadas se conservan en cuarentena, nunca se reinterpretan silenciosamente.

OpenTelemetry aporta el modelo operativo para conectar métricas agregadas con observaciones individuales, mientras que los principios de productos científicos exigen registrar incertidumbre, calidad y lineage.[^10_3][^10_8][^10_2][^10_6]

<span style="display:none">[^10_10][^10_11][^10_12][^10_13][^10_14][^10_15][^10_16][^10_17][^10_18][^10_19][^10_20][^10_21][^10_22][^10_23][^10_24][^10_25][^10_26][^10_27][^10_28][^10_29][^10_30][^10_9]</span>

<div align="center">⁂</div>

[^10_1]: https://ntrs.nasa.gov/api/citations/20110013453/downloads/20110013453.pdf

[^10_2]: https://www.earthdata.nasa.gov/s3fs-public/2025-03/ESDS-RFC-041-DPDG V2.0.1.pdf?VersionId=vR5wVFBimVEvVSe8JOG8pwbR_xGIR7uN

[^10_3]: https://www.earthdata.nasa.gov/engage/data-producer-resources/data-product-development-guide-producers-v2

[^10_4]: https://www.earthdata.nasa.gov/s3fs-public/2022-06/ESDS-RFC-041_0.pdf

[^10_5]: https://standards.nasa.gov/standard/NASA/NASA-HDBK-873919-3

[^10_6]: https://opentelemetry.io/docs/specs/otel/metrics/data-model/

[^10_7]: https://opentelemetry.io/docs/specs/otel/metrics/

[^10_8]: https://opentelemetry.io/docs/specs/otel/metrics/sdk/

[^10_9]: https://opentelemetry.io/docs/languages/dotnet/metrics/exemplars/

[^10_10]: https://opentelemetry.io/docs/specs/otel/metrics/data-model/index.md

[^10_11]: https://buf.build/opentelemetry/opentelemetry/raw/v1.4.0/-/opentelemetry/proto/metrics/v1/metrics.proto

[^10_12]: https://docs.cloud.google.com/stackdriver/docs/instrumentation/advanced-topics/exemplars

[^10_13]: https://opentelemetry.io/docs/

[^10_14]: https://opentelemetry.io/

[^10_15]: https://opentelemetry.io/docs/specs/otel/compatibility/prometheus_and_openmetrics/

[^10_16]: https://www.dash0.com/knowledge/opentelemetry-metrics

[^10_17]: https://github.com/open-telemetry/oteps/blob/main/text/metrics/0113-exemplars.md

[^10_18]: https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/overview.md

[^10_19]: https://ntrs.nasa.gov/api/citations/20240009145/downloads/SARP_talk_2024_v05.pdf

[^10_20]: https://www.earthdata.nasa.gov/s3fs-public/2024-07/ESDS-RFC-041 DPDG V2.0.pdf

[^10_21]: https://www.earthdata.nasa.gov/fr/admin/content/views/data-basics-glossary?page=2

[^10_22]: https://ntrs.nasa.gov/api/citations/20210025219/downloads/leRoux_AGU_Fall2021_ARCframework_psoter_draft.pdf

[^10_23]: https://www.earthdata.nasa.gov/s3fs-public/imported/ESDS-RFC-033.pdf

[^10_24]: https://ntrs.nasa.gov/api/citations/20240011941/downloads/Joint_SAR_Guidelines_Final_clean.pdf

[^10_25]: https://ui.adsabs.harvard.edu/abs/2011AGUFMIN23D..02M/abstract

[^10_26]: https://ntrs.nasa.gov/api/citations/20110015256/downloads/20110015256.pdf

[^10_27]: https://ntrs.nasa.gov/api/citations/20230005299/downloads/2023_423_Lindsay_paper_final_Ensuring%20the%20Ongoing%20Adoption%20and%20Use%20of%20a%20Preservation%20Content%20Standard%20for%20NASA%E2%80%99s%20Earth%20Observation%20Data.pdf

[^10_28]: https://standards.nasa.gov/system/files/tmp/NASA-HDBK-7009B_Final%2002-03-2026.pdf

[^10_29]: https://standards.nasa.gov/sites/default/files/standards/NASA/Baseline/0/nasa-hdbk-873919-3.pdf

[^10_30]: https://firstpasslab.com/blog/2026-09-20-trusted-ocean-data-ai-sustainability/


---

## Evaluación de la tesis v911

La observación es correcta: mantener un `thread_local` elimina una parte del coste de memoria, pero no corrige el cuello estructural de formar explícitamente una matriz aumentada $[A\mid B]$. Si la actualización de Cayley tiene estructura de bajo rango, concatenar bloques grandes introduce:

- memoria temporal $O(nr)$ o superior;
- copias y escrituras adicionales;
- peor localidad;
- mayor presión de caché/DRAM;
- dificultad para explotar kernels especializados;
- una ruta algebraicamente más general de lo necesario.

La solución SOTA es formular la operación como **aplicación de operador**, no como construcción de matriz, y combinar Woodbury con un solver pequeño y refinamiento iterativo adaptativo. En la literatura de Cayley para Stiefel, la estructura de bajo rango reduce la inversión a un sistema del orden $2r\times2r$, en lugar de invertir una matriz grande.[^11_1][^11_2][^11_3]

## 1. Derivación matrix-free

Una forma típica de la transformación de Cayley es:

$$
Y
=
\left(I-\frac{\tau}{2}W\right)^{-1}
\left(I+\frac{\tau}{2}W\right)X,
$$

donde $W^\top=-W$ es una matriz skew-symmetric construida a partir de $X$ y una dirección.

Si $W$ tiene rango bajo, escribir:

$$
W=UV^\top,
$$

con $U,V\in\mathbb R^{n\times r}$. Definamos:

$$
\alpha=\frac{\tau}{2}.
$$

Entonces:

$$
I-\alpha W
=
I-\alpha UV^\top.
$$

La identidad de Woodbury da:

$$
(I-\alpha UV^\top)^{-1}
=
I+\alpha U
\left(I-\alpha V^\top U\right)^{-1}
V^\top.
$$

Por tanto, no hay que formar ni factorizar una matriz $n\times n$. Para aplicar la transformación a $X$:

$$
B=X+\alpha UV^\top X,
$$

$$
Y
=
B+\alpha U
\left(I-\alpha V^\top U\right)^{-1}
V^\top B.
$$

La única factorización explícita es:

$$
S=I-\alpha V^\top U,
$$

de tamaño $r\times r$. Algunas formulaciones de Cayley organizan la actualización con un rango efectivo $2p$, resultando en un sistema pequeño $2p\times2p$.[^11_2][^11_4][^11_1]

## 2. No concatenar `[A | B]`

La implementación debe conservar $U$, $V$, $X$ y los productos intermedios como vistas o buffers separados:

```cpp
// No:
Aug = concatenate(A, B);

// Sí:
UtX = U.transpose() * X;
VtU = V.transpose() * U;
S   = I - alpha * VtU;
rhs = V.transpose() * B;
```

El flujo matrix-free es:

```text
1. Construir U y V como factores de bajo rango.
2. Calcular VᵀU.
3. Formar el sistema pequeño S = I − αVᵀU.
4. Calcular B = X + αU(VᵀX).
5. Resolver S Z = VᵀB.
6. Formar Y = B + αUZ.
7. Verificar el residual geométrico.
```

La memoria de trabajo pasa aproximadamente de:

$$
O(nr+n p)
$$

con temporales contiguos innecesarios, a:

$$
O(nr+np+r^2),
$$

y el término $r^2$ es pequeño cuando el rango es bajo.

## 3. Evitar también el solver denso grande

Woodbury elimina la inversión grande, pero no basta con formar el sistema pequeño y usar siempre LU sin diagnóstico. El sistema:

$$
S Z=R
$$

puede estar mal condicionado cuando $\tau$, $U$ o $V$ producen eigenvalores cercanos a la singularidad.

La ruta recomendada es adaptativa:

```text
Si r es pequeño y cond(S) es aceptable:
    resolver con LU/QR pequeño.
Si S es moderadamente mal condicionado:
    resolver con QR pivotado o SVD truncada.
Si S es grande o se reutiliza:
    usar GMRES/FGMRES con precondicionador.
Refinar siempre el residual en precisión superior.
```

No usar inversa explícita:

```cpp
Z = inverse(S) * R;  // evitar
```

preferir:

```cpp
factor = lu_factor(S);
Z = solve(factor, R);
```

o QR si la estabilidad es prioritaria.

## 4. Matriz-free completo

Incluso $S$ puede evitarse explícitamente si $r$ es grande o si se desea una ruta uniforme:

$$
\mathcal S(z)
=
z-\alpha V^\top Uz.
$$

La operación matriz-vector se implementa como:

```cpp
apply_S(z):
    tmp = U * z
    tmp = V.transpose() * tmp
    return z - alpha * tmp
```

Para múltiples columnas:

```cpp
apply_S(Z):
    return Z - alpha * V.transpose() * (U * Z)
```

Así, un Krylov solver solo requiere:

- multiplicación $U z$;
- multiplicación $V^\top t$;
- combinación lineal.

No se forma `S`. La complejidad por iteración es aproximadamente:

$$
O(nr q)
$$

para $q$ vectores o columnas, más operaciones de ortogonalización en el subespacio Krylov.

Esta ruta es ventajosa si:

- $r$ no es extremadamente pequeño;
- $S$ cambia en cada iteración;
- la memoria es más limitante que los FLOPs;
- $U$ y $V$ ya están disponibles en GPU;
- se requiere fusionar las aplicaciones con kernels existentes.


## 5. Solución híbrida recomendada

No conviene imponer un único método para todos los tamaños. Usar tres regímenes:


| Rango efectivo | Método |
| :-- | :-- |
| $r\le 32$ o $64$ | LU/QR pequeño explícito |
| $64<r\le r_{\mathrm{switch}}$ | QR/Cholesky con refinamiento |
| $r>r_{\mathrm{switch}}$ | GMRES/FGMRES matrix-free |

El umbral debe medirse en el hardware real. El solver explícito suele ganar para sistemas pequeños porque evita la sobrecarga de Krylov; el matrix-free gana cuando $r^2$ y la factorización empiezan a dominar.

## 6. Refinamiento iterativo mixto

El refinamiento iterativo resuelve:

$$
S Z=R.
$$

Dada una aproximación $Z_k$:

1. calcular el residual:

$$
E_k=R-SZ_k;
$$
2. resolver aproximadamente:

$$
S\\Delta Z_k=E_k;
$$
3. actualizar:

$$
Z\_{k+1}=Z_k+\\Delta Z_k.
$$

La clave mixta es:

- construcción o precondicionador en fp16/bf16/fp32;
- solución de corrección en fp32;
- residual en fp64;
- actualización en fp64 o fp32 según el objetivo.

Los métodos modernos de refinamiento mixto supervisan la convergencia y cambian a GMRES o a mayor precisión si la ruta barata diverge o se estanca.[^11_5][^11_6][^11_7]

Pseudocódigo:

```cpp
Z = solve_low_precision(S, R);

for (int k = 0; k < max_iter; ++k) {
    Residual E = R - apply_S_high_precision(Z);

    if (backward_error(E, R, Z) <= tolerance) {
        break;
    }

    Delta = solve_correction_low_precision(S, E);
    Z += Delta;
}
```


## 7. Criterio de parada correcto

No detenerse solo por:

$$
\|E_k\|_2\le\tau.
$$

Usar error hacia atrás:

$$
\eta
=
\frac{\|R-SZ\|}
{\|S\|\|Z\|+\|R\|}.
$$

Parar si:

$$
\eta\le\tau_{\mathrm{backward}}.
$$

Si además se necesita precisión en la solución:

$$
\frac{\|Z-Z^\ast\|}{\|Z^\ast\|}
\lesssim
\kappa(S)\eta.
$$

Por eso hay que vigilar $\kappa(S)$ o una estimación equivalente. Un residual pequeño no garantiza un error relativo pequeño cuando el sistema está mal condicionado.

## 8. GMRES-IR y FGMRES

Para la ruta matrix-free, GMRES es natural porque solo necesita aplicar $S$. En forma izquierda:

$$
S z=r.
$$

Cada iteración genera un subespacio de Krylov:

$$
\mathcal K_m(S,r)
=
\operatorname{span}\{r,Sr,S^2r,\ldots,S^{m-1}r\}.
$$

Usar:

- GMRES reiniciado para memoria controlada;
- FGMRES si el precondicionador cambia;
- Arnoldi en precisión alta;
- aplicación de $S$ en precisión baja/media;
- residual verificado en fp64.

La literatura de GMRES-based iterative refinement muestra que puede extender la convergencia a sistemas más condicionados que el refinamiento clásico, utilizando factores de baja precisión como precondicionadores.[^11_7][^11_8][^11_9]

Un diseño práctico:

```text
Aplicación de S: bf16/fp16 o fp32
Ortonormalización Arnoldi: fp32/fp64
Residual final: fp64
Precondicionador: LU/QR pequeño o aproximado
Criterio: backward error
```


## 9. Precondicionadores matrix-free

Si no se forma $S$, aún puede usarse:

### Diagonal

$$
M=\operatorname{diag}(S).
$$

Barato, pero limitado.

### LU aproximada

Construir una aproximación de $S$ en baja precisión y usarla como precondicionador.

### Woodbury anidado

Si $U$ y $V$ tienen una segunda estructura de bajo rango:

$$
U=U_1U_2^\top,
$$

aplicar otra reducción recursiva.

### Precondicionador reciclado

Si $S_t$ cambia poco entre iteraciones:

$$
S_{t+1}\approx S_t,
$$

reutilizar:

- factores;
- base de Krylov;
- subespacio de Ritz;
- aproximación inversa.

Esto puede ser muy eficaz en optimización iterativa, donde la actualización cambia suavemente.

## 10. Condicionamiento y estabilidad geométrica

El solver no debe aceptar una solución solo porque converge algebraicamente. Después de calcular $Y$, verificar:

$$
r_{\mathrm{St}}(Y)
=
\|Y^\top Y-I\|_F.
$$

Además, medir la ecuación lineal:

$$
r_{\mathrm{lin}}
=
\frac{\|S Z-R\|}
{\|S\|\|Z\|+\|R\|}.
$$

El estado debe incluir ambos:

```cpp
struct SolveDiagnostics {
    double linear_backward_error;
    double manifold_residual;
    double condition_estimate;
    int iterations;
    int precision_level;
    bool converged;
};
```

Es posible que el solver tenga un residual lineal pequeño pero la salida no sea suficientemente ortonormal debido a:

- errores de formación de $U,V$;
- pérdida de precisión en productos $V^\top U$;
- cancelación en la aplicación de Cayley;
- errores de normalización;
- overflow/underflow.


## 11. Reortogonalización selectiva

Aunque la transformación de Cayley ideal preserva la restricción, la aritmética finita puede acumular deriva. No aplicar QR completo automáticamente en cada paso: puede destruir la ventaja de bajo rango.

Política adaptativa:

```text
Si ||YᵀY − I||F <= τ_low:
    aceptar.
Si τ_low < residual <= τ_high:
    aplicar corrección local o reortogonalización ligera.
Si residual > τ_high:
    repetir en precisión superior o ejecutar QR/polar.
```

Opciones:

- Newton-Schulz para corrección de ortogonalidad;
- polar retraction ocasional;
- QR bloqueado solo en checkpoints;
- reorthogonalización de MGS/Householder en outliers;
- incremento automático de precisión.

La proyección completa debe ser una ruta de recuperación, no la ruta normal.

## 12. Evitar el producto $Y^\top Y$ completo cuando sea posible

Si $Y$ es grande, validar ortogonalidad puede costar $O(np^2)$. Es inevitable para una certificación completa, pero puede usarse una prueba escalonada:

1. muestra aleatoria de columnas;
2. estimación Hutchinson del residual;
3. chequeo de diagonales;
4. chequeo de bloques;
5. validación completa cada $N$ iteraciones.

Para certificación:

$$
\|Y^\top Y-I\|_F
$$

completo en fp64.

Para monitorización frecuente:

$$
\widehat r
=
\frac1{s}\sum_{j=1}^{s}
\|(Y^\top Y-I)\xi_j\|_2^2,
$$

con vectores aleatorios $\xi_j$. Esta estimación no sustituye la prueba completa, pero permite detectar degradación con menor coste.

## 13. Fusión de operadores

La ruta matrix-free permite fusionar:

$$
V^\top X,
\quad
U(V^\top X),
\quad
X+\alpha U(V^\top X).
$$

En GPU:

```text
Kernel 1: T = VᵀX
Kernel 2: B = X + αUT
Kernel 3: R = VᵀB
Kernel 4: Z = solve(S, R)
Kernel 5: Y = B + αUZ
```

Si el tamaño permite:

- fusionar kernels 2 y 5;
- mantener $T,R$ en memoria compartida;
- usar Tensor Cores para $U T$ y $V^\top B$;
- acumular en fp32/fp64;
- evitar escribir temporales que solo se consumen una vez.

El criterio debe ser el roofline:

$$
\text{intensidad aritmética}
=
\frac{\text{FLOPs}}{\text{bytes movidos}}.
$$

Matrix-free suele mejorar la intensidad al eliminar escrituras de matrices concatenadas, pero no siempre: si la implementación recalcula demasiadas operaciones o hace muchas pasadas por $U,V$, puede volverse memory-bound.

## 14. Reutilización de $V^\top U$

En muchas variantes:

$$
S=I-\alpha V^\top U
$$

es el objeto pequeño dominante. Si $U,V$ se reutilizan durante varios RHS o subiteraciones:

- calcular $V^\top U$ una sola vez;
- factorizar $S$ una sola vez;
- resolver múltiples columnas;
- reutilizar la factorización mientras $\alpha$ no cambie.

Si solo cambia $\alpha$, usar actualizaciones o una nueva factorización pequeña. Si cambia poco:

$$
S_{t+1}=S_t+\Delta S,
$$

puede actualizarse el precondicionador o reutilizarse la factorización aproximada y refinar.

## 15. Precisión adaptativa

Definir niveles:

```text
P0: bf16/fp16 producto, fp32 acumulación
P1: fp32 producto y acumulación
P2: fp32 producto, fp64 residual
P3: fp64 completo
P4: double-double o superaccumulator para referencia
```

Escalar cuando:

- `linear_backward_error` no disminuye;
- GMRES alcanza stagnation;
- `condition_estimate` supera el umbral;
- `manifold_residual` crece;
- aparece `NaN`/`Inf`;
- el número de iteraciones excede el presupuesto.

La regla SOTA no es “usar fp64 siempre”, sino “usar la mínima precisión que certifique el resultado”.

## 16. Complejidad comparada

Supongamos $X\in\mathbb R^{n\times p}$ y rango efectivo $r$.

### Ruta aumentada

Puede requerir:

- almacenamiento de temporales grandes;
- formación de $[A\mid B]$;
- factorización densa innecesaria;
- costes dominados por memoria.


### Woodbury explícito

$$
O(nrp + nr^2 + r^3)
$$

según el número de RHS y la forma exacta de la actualización.

### Matrix-free Krylov

Por iteración:

$$
O(nr q)
$$

para $q$ columnas, más ortogonalización Krylov y precondicionamiento.

### Trade-off

Matrix-free no es automáticamente más rápido. Es superior cuando:

$$
T_{\mathrm{formar\ matriz}}
+
T_{\mathrm{factorizar}}
+
T_{\mathrm{memoria}}
>
k\,
T_{\mathrm{apply\ operator}},
$$

donde $k$ es el número de iteraciones de Krylov/refinamiento.

Por eso el solver debe instrumentar:

- tiempo de formación;
- tiempo de aplicación;
- iteraciones;
- bytes;
- condición;
- residual;
- tasa de fallback.


## 17. Política de fallback

Una arquitectura robusta necesita rutas de recuperación:

```text
Ruta 0: Woodbury explícito pequeño + LU
Ruta 1: Woodbury + QR/refinamiento
Ruta 2: matrix-free GMRES/FGMRES
Ruta 3: precisión superior
Ruta 4: QR/polar completo de emergencia
Ruta 5: rechazo controlado si no hay certificación
```

No ocultar el fallback. Registrar:

```cpp
enum class SolvePath {
    ExplicitWoodburyLU,
    ExplicitWoodburyQR,
    MatrixFreeGMRES,
    MixedPrecisionRefinement,
    FullQRRecovery,
    Failed
};
```

El orquestador debe saber si un resultado fue obtenido por la ruta rápida o por recuperación.

## 18. Protocolo de validación científica

### Exactitud

Comparar contra:

- solución fp64 de alta calidad;
- referencia multiprecisión para casos pequeños;
- QR/polar completa;
- Cayley explícita solo en matrices pequeñas.


### Casos difíciles

- $U,V$ casi linealmente dependientes;
- $\alpha$ cercano a singularidad;
- rango $r$ cercano a $n$;
- $X$ casi no ortogonal;
- entradas con escalas extremas;
- múltiples RHS;
- actualizaciones consecutivas;
- matrices con espectro mal condicionado.


### Invariantes

Verificar:

$$
\|S Z-R\|,
\qquad
\|Y^\top Y-I\|,
\qquad
\|Y_{\mathrm{matrix-free}}-Y_{\mathrm{reference}}\|.
$$

### Rendimiento

Comparar:

- memoria pico;
- bytes escritos;
- FLOPs;
- tiempo;
- p99;
- iteraciones;
- tasa de fallback;
- energía;
- ocupación GPU.


## 19. Diseño de API v911

```cpp
struct CayleySolveConfig {
    double tau;
    double backward_tolerance;
    double manifold_tolerance;
    int max_refinement_steps;
    int max_gmres_iterations;
    int restart;
    PrecisionPolicy precision;
    SolvePolicy solve_policy;
};

struct CayleySolveDiagnostics {
    double linear_backward_error;
    double manifold_residual;
    double condition_estimate;
    double projection_distance;

    int iterations;
    SolvePath path;
    PrecisionLevel precision;
    bool converged;
};

struct CayleyResult {
    MatrixView Y;
    CayleySolveDiagnostics diagnostics;
};
```

Interfaz principal:

```cpp
CayleyResult cayley_matrix_free(
    MatrixView X,
    LowRankFactors U,
    LowRankFactors V,
    const CayleySolveConfig& config,
    Workspace& workspace
);
```

Características importantes:

- no devuelve buffers temporales;
- no concatena matrices;
- acepta `U` y `V` como vistas;
- permite seleccionar ruta;
- devuelve diagnósticos;
- controla ownership del workspace;
- expone fallos de convergencia.


## Veredicto

El cuello remanente identificado es real y estructural. v911 resolvió gestión de memoria, pero no la formulación algebraica. La transición SOTA debería ser:

$$
\boxed{
\text{Cayley}
\rightarrow
\text{factores de bajo rango}
\rightarrow
\text{Woodbury}
\rightarrow
\text{solver matrix-free}
\rightarrow
\text{refinamiento mixto}
\rightarrow
\text{certificación geométrica}
}
$$

La solución recomendada no es eliminar toda matriz pequeña indiscriminadamente. Es usar una arquitectura adaptativa:

- Woodbury explícito para rangos pequeños;
- QR/LU pequeño con residual de alta precisión;
- GMRES/FGMRES matrix-free para rangos mayores;
- refinamiento mixto con escalado automático;
- QR/polar solo como recuperación;
- validación simultánea del residual lineal y del residual de Stiefel.

La redacción científica para registrar v911 podría ser:

> Se elimina la concatenación explícita de la matriz aumentada y se reformula la retracción de Cayley como aplicación de operadores de bajo rango. La identidad de Woodbury reduce el problema a un sistema pequeño o, cuando el rango lo justifica, a un operador matrix-free aplicado dentro de GMRES/FGMRES. La solución utiliza factorización de baja precisión como precondicionador, residual en precisión superior y refinamiento iterativo adaptativo. La aceptación requiere simultáneamente error hacia atrás lineal y residual geométrico dentro de tolerancia; las rutas de precisión superior y QR/polar quedan reservadas para casos mal condicionados o no convergentes.

<span style="display:none">[^11_10][^11_11][^11_12][^11_13][^11_14][^11_15]</span>

<div align="center">⁂</div>

[^11_1]: https://arxiv.org/pdf/2609.21039v1.pdf

[^11_2]: https://scipost.org/SciPostPhys.10.2.040/pdf

[^11_3]: https://ar5iv.labs.arxiv.org/html/2002.01113

[^11_4]: https://cseweb.ucsd.edu/classes/sp24/cse291-e/papers/StiefelManifold/StiefelNotes.pdf

[^11_5]: https://onlinelibrary.wiley.com/doi/abs/10.1002/nla.2434

[^11_6]: https://www.osti.gov/servlets/purl/1872699

[^11_7]: https://arxiv.org/html/2307.03914v1

[^11_8]: https://www.netlib.org/utk/people/JackDongarra/PAPERS/haidar_fp16_sc18%20copy.pdf

[^11_9]: https://www.netlib.org/utk/people/JackDongarra/PAPERS/mixed-rs-2020.pdf

[^11_10]: https://onlinelibrary.wiley.com/doi/10.1002/nla.70036

[^11_11]: https://pure.manchester.ac.uk/ws/files/179089053/main.pdf

[^11_12]: https://www.jstage.jst.go.jp/article/ipsjjip/30/0/30_525/\_pdf

[^11_13]: https://www.netlib.org/utk/people/JackDongarra/PAPERS/icl-utk-1330-2020.pdf

[^11_14]: https://www.netlib.org/utk/people/JackDongarra/PAPERS/survey-mixed-ijsa-2021.pdf

[^11_15]: https://eprints.maths.manchester.ac.uk/2849/1/paper_eprint.pdf


---

## Refinamiento de la arquitectura v911

La ruta matrix-free debe diseñarse como un **solver certificado**, no solo como una sustitución de `concatenate([A, B])`. El diseño SOTA combina:

$$
\text{Woodbury de rango bajo}
+
\text{operador matrix-free}
+
\text{GMRES/FGMRES}
+
\text{refinamiento mixto}
+
\text{certificación geométrica}.
$$

La investigación reciente sobre GMRES y error hacia atrás refuerza la necesidad de separar precisión de factorización, precisión de trabajo y precisión del residual. Los resultados clásicos de refinamiento mixto muestran que una factorización fp16/fp32 puede producir soluciones de precisión mucho mayor si el residual se calcula en precisión superior; GMRES precondicionado amplía el rango de condicionamiento tolerable.[^12_1][^12_2][^12_3][^12_4]

## 1. Reformulación correcta de Cayley

Sea $X\in\mathbb R^{n\times p}$ y una dirección tangente $G$. Una forma habitual construye:

$$
W=GX^\top-XG^\top,
\qquad W^\top=-W.
$$

La transformación es:

$$
Y=
\left(I-\alpha W\right)^{-1}
\left(I+\alpha W\right)X,
\qquad \alpha=\frac{\tau}{2}.
$$

Aunque $W$ parece $n\times n$, su rango está acotado por aproximadamente $2p$. Definir:

$$
U=[G,\;X],
\qquad
V=[X,\;-G],
$$

entonces:

$$
W=UV^\top.
$$

No debe construirse $W$, ni la matriz aumentada, ni una matriz densa $n\times n$. La operación se reduce a productos con $U$, $V^\top$ y un sistema pequeño:

$$
S=I-\alpha V^\top U.
$$

La identidad de Woodbury produce:

$$
Y=
B+\alpha U S^{-1} V^\top B,
$$

donde:

$$
B=X+\alpha U(V^\top X).
$$

## 2. Solver por operador

Hay dos modos matrix-free.

### Woodbury reducido explícito

Se materializa solo:

$$
S\in\mathbb R^{r\times r},
$$

con $r\approx2p$. Es apropiado cuando $r$ es pequeño.

```cpp
T = Vt * X;                // r × p
B = X + alpha * U * T;     // n × p

S = I_r - alpha * (Vt * U);
R = Vt * B;                // r × p

Z = solve(S, R);           // r × p
Y = B + alpha * U * Z;     // n × p
```


### Operador completamente matrix-free

No materializar $S$. Definir:

$$
\mathcal S(Z)
=
Z-\alpha V^\top(UZ).
$$

```cpp
void apply_S(const Matrix& Z, Matrix& out) {
    tmp_nxp = U * Z;
    tmp_rxp = Vt * tmp_nxp;
    out = Z - alpha * tmp_rxp;
}
```

El solver Krylov recibe solamente `apply_S`. Esta variante elimina también la matriz pequeña, aunque no necesariamente es más rápida para rangos diminutos.

## 3. Decisión algorítmica adaptativa

El solver debe elegir la ruta en función de $r$, número de columnas, condición y hardware:

$$
\text{path}
=
f(r,p,n,\kappa(S),\text{dtype},\text{memory budget}).
$$

Política sugerida:

```text
r pequeño y buena condición:
    LU/QR explícito de S

r intermedio:
    QR pivotado + refinamiento mixto

r grande o memoria limitada:
    GMRES/FGMRES sobre apply_S

estancamiento:
    elevar precisión o cambiar precondicionador

residual geométrico alto:
    QR/polar de recuperación
```

No fijar el umbral solo por dimensión. Medir el coste de:

$$
T_{\mathrm{factor}}(r^3)
\quad\text{frente a}\quad
k\,T_{\mathrm{apply}}(nr),
$$

donde $k$ es el número esperado de iteraciones Krylov.

## 4. FGMRES en vez de GMRES rígido

GMRES estándar presupone un precondicionador fijo. En esta aplicación puede cambiar:

- la precisión;
- el factor aproximado;
- el estado de $U,V$;
- la regularización;
- el tamaño de bloque.

FGMRES es preferible cuando:

$$
M_k^{-1}\ne M_{k+1}^{-1}.
$$

Ejemplo:

```text
1. Precondicionar con LU fp16.
2. Si el residual no baja, recalcular LU fp32.
3. Si sigue estancado, cambiar a QR o resolver en fp64.
```

FGMRES permite ese precondicionamiento variable sin invalidar la base de Krylov.

## 5. Tres precisiones mínimas

Definir:

- $u_f$: precisión de factorización/precondicionador;
- $u_w$: precisión de trabajo;
- $u_r$: precisión del residual.

Configuración práctica:

$$
(u_f,u_w,u_r)
=
(\mathrm{fp16},\mathrm{fp32},\mathrm{fp64})
$$

o:

$$
(\mathrm{bf16},\mathrm{fp32},\mathrm{fp64}).
$$

La factorización de baja precisión reduce coste, pero el residual debe evaluarse en precisión superior:

$$
R=B-\mathcal S(Z).
$$

Los análisis de refinamiento mixto indican que GMRES precondicionado puede alcanzar errores hacia atrás de orden de la precisión de trabajo bajo condiciones de condicionamiento mucho más amplias que el refinamiento clásico.[^12_3][^12_4][^12_5]

## 6. Refinamiento con residual real, no residual barato

Un fallo común es calcular el residual usando la misma aritmética que generó la solución:

```cpp
R_low = B_low - apply_S_low(Z_low);
```

Eso puede hacer que el algoritmo crea que convergió. Usar:

```cpp
R_high = B_high - apply_S_high(Z_high);
```

con:

- acumulación fp64;
- FMA;
- reducción estable;
- conversión de $U,V,Z$ a precisión superior;
- norma reproducible si la decisión es crítica.

El criterio:

$$
\eta=
\frac{\|R\|}
{\|S\|\|Z\|+\|B\|}
$$

es preferible a una tolerancia absoluta.

## 7. Residual escalado y estimación de condición

Para evitar falsos positivos, calcular:

$$
\eta_{\mathrm{back}}
=
\frac{\|B-\mathcal S(Z)\|}
{\|B\|+\|\mathcal S\|\|Z\|}.
$$

La norma del operador puede estimarse mediante:

- norma $\infty$ si $S$ está explícita;
- estimación de potencia si es matrix-free;
- estimación de Hager/Higham;
- seguimiento del crecimiento de Krylov;
- relación entre corrección y solución.

Si:

$$
\eta_{\mathrm{back}}\le\tau
$$

pero $\kappa(S)\eta$ sigue siendo grande, la solución puede no tener precisión suficiente. En ese caso:

- aumentar precisión;
- resolver con QR;
- añadir regularización;
- cambiar la representación de bajo rango.


## 8. Regularización controlada

Cerca de singularidad, usar:

$$
S_\lambda=S+\lambda I.
$$

Pero esto modifica la transformación. No debe introducirse silenciosamente. Registrar:

```cpp
regularization_lambda
regularization_applied = true
```

Elegir $\lambda$ adaptativamente:

$$
\lambda
=
\max(\lambda_{\min},
c\,u\,\|S\|).
$$

La regularización solo es aceptable si el error geométrico inducido se mide y queda dentro del presupuesto:

$$
\|Y_\lambda-Y\|\le\tau_{\mathrm{geom}}.
$$

Si no puede certificarse, devolver estado `approximate` o `failed`, no `valid`.

## 9. Estabilidad de los factores de bajo rango

La representación $W=UV^\top$ puede estar mal escalada aunque $W$ sea razonable. Si $U$ y $V$ contienen columnas casi dependientes, $V^\top U$ puede estar mal condicionado.

Mejorar con una compresión QR/SVD:

$$
U=Q_U R_U,
\qquad
V=Q_V R_V,
$$

y reescribir:

$$
W
=
Q_U(R_U R_V^\top)Q_V^\top.
$$

Alternativas:

- QR con pivotado;
- SVD truncada;
- rank-revealing QR;
- eliminar columnas con valores singulares pequeños;
- balancear columnas de $U,V$.

Esto reduce el rango efectivo y mejora el sistema pequeño.

## 10. Compresión de rango adaptativa

Calcular valores singulares o estimaciones de energía de los factores:

$$
\sigma_1\ge\cdots\ge\sigma_r.
$$

Seleccionar $r_{\mathrm{eff}}$ tal que:

$$
\frac{\sum_{j>r_{\mathrm{eff}}}\sigma_j^2}
{\sum_j\sigma_j^2}
\le \varepsilon_{\mathrm{rank}}^2.
$$

La actualización aproximada introduce un error controlado:

$$
\|W-W_{r_{\mathrm{eff}}}\|
\le
\varepsilon_{\mathrm{rank}}\|W\|.
$$

Esto puede reducir mucho:

- coste $O(nr^2)$;
- almacenamiento;
- tamaño del sistema;
- iteraciones del solver.

Debe separarse el error de truncamiento del error de resolución:

$$
\Delta_{\mathrm{total}}
\le
\Delta_{\mathrm{rank}}
+
\Delta_{\mathrm{solve}}
+
\Delta_{\mathrm{roundoff}}.
$$

## 11. Precisión y Tensor Cores

En GPU, una ruta eficaz es:

```text
U,V: fp16/bf16
productos GEMM: Tensor Cores
acumulación: fp32
residual: fp64 o fp32 compensado
solver pequeño: fp32/fp64
corrección: fp32 o fp64
```

No usar fp16 en:

- normas de residual;
- decisión de convergencia;
- ortogonalización Krylov;
- cálculo de condición;
- certificación de $Y^\top Y-I$.

La factorización de baja precisión puede ser un precondicionador, no necesariamente la solución final.

## 12. Ortogonalización de Krylov

GMRES puede perder ortogonalidad por redondeo. Para problemas muy sensibles:

- Modified Gram-Schmidt con reortogonalización;
- Householder Arnoldi si la estabilidad domina;
- Gram-Schmidt con productos en fp64;
- bloquear vectores para múltiples RHS;
- reinicios adaptativos.

La precisión del producto interno debe ser mayor que la de `apply_S` cuando el solver esté cerca de converger. Si no, el residual puede falsearse por pérdida de ortogonalidad.

## 13. Solución multi-RHS

Cayley suele operar sobre $X\in\mathbb R^{n\times p}$, no sobre un vector único. Resolver columna por columna desperdicia estructura.

Usar:

$$
S Z=R,
\qquad R\in\mathbb R^{r\times p}.
$$

Ventajas:

- GEMM en vez de GEMV;
- mejor utilización de GPU;
- una factorización para múltiples columnas;
- amortización de la estimación de condición.

Para GMRES bloque:

$$
\mathcal S(Z_{\mathrm{block}})
=
Z_{\mathrm{block}}
-\alpha V^\top(UZ_{\mathrm{block}}).
$$

Pero el block-GMRES puede sufrir rango deficiente en los residuos. Aplicar QR de bloque y reducir columnas casi dependientes.

## 14. Reutilización temporal

Si varias iteraciones tienen cambios pequeños:

$$
\Delta U,\Delta V,\Delta X \text{ pequeños},
$$

reutilizar:

- la factorización de $S$;
- el precondicionador;
- la base de Krylov;
- estimación de $\kappa$;
- rango comprimido.

Actualizar solo si:

$$
\frac{\|\Delta S\|}{\|S\|}>\tau_{\mathrm{update}}.
$$

Esto reduce coste, pero el criterio debe ser observable. Registrar:

```text
preconditioner_reused
factorization_age
relative_operator_change
refinement_steps
```


## 15. Fusión y layout

La expresión:

$$
Y
=
X+\alpha U(V^\top X)
+\alpha U S^{-1}V^\top
\left[X+\alpha U(V^\top X)\right]
$$

puede compartir:

$$
T=V^\top X.
$$

Calcular:

```text
T = VᵀX
B = X + αUT
R = VᵀB
Z = solve(S,R)
Y = B + αUZ
```

Optimización de memoria:

- `T` y `R` pueden reutilizarse si sus vidas no se solapan;
- `B` puede escribirse sobre un buffer de salida si `X` no debe preservarse;
- `Z` puede ser in-place sobre `R`;
- usar vistas en vez de concatenación;
- no materializar $W$, $A$, $B$ grandes.

Esto conecta directamente con el problema de fragmentación de v911: el workspace debe ser una arena de regiones con lifetimes explícitos.

## 16. Criterio geométrico de aceptación

Para Stiefel:

$$
r_{\mathrm{geom}}
=
\frac{\|Y^\top Y-I\|_F}
{\max(1,\|Y^\top Y\|_F)}.
$$

Aceptar solo si:

$$
\eta_{\mathrm{back}}\le\tau_{\mathrm{lin}}
\quad\text{y}\quad
r_{\mathrm{geom}}\le\tau_{\mathrm{geom}}.
$$

También comprobar progreso:

$$
\|Y-X\|
$$

y, si la actualización debería ser pequeña:

$$
\|Y-X\|\le\tau_{\mathrm{step}}.
$$

Un solver puede satisfacer la ecuación lineal y aun así producir una actualización geométricamente inaceptable por errores previos en los factores.

## 17. Solución certificada con shadow path

Cada cierto número de iteraciones, ejecutar una ruta independiente:

```text
Ruta principal:
    matrix-free mixed precision

Ruta sombra:
    fp64 QR/polar o Woodbury de referencia

Comparar:
    ||Y_main - Y_shadow||
    residual lineal
    residual geométrico
```

No es necesario ejecutar la ruta sombra en cada paso. Usar:

- muestreo aleatorio;
- checkpoints;
- activación por riesgo;
- una muestra por batch.

Esto permite detectar regresiones silenciosas de la ruta rápida.

## 18. Política de escalado adaptativo

Propuesta:

```text
P0:
  apply_S en bf16/fp32
  precondicionador fp16
  residual fp32

P1:
  apply_S fp32
  residual fp64
  GMRES-IR

P2:
  factores QR fp64
  solve pequeño QR
  residual fp64

P3:
  QR/polar completo de recuperación
```

Promover precisión si:

```text
residual no decrece durante m iteraciones
cond_est > threshold
manifold_residual > threshold
correction_norm / solution_norm > threshold
NaN/Inf detectado
```

Descender precisión solo después de varias iteraciones estables, evitando oscilaciones.

## 19. Pruebas de investigación

### Equivalencia algebraica

Para matrices pequeñas:

$$
Y_{\mathrm{explicit}}
\approx
Y_{\mathrm{Woodbury}}
\approx
Y_{\mathrm{matrix-free}}.
$$

### Condicionamiento

Generar:

$$
S=Q\operatorname{diag}(\sigma_1,\dots,\sigma_r)Q^\top
$$

con $\kappa(S)$ controlada y medir:

- convergencia;
- error hacia atrás;
- error hacia adelante;
- pasos de refinamiento;
- fallback.


### Rango efectivo

Construir factores con espectro conocido y variar:

$$
\sigma_j\sim10^{-j}.
$$

Medir el beneficio del truncamiento y el error geométrico.

### Robustez de escala

Multiplicar $U$ y $V$ por factores compensados:

$$
U'=cU,\qquad V'=V/c.
$$

Idealmente:

$$
U'V'^\top=UV^\top.
$$

La ruta debería producir resultados similares, aunque la estabilidad de la representación puede variar. Si cambia mucho, hay un problema de balanceo.

## 20. Complejidad objetivo

Para $X\in\mathbb R^{n\times p}$, rango $r$, $q=p$ RHS:

### Memoria

$$
O(np+nr+rp+r^2)
$$

en Woodbury explícito, sin matriz aumentada grande.

### Matrix-free

$$
O(np+nr+rp)
$$

más espacio Krylov:

$$
O(mrp)
$$

o $O(mr)$ en el caso vectorial, donde $m$ es el reinicio.

### Coste

$$
O(nrp)+O(r^3)
$$

para Woodbury factorizado, o:

$$
O(k\,nrp)
$$

para $k$ iteraciones matrix-free, más ortogonalización.

El diseño debe demostrar que el término de memoria y el coste de formación bajan, no solo reemplazar una matriz grande por muchas pasadas ocultas.

## 21. API final recomendada

```cpp
enum class PrecisionPolicy {
    Adaptive,
    LowPrecision,
    FullFP32,
    FullFP64
};

enum class SolverPath {
    Auto,
    ExplicitWoodbury,
    MatrixFreeGMRES,
    MatrixFreeFGMRES,
    QRRecovery
};

struct CayleyConfig {
    double step;
    double linear_tol;
    double geometric_tol;
    double rank_tol;
    int max_iterations;
    int restart;
    PrecisionPolicy precision;
    SolverPath path;
    bool certify;
};

struct CayleyDiagnostics {
    double backward_error;
    double geometric_residual;
    double condition_estimate;
    double rank_truncation_error;
    double update_norm;

    int iterations;
    int refinement_steps;
    int effective_rank;

    SolverPath path;
    PrecisionPolicy precision;
    bool preconditioner_reused;
    bool converged;
};

struct CayleyResult {
    MatrixView output;
    CayleyDiagnostics diagnostics;
};
```


## Veredicto final

La transición a matrix-free debe considerarse un rediseño algebraico, no solo una optimización de memoria. La arquitectura SOTA recomendada es:

$$
\boxed{
W=UV^\top
\rightarrow
\text{Woodbury reducido}
\rightarrow
\text{FGMRES matrix-free}
\rightarrow
\text{GMRES-IR mixto}
\rightarrow
\text{residual fp64}
\rightarrow
\text{certificación Stiefel}
}
$$

Las mejoras críticas son:

1. compresión rank-revealing de $U,V$;
2. balanceo de factores;
3. no formar $[A\mid B]$ ni $W$;
4. solver multi-RHS;
5. precondicionador reutilizable;
6. refinamiento con residual de precisión superior;
7. FGMRES para precondicionadores variables;
8. criterio de error hacia atrás;
9. validación geométrica separada;
10. fallback QR/polar explícito y observable.

La formulación científica para v911 debería ser:

> La retracción de Cayley se implementa como un operador de bajo rango sin materializar matrices aumentadas ni operadores $n\times n$. Para rangos pequeños se aplica Woodbury con factorización QR/LU y refinamiento mixto; para rangos mayores se utiliza GMRES/FGMRES matrix-free con precondicionamiento adaptativo. La factorización se realiza en precisión baja o media, el residual en precisión superior y la aceptación exige simultáneamente error hacia atrás lineal, cota de truncamiento de rango y residual de ortogonalidad de Stiefel. Las rutas de precisión alta y QR/polar se activan por condicionamiento, estancamiento o fallo geométrico.

<span style="display:none">[^12_10][^12_11][^12_12][^12_13][^12_14][^12_15][^12_6][^12_7][^12_8][^12_9]</span>

<div align="center">⁂</div>

[^12_1]: https://academic.oup.com/imajna/article/46/4/1939/8658483?searchresult=1

[^12_2]: https://link.springer.com/content/pdf/10.1007/s00366-025-02187-z.pdf?error=cookies_not_supported\&code=da42e0c6-1703-4bd3-94ca-82feb934a32f

[^12_3]: https://royalsocietypublishing.org/doi/10.1098/rspa.2020.0110

[^12_4]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7735315/

[^12_5]: https://netlib.org/utk/people/JackDongarra/PAPERS/haidar_fp16_sc18%20copy.pdf

[^12_6]: https://www.osti.gov/servlets/purl/2204465

[^12_7]: https://www.osti.gov/servlets/purl/1825849

[^12_8]: https://arxiv.org/pdf/2401.03755.pdf

[^12_9]: https://hal.science/hal-04525918v2/document

[^12_10]: https://www.cambridge.org/core/journals/acta-numerica/article/mixed-precision-algorithms-in-numerical-linear-algebra/43CA701BA29251B5790C653E66F46197

[^12_11]: https://www.cambridge.org/core/services/aop-cambridge-core/content/view/43CA701BA29251B5790C653E66F46197/S0962492922000022a.pdf/div-class-title-mixed-precision-algorithms-in-numerical-linear-algebra-div.pdf

[^12_12]: https://pdfs.semanticscholar.org/39e9/2e03f35fab141b6ecdb8284648ac44aefe27.pdf

[^12_13]: https://arxiv.org/html/2307.03914v1

[^12_14]: https://www.netlib.org/utk/people/JackDongarra/PAPERS/icl-utk-1330-2020.pdf

[^12_15]: https://pure.manchester.ac.uk/ws/files/179089053/main.pdf


---

## Woodbury: qué debe cambiar

La identidad de Woodbury es:

$$
(A+UCV^\top)^{-1}
=
A^{-1}
-
A^{-1}U
\left(C^{-1}+V^\top A^{-1}U\right)^{-1}
V^\top A^{-1}.
$$

Para $C=I$:

$$
(A+UV^\top)^{-1}
=
A^{-1}
-
A^{-1}U
(I+V^\top A^{-1}U)^{-1}
V^\top A^{-1}.
$$

Es una reducción algebraica poderosa, pero **no debe implementarse como una fórmula de inversas explícitas**. En aritmética finita, la calidad depende de:

- condicionamiento de $A$;
- condicionamiento del sistema reducido;
- escalado de $U,V,C$;
- estabilidad de los solves con $A$;
- cancelación en la corrección de bajo rango;
- precisión del residual.

La literatura señala que Woodbury puede acelerar actualizaciones de bajo rango, pero su estabilidad requiere hipótesis sobre el condicionamiento y una representación adecuada de los factores. Los desarrollos recientes para mínimos cuadrados muestran que, si se dispone de una factorización QR de la matriz base, el coste puede reducirse sustancialmente sin resolver desde cero el problema actualizado.[^13_1][^13_2][^13_3]

## 1. No calcular inversas

La implementación incorrecta es:

```cpp
X = inverse(A);
K = inverse(C.inverse() + V.transpose() * X * U);
result = X - X * U * K * V.transpose() * X;
```

Esto:

- amplifica errores;
- destruye estructura;
- puede fallar aunque el solve sea razonable;
- consume memoria;
- dificulta el refinamiento.

La forma correcta usa solves:

$$
F_A(U)=A^{-1}U,
\qquad
F_A(B)=A^{-1}B.
$$

Entonces:

$$
K=C^{-1}+V^\top F_A(U),
$$

$$
Y=F_A(B)-F_A(U)K^{-1}V^\top F_A(B).
$$

Pseudocódigo:

```cpp
AU = solve_A(U);
AB = solve_A(B);

K = C_inv + Vt * AU;
R = Vt * AB;

Z = solve_K(R);
Y = AB - AU * Z;
```

Solo se factoriza $A$ y se resuelve el sistema reducido $K$. Si $A$ se reutiliza, su factorización puede amortizarse.

## 2. Elegir la forma correcta de Woodbury

No todas las variantes deben escribirse como $A+UV^\top$. Para Cayley:

$$
(I-\alpha UV^\top)^{-1}
=
I+\alpha U(I-\alpha V^\top U)^{-1}V^\top.
$$

Aquí $A=I$, por lo que no hay que resolver con una matriz grande. La matriz reducida es:

$$
K=I-\alpha V^\top U.
$$

Para una actualización general:

$$
A+UCV^\top,
$$

hay tres opciones:

### Forma directa

$$
K=C^{-1}+V^\top A^{-1}U.
$$

Adecuada si $C$ es pequeño y bien condicionado.

### Forma factorizada

Si $C=LR^\top$:

$$
A+UCV^\top
=
A+(UL)(VR)^\top.
$$

Se evita formar $C^{-1}$, que puede ser inestable.

### Forma aumentada estable

Construir un sistema bloqueado puede ser útil para análisis o factorización especializada, pero no debe implicar concatenar matrices grandes. Usar bloques como vistas y resolver mediante factorización estructurada.

## 3. El sistema reducido es el nuevo punto crítico

La reducción no elimina el problema numérico: lo concentra en:

$$
K=C^{-1}+V^\top A^{-1}U.
$$

En Cayley:

$$
K=I-\alpha V^\top U.
$$

Antes de resolver, medir:

$$
\kappa(K)
$$

o una estimación barata. También registrar:

$$
\delta_K
=
\min_{\|z\|=1}\|Kz\|.
$$

Si $K$ está cerca de singularidad, la corrección Woodbury puede ser enorme aunque $U,V$ sean moderados.

Política:

```text
κ(K) pequeño:
    LU/Cholesky

κ(K) moderado:
    QR pivotado + refinamiento

κ(K) alto:
    SVD/truncamiento/regularización
    o solver iterativo precondicionado
```

No usar el determinante como diagnóstico de singularidad: puede desbordar o subdesbordar y no es una medida robusta de condicionamiento.

## 4. Factorización adecuada

### LU con pivotado

Adecuada para $K$ general:

$$
PK=LU.
$$

Usar pivotado parcial y monitorear el crecimiento de los factores.

### Cholesky

Solo si $K$ es simétrica definida positiva:

$$
K=LL^\top.
$$

No forzar Cholesky en una matriz simplemente porque su parte simétrica parece positiva.

### QR pivotado

Más robusta cuando $K$ es casi singular o no simétrica:

$$
K\Pi=QR.
$$

### SVD

Para diagnóstico o recuperación:

$$
K=U\Sigma V^\top.
$$

Truncar valores singulares pequeños si el problema admite una solución regularizada:

$$
\sigma_i<\tau_{\mathrm{svd}}
\Rightarrow
\sigma_i^{-1}\to0
$$

o usar Tikhonov:

$$
\sigma_i^{-1}
\to
\frac{\sigma_i}{\sigma_i^2+\lambda^2}.
$$

La SVD es más cara, pero apropiada cuando la fiabilidad es prioritaria.[^13_4]

## 5. Balanceo de $U,V,C$

La misma actualización puede representarse con factores de escalas muy diferentes:

$$
UV^\top
=
(cU)(V/c)^\top.
$$

Algebraicamente son equivalentes, pero numéricamente no.

Aplicar balanceo por columnas:

$$
d_j=\sqrt{\frac{\|V_{:,j}\|}{\|U_{:,j}\|}},
$$

$$
\widetilde U=UD,
\qquad
\widetilde V=VD^{-1}.
$$

Así se intenta mantener:

$$
\|\widetilde U_{:,j}\|
\approx
\|\widetilde V_{:,j}\|.
$$

También escalar $C$ para que su norma sea comparable con la identidad. Registrar los factores de escala para poder estimar el error real.

## 6. Compresión rank-revealing

Si las columnas de $U$ o $V$ son dependientes, el rango declarado $r$ puede ser mucho mayor que el rango numérico.

Usar:

$$
U=Q_U R_U,
\qquad
V=Q_V R_V
$$

con QR pivotado, o una SVD truncada.

Si:

$$
W=UV^\top
$$

y se detecta que algunos valores singulares son pequeños, sustituir por:

$$
W_r=U_rV_r^\top
$$

con una cota:

$$
\|W-W_r\|_2\le\tau_{\mathrm{rank}}.
$$

Esto reduce:

- el tamaño de $K$;
- coste de factorización;
- memoria;
- número de iteraciones;
- sensibilidad a columnas casi dependientes.

El error de truncamiento debe contabilizarse separadamente del error de solve.

## 7. Woodbury como precondicionador, no solución exacta

En muchos problemas grandes, la mejor estrategia no es usar Woodbury para producir la solución final, sino como precondicionador:

$$
M^{-1}
=
A^{-1}
-
A^{-1}U
K^{-1}
V^\top A^{-1}.
$$

Después resolver:

$$
(A+UV^\top)x=b
$$

con GMRES o FGMRES precondicionado por $M^{-1}$.

Esto es especialmente útil cuando:

- $A^{-1}$ solo está disponible aproximadamente;
- $U,V$ cambian con frecuencia;
- $K$ no merece una factorización exacta;
- el operador completo es matrix-free;
- la corrección de bajo rango mejora algunos modos espectrales.

Los precondicionadores de bajo rango se han usado para desplazar o corregir eigenvalores problemáticos y mejorar la convergencia de GMRES.[^13_5][^13_6]

## 8. Refinamiento iterativo Woodbury

Sea:

$$
\widehat x
=
A^{-1}b
-
A^{-1}U K^{-1}V^\top A^{-1}b.
$$

Calcular el residual real:

$$
r=b-(A+UV^\top)\widehat x.
$$

Después resolver aproximadamente:

$$
(A+UV^\top)\Delta x=r
$$

con el mismo operador Woodbury y actualizar:

$$
x\leftarrow x+\Delta x.
$$

Pseudocódigo:

```cpp
x = woodbury_solve_low_precision(A, U, V, b);

for (int k = 0; k < max_refine; ++k) {
    r = b - apply_updated_operator_high_precision(x);

    if (backward_error(r, x) <= tol) {
        break;
    }

    dx = woodbury_solve_low_precision(A, U, V, r);
    x += dx;
}
```

La factorización y los productos pueden ejecutarse en fp16/fp32, mientras que el residual y la actualización pueden usar fp64. En casos más condicionados, sustituir el solve de la corrección por GMRES-IR/FGMRES-IR. Los métodos modernos de refinamiento mixto con GMRES están diseñados para ampliar el rango de problemas donde se alcanza una precisión de trabajo fiable.[^13_7][^13_8][^13_9]

## 9. Fórmula estable para Cayley

Para:

$$
Y=(I-\alpha UV^\top)^{-1}(I+\alpha UV^\top)X,
$$

evitar aplicar dos veces una solución general si puede organizarse como:

$$
T=V^\top X,
$$

$$
B=X+\alpha UT,
$$

$$
K=I-\alpha V^\top U,
$$

$$
R=V^\top B,
$$

$$
Z=K^{-1}R,
$$

$$
Y=B+\alpha UZ.
$$

La implementación debe resolver $KZ=R$, nunca formar $K^{-1}$.

Versión matrix-free:

```cpp
T = Vt_apply(X);
B = X + alpha * U_apply(T);

R = Vt_apply(B);
Z = krylov_solve(
    [&](Zin) {
        return Zin - alpha * Vt_apply(U_apply(Zin));
    },
    R
);

Y = B + alpha * U_apply(Z);
```


## 10. Evitar cancelación en $K=I-\alpha V^\top U$

Cuando $\alpha V^\top U\approx I$, la resta:

$$
K=I-\alpha V^\top U
$$

puede perder muchos bits.

Mitigaciones:

- formar $K$ en fp64;
- usar FMA para $1-\alpha a_{ij}$;
- balancear $U,V$;
- usar QR/SVD de $K$;
- estimar $\sigma_{\min}(K)$;
- cambiar la parametrización si $\alpha$ se acerca a una singularidad;
- usar solver iterativo con residual alto;
- recurrir a una representación Cayley alternativa.

Si el paso $\tau$ es ajustable, limitarlo mediante:

$$
\alpha\|V^\top U\|<1-\delta
$$

como criterio suficiente conservador. No es una condición necesaria general, pero evita acercarse deliberadamente a una zona peligrosa.

## 11. Woodbury y simetría

Si la matriz actualizada es simétrica:

$$
A+UCU^\top,
$$

preservar esa estructura. Usar:

$$
K=C^{-1}+U^\top A^{-1}U.
$$

Si $A$ es SPD y $C$ es simétrica, $K$ puede ser simétrica; entonces Cholesky es más barato y estable que LU.

En Cayley, $W$ es skew-symmetric, por lo que la estructura no es SPD. No aplicar automáticamente una factorización simétrica positiva: verificar las propiedades algebraicas reales de la matriz reducida.

## 12. Método híbrido explícito/matrix-free

Recomendar tres rutas:

### Ruta rápida

```text
r pequeño
U,V bien condicionados
K explícita
LU/QR en fp32
refinamiento fp64
```


### Ruta estable

```text
r intermedio
QR rank-revealing
K en fp64
QR pivotado
residual escalado
```


### Ruta escalable

```text
r grande
K no materializada
FGMRES sobre apply_K
precondicionador Woodbury aproximado
refinamiento adaptativo
```

La selección debe depender de una estimación de coste:

$$
C_{\mathrm{explicit}}
\approx
r^3+n r q,
$$

$$
C_{\mathrm{matrixfree}}
\approx
k\,n r q+k\,r^2q.
$$

## 13. Actualizaciones repetidas

Si:

$$
A_{k+1}=A_k+U_kV_k^\top,
$$

no encadenar Woodbury indefinidamente:

$$
A_k^{-1}
\rightarrow
A_{k+1}^{-1}
\rightarrow
A_{k+2}^{-1}
$$

porque el rango efectivo y el error pueden crecer.

Cada $m$ actualizaciones:

1. recomputar una factorización base;
2. comprimir factores acumulados;
3. eliminar componentes dependientes;
4. recalcular el precondicionador;
5. medir el error de actualización.

Mantener una cadena de bajo rango solo mientras:

$$
\frac{\|E_{\mathrm{acc}}\|}{\|A\|}
\le
\tau_{\mathrm{rebuild}}.
$$

## 14. Error de Woodbury completo

Separar:

$$
\Delta_{\mathrm{total}}
=
\Delta_A
+
\Delta_K
+
\Delta_{\mathrm{prod}}
+
\Delta_{\mathrm{cancel}}
+
\Delta_{\mathrm{rank}}
+
\Delta_{\mathrm{iter}}.
$$

Donde:

- $\Delta_A$: error en solves con $A$;
- $\Delta_K$: error del sistema reducido;
- $\Delta_{\mathrm{prod}}$: error de productos $V^\top A^{-1}U$;
- $\Delta_{\mathrm{cancel}}$: cancelación en la corrección;
- $\Delta_{\mathrm{rank}}$: truncamiento;
- $\Delta_{\mathrm{iter}}$: convergencia incompleta.

Publicar al menos:

```text
woodbury_backward_error
small_system_condition
rank_truncation_error
residual_norm
refinement_steps
```


## 15. Diseño matrix-free completo

Definir operadores:

```cpp
struct LowRankOperator {
    void apply_U(MatrixView z, MatrixView out) const;
    void apply_Vt(MatrixView z, MatrixView out) const;

    void apply_K(MatrixView z, MatrixView out,
                 double alpha) const {
        apply_U(z, tmp_n);
        apply_Vt(tmp_n, tmp_r);
        out = z - alpha * tmp_r;
    }
};
```

El operador no debe conocer una matriz concatenada. Puede implementar:

- factores contiguos;
- vistas de bloques;
- kernels fusionados;
- compresión;
- acumulación mixta;
- buffers proporcionados por un `Workspace`.


## 16. Solución multi-RHS y bloqueada

Para $B\in\mathbb R^{n\times q}$:

$$
KZ=V^\top A^{-1}B.
$$

Resolver todas las columnas conjuntamente:

- factorizar $K$ una vez;
- usar TRSM/GEMM;
- evitar solves independientes;
- emplear block-GMRES si $K$ es matrix-free.

Si los RHS son casi dependientes, comprimir el bloque:

$$
R=QR_R
$$

y resolver solo el subespacio numéricamente independiente.

## 17. Pruebas científicas

### Prueba de identidad

Generar matrices pequeñas y comprobar:

$$
(A+UV^\top)X_{\mathrm{WB}}\approx B.
$$

Comparar contra:

- solve directo en fp64;
- QR;
- SVD;
- precisión multiprecisión.


### Prueba de condicionamiento

Controlar:

$$
\kappa(A),\qquad\kappa(K)
$$

de forma independiente. Esto identifica si falla la base o la reducción.

### Prueba de representación

Usar:

$$
U'=UD,\qquad V'=VD^{-T}
$$

para distintas matrices diagonales $D$. El resultado matemático es el mismo; una variación grande revela inestabilidad de escalado.

### Prueba de rango

Crear factores con rango numérico menor que el declarado y verificar:

- compresión;
- error de truncamiento;
- coste;
- residual.


### Prueba de actualizaciones repetidas

Aplicar cientos de actualizaciones de bajo rango y medir la deriva frente a recomputar desde cero.

## 18. Veredicto SOTA

Woodbury debe tratarse como una **familia de algoritmos adaptativos**, no como una fórmula fija de inversión. La arquitectura recomendada es:

$$
\boxed{
\text{factorización de }A
+
\text{factores balanceados}
+
\text{compresión rank-revealing}
+
\text{solve reducido}
+
\text{residual de alta precisión}
+
\text{reconstrucción periódica}
}
$$

Para Cayley-Stiefel:

$$
\boxed{
K=I-\alpha V^\top U
}
$$

debe resolverse con:

- LU/QR para rango pequeño;
- QR/SVD cuando hay mal condicionamiento;
- FGMRES matrix-free para rango grande;
- refinamiento mixto para recuperar precisión;
- validación simultánea algebraica y geométrica.

La redacción recomendada para v911 sería:

> La identidad de Woodbury se implementa como una reducción de solves, no como una fórmula de inversas. Los factores de bajo rango se balancean y comprimen mediante QR/SVD rank-revealing; el sistema reducido se resuelve con LU/QR/SVD según su condicionamiento, o mediante FGMRES matrix-free para rangos mayores. La factorización puede ejecutarse en baja precisión, pero los residuales y las decisiones de aceptación se calculan en precisión superior. Las actualizaciones repetidas se recomprimen y se reconstruye periódicamente la factorización base para evitar acumulación de error. Cada resultado reporta error hacia atrás, condición del sistema reducido, error de truncamiento y estado geométrico.

Woodbury elimina el coste estructural de la matriz grande, pero la solución científicamente correcta exige controlar el sistema reducido, el rango numérico, la representación de los factores y la acumulación de error.

<span style="display:none">[^13_10][^13_11][^13_12][^13_13][^13_14][^13_15][^13_16][^13_17]</span>

<div align="center">⁂</div>

[^13_1]: https://en.wikipedia.org/wiki/Woodbury_matrix_identity

[^13_2]: https://arxiv.org/html/2406.15120v2

[^13_3]: https://research.manchester.ac.uk/en/publications/a-sherman-morrison-woodbury-approach-to-solving-least-squares-pro/

[^13_4]: http://www.cs.umd.edu/~oleary/c660/660mxfacthand.pdf

[^13_5]: https://www.cerfacs.fr/algor/reports/2003/TR_PA_03_95.pdf

[^13_6]: https://hal.science/hal-02311256/document

[^13_7]: https://link.springer.com/content/pdf/10.1007/s00366-025-02187-z.pdf?error=cookies_not_supported\&code=da42e0c6-1703-4bd3-94ca-82feb934a32f

[^13_8]: https://www.osti.gov/servlets/purl/1825849

[^13_9]: https://hal.science/hal-04525918v2/document

[^13_10]: https://www.jmlr.org/papers/volume2/fine01a/fine01a.pdf

[^13_11]: https://d-nb.info/136751617X/34

[^13_12]: https://onlinelibrary.wiley.com/doi/10.1002/nla.2528

[^13_13]: https://www.cs.princeton.edu/courses/archive/fall11/cos323/notes/cos323_f11_lecture06_linsys2.pdf

[^13_14]: https://www.asc.ohio-state.edu/statistics/dmsl/thinSVDtracking.pdf

[^13_15]: https://web.dm.unipi.it/robol/assets/pdf/low-rank-updates.pdf

[^13_16]: https://github.com/nla-group/WoodburyLS

[^13_17]: https://pure.manchester.ac.uk/ws/files/179089053/main.pdf


---

## Woodbury SOTA: nivel más profundo

El error conceptual más frecuente es tratar Woodbury como una identidad para “calcular una inversa”. En cómputo científico debe verse como una **transformación de un problema grande en una secuencia de solves, productos y un sistema reducido**, con una política explícita de estabilidad.

Para:

$$
B=A+UCV^\top,
$$

la forma útil es:

$$
Bx=b
$$

y no:

$$
B^{-1}=\cdots
$$

La implementación SOTA debe decidir, según el condicionamiento y el rango numérico, entre:

- actualización explícita reducida;
- precondicionador de bajo rango;
- solver matrix-free;
- refinamiento mixto;
- compresión aleatorizada;
- reconstrucción periódica.

Investigaciones recientes estudian directamente la estabilidad de SMW con inversas aproximadas y muestran que los errores forward/backward dependen tanto del error de las solves base como del condicionamiento de la reducción.[^14_1]

## 1. Forma estable general

Para:

$$
B=A+UCV^\top,
$$

resolver:

$$
Bx=b
$$

mediante:

$$
y=A^{-1}b,
\qquad
Z=A^{-1}U.
$$

Entonces:

$$
\left(C^{-1}+V^\top Z\right)w=V^\top y,
$$

$$
x=y-Zw.
$$

Pero formar $C^{-1}$ puede ser inestable. Es preferible resolver el sistema bloqueado:

$$
\begin{bmatrix}
A & U\\
-V^\top & C^{-1}
\end{bmatrix}
\begin{bmatrix}
x\\
w
\end{bmatrix}
=
\begin{bmatrix}
b\\
0
\end{bmatrix},
$$

solo si $C$ es pequeño y está bien definido, o usar una factorización de $C$ sin invertirlo.

Si:

$$
C=LR^\top,
$$

reescribir:

$$
UCV^\top=(UL)(VR)^\top.
$$

Así, el problema pasa a una forma $A+\widetilde U\widetilde V^\top$ sin evaluar $C^{-1}$.

## 2. No encadenar Sherman–Morrison rango uno

Aplicar sucesivamente:

$$
A_{k+1}^{-1}
=
A_k^{-1}
-
\frac{A_k^{-1}u_kv_k^\top A_k^{-1}}
{1+v_k^\top A_k^{-1}u_k}
$$

parece simple, pero acumula redondeo, puede destruir simetría/definición positiva y puede pasar por matrices intermedias singulares aunque la actualización final sea válida.[^14_2]

La alternativa superior es agrupar las actualizaciones:

$$
\Delta A
=
\sum_{k=1}^r u_kv_k^\top
=
UV^\top
$$

y aplicar una sola reducción de rango $r$. Si se requieren muchas actualizaciones, recomprimir periódicamente los factores y reconstruir la factorización base.

## 3. Actualización multiplicativa

En precondicionamiento, a menudo no se tiene:

$$
B=A+UV^\top,
$$

sino una corrección multiplicativa:

$$
B=M(I+UV^\top)
$$

o:

$$
M^{-1}B=I+E.
$$

Si:

$$
E\approx UV^\top,
$$

se puede aplicar:

$$
(I+UV^\top)^{-1}
=
I-U(I+V^\top U)^{-1}V^\top.
$$

El precondicionador queda:

$$
P^{-1}
=
(I+UV^\top)^{-1}M^{-1}.
$$

Esta forma suele ser más útil que actualizar una inversa completa: Woodbury corrige los modos espectrales difíciles del precondicionador, mientras GMRES resuelve el residuo restante.

La literatura de correcciones low-rank muestra que el error del precondicionador actualizado depende tanto del error de aproximación low-rank como de cómo se propaga mediante los factores del operador.[^14_3][^14_4]

## 4. Woodbury + randomized range finder

Cuando $U,V$ no están disponibles directamente o el rango efectivo es desconocido, usar una aproximación aleatorizada.

Para una matriz u operador $E$:

1. generar $\Omega\in\mathbb R^{n\times(r+s)}$;
2. calcular:

$$
Y=E\\Omega;
$$
3. ortogonalizar:

$$
Y=QR;
$$
4. proyectar:

$$
B=Q^\\top E;
$$
5. factorizar $B$ mediante SVD o QR;
6. formar:

$$
E\\approx U_rV_r^\\top.
$$

El oversampling $s$ y las iteraciones de potencia mejoran la captura de espectros lentos:

$$
Y=(EE^\top)^qE\Omega.
$$

En un sistema matrix-free, solo se necesitan aplicaciones de $E$ y $E^\top$, no la matriz completa. Los métodos de sketching y randomized SVD se usan para construir precondicionadores de bajo rango con costes reducidos.[^14_5][^14_6][^14_7]

### Criterio de aceptación

No aceptar el rango aproximado solo por el tamaño de la proyección. Estimar:

$$
\|(I-QQ^\top)E\|_2
$$

mediante vectores de prueba independientes $\Omega_{\mathrm{test}}$:

$$
\widehat\epsilon
=
\frac{\|(I-QQ^\top)E\Omega_{\mathrm{test}}\|_F}
{\|\Omega_{\mathrm{test}}\|_F}.
$$

Si $\widehat\epsilon$ es demasiado grande:

- aumentar $r$;
- usar potencia $q>0$;
- cambiar a QR pivotado;
- abandonar la ruta low-rank.


## 5. Rango efectivo y espectro

El rango algebraico no es el rango numérico. Definir:

$$
r_{\mathrm{eff}}(\tau)
=
\#\{j:\sigma_j>\tau\sigma_1\}.
$$

Si $\sigma_j$ decae rápidamente, Woodbury es excelente. Si el espectro es plano, una reducción de rango pequeño puede ser peor que un solver iterativo directo.

Clasificación:


| Espectro | Estrategia |
| :-- | :-- |
| Decaimiento rápido | SVD/QR truncada + Woodbury |
| Cola moderada | randomized SVD + refinamiento |
| Espectro plano | GMRES/FGMRES sin compresión agresiva |
| Valores singulares pequeños | regularización o modo rechazado |
| Rango casi completo | abandonar Woodbury como ruta primaria |

## 6. Estabilidad de la base

No usar factores arbitrarios si sus columnas están casi dependientes. Formar bases ortonormales:

$$
U=Q_U R_U,
\qquad
V=Q_V R_V.
$$

Entonces:

$$
UV^\top
=
Q_U(R_UR_V^\top)Q_V^\top.
$$

El sistema reducido puede formularse con bases ortonormales y un núcleo pequeño. Esto reduce:

- crecimiento de errores;
- dependencia de escalado;
- pérdida de rango;
- estimaciones de condición engañosas.

Para máxima robustez:

- QR con pivotado si se necesita detección de rango;
- SVD si la decisión de truncamiento es crítica;
- Householder antes que Gram-Schmidt clásico;
- reortogonalización si se usa MGS en baja precisión.


## 7. Sistemas singulares o rectangulares

La identidad clásica supone inversibilidad. En problemas de optimización o least squares puede aparecer:

- $A$ rectangular;
- $A$ rank-deficient;
- actualización que cambia el rango;
- solución mínima norma.

En ese caso, la forma correcta puede requerir pseudoinversas generalizadas. Los desarrollos recientes de identidades SMW generalizadas extienden la teoría a inversas y pseudoinversas bajo condiciones de rango menos restrictivas.[^14_8]

Para una matriz rectangular:

$$
\min_x\|Ax-b\|_2,
$$

una actualización de bajo rango puede resolverse mediante:

- QR actualizado;
- SVD rank-revealing;
- LSQR/LSMR precondicionado;
- Woodbury aplicado al sistema normal solo con mucha cautela;
- reformulación aumentada estable.

Evitar formar:

$$
A^\top A
$$

si el condicionamiento es crítico, porque:

$$
\kappa(A^\top A)=\kappa(A)^2.
$$

## 8. Woodbury en mínimos cuadrados: QR antes que normales

Si:

$$
\widetilde A=A+UV^\top,
$$

y se busca:

$$
\min_x\|\widetilde A x-b\|_2,
$$

la ruta SOTA no es formar directamente $\widetilde A^\top\widetilde A$. Preferir:

1. factorizar $A=QR$;
2. representar la actualización en la base QR;
3. resolver un sistema reducido o actualizar QR;
4. usar LSQR/LSMR si la matriz es grande;
5. validar el residual original $\|\widetilde A x-b\|$.

Los trabajos recientes sobre SMW para mínimos cuadrados estudian justamente cómo actualizar soluciones y pseudoinversas ante modificaciones low-rank sin reiniciar el problema completo.[^14_9][^14_10]

## 9. Precondicionador con corrección espectral

Si $M$ aproxima $A$ y:

$$
E=AM^{-1}-I,
$$

aproximar:

$$
E\approx UV^\top.
$$

Entonces:

$$
AM^{-1}
\approx
I+UV^\top.
$$

Un precondicionador corregido puede eliminar modos lentos:

$$
P^{-1}
=
M^{-1}
\left[I-U(I+V^\top U)^{-1}V^\top\right].
$$

Para GMRES, esto puede concentrar el espectro cerca de uno. Pero la baja-rank correction no siempre reduce el rango del error restante; el análisis depende de la interacción entre el error original y la actualización.[^14_4]

Medir antes y después:

- radio espectral estimado;
- valores de Ritz;
- número de iteraciones;
- residual por iteración;
- coste de aplicar el precondicionador.


## 10. GMRES para $I+K+E$

Cuando:

$$
B=I+K+E,
$$

con $K$ low-rank y $E$ pequeño en norma, GMRES puede converger rápidamente si la parte dominante queda capturada por la corrección. La teoría específica de sistemas “identidad + bajo rango + perturbación pequeña” permite justificar el uso de Woodbury como precondicionador.[^14_11]

Ruta:

$$
M^{-1}=(I+K)^{-1}
$$

por Woodbury, y luego resolver:

$$
M^{-1}Bx=M^{-1}b
$$

con GMRES. El error que queda es:

$$
M^{-1}E,
$$

que debe medirse, no suponerse pequeño.

## 11. Error hacia atrás de la aplicación Woodbury

Para un resultado $\hat x$, calcular:

$$
r=b-B\hat x.
$$

El backward error relativo:

$$
\eta_B
=
\frac{\|r\|}
{\|B\|\|\hat x\|+\|b\|}.
$$

Si $B$ no se materializa, estimar $\|B\|$ mediante:

- norma de $A$ más cota:

$$
|B|\\le|A|+|U||C||V|;
$$
- estimación de potencia;
- muestreo aleatorio;
- cota conservadora.

El resultado no debe marcarse como correcto solo porque $K$ se resolvió con éxito. Hay que validar el operador original.

## 12. Error de aproximación low-rank

Si:

$$
B=A+\widehat U\widehat V^\top
$$

aproxima:

$$
B^\star=A+UV^\top,
$$

entonces:

$$
\|B^\star-B\|
\le
\|UV^\top-\widehat U\widehat V^\top\|.
$$

Para la solución:

$$
x^\star-\hat x
\approx
B^{-1}(B-\widehat B)\hat x.
$$

Por tanto:

$$
\frac{\|x^\star-\hat x\|}{\|x^\star\|}
\lesssim
\kappa(B)
\frac{\|B-\widehat B\|}{\|B\|}.
$$

Una compresión pequeña puede producir un error grande si $B$ está mal condicionado. La tolerancia de rango debe depender de $\kappa(B)$, no solo de la energía descartada.

## 13. Refinamiento de bajo rango

Si el sistema reducido es lo único mal resuelto, refinar solo el sistema pequeño puede ser suficiente:

$$
KZ=R.
$$

Proceso:

```text
1. Resolver KZ=R en fp16/fp32.
2. Calcular R − KZ en fp64.
3. Resolver KΔ=error.
4. Actualizar Z ← Z+Δ.
5. Repetir.
```

Esto es barato porque $K$ es pequeño. Si el error dominante está en $A^{-1}U$ o $A^{-1}B$, hay que refinar también las solves base.

Separar diagnósticos:

```text
error_base_solve
error_reduced_solve
error_final_operator
```


## 14. Precondicionador de precisión variable

Usar:

$$
M_k^{-1}
$$

con precisión adaptativa:

```text
iteración normal: precondicionador fp16/fp32
residual lento: precondicionador fp32
estancamiento: QR/fp64
recuperación: SVD o rebuild
```

FGMRES es adecuado porque permite que $M_k$ cambie. El análisis moderno de GMRES enfatiza que la precisión de las operaciones y los errores locales deben incorporarse a la evaluación de backward error.[^14_12][^14_13]

## 15. Rebuild y compresión periódica

Para actualizaciones sucesivas:

$$
A_{k+1}=A_k+U_kV_k^\top,
$$

mantener una lista indefinida de factores es mala práctica. Cada cierto número de pasos:

1. concatenar conceptualmente los factores, no necesariamente en un gran buffer;
2. comprimir mediante QR/SVD;
3. balancear;
4. estimar error;
5. reconstruir la factorización base si el rango efectivo crece.

Trigger de rebuild:

$$
r_{\mathrm{acc}}\ge r_{\max},
$$

o:

$$
\eta_{\mathrm{update}}\ge\tau,
$$

o:

$$
\frac{T_{\mathrm{Woodbury}}}{T_{\mathrm{refactor}}}
\ge\gamma.
$$

El rebuild debe ser una decisión coste/precisión, no un intervalo fijo ciego.

## 16. Estructura de datos SOTA

```cpp
struct LowRankUpdate {
    MatrixView U;
    MatrixView V;
    MatrixView C;       // opcional
    double approximation_error;
    int numerical_rank;
};

struct WoodburyDiagnostics {
    double cond_reduced;
    double backward_error;
    double rank_error;
    double base_solve_error;
    double reduced_solve_error;

    int refinement_steps;
    int rebuild_count;
    bool compressed;
    bool regularized;
};
```

El objeto debe almacenar vistas y metadatos, no copiar matrices automáticamente. La memoria debe vivir en una arena/workspace con ownership explícito.

## 17. Política de decisión final

```text
1. ¿A es resoluble con factor existente?
   No → refactorizar o cambiar precondicionador.

2. ¿El rango numérico es pequeño?
   Sí → Woodbury explícito.
   No → matrix-free / randomized low-rank.

3. ¿K está bien condicionado?
   Sí → LU/Cholesky/QR.
   No → QR pivotado, SVD o FGMRES.

4. ¿El residuo converge?
   Sí → aceptar si también pasa validación original.
   No → aumentar precisión o rebuild.

5. ¿La aproximación low-rank supera la tolerancia?
   No → aumentar rango o rechazar.

6. ¿La cadena de actualizaciones creció demasiado?
   Sí → comprimir/reconstruir.
```


## Veredicto

La solución Woodbury SOTA no es “usar la identidad de memoria eficiente”, sino controlar seis capas:

$$
\boxed{
\text{representación}
+
\text{rango numérico}
+
\text{condicionamiento}
+
\text{precisión}
+
\text{error de aproximación}
+
\text{reconstrucción}
}
$$

La arquitectura más robusta para Cayley-Stiefel y sistemas similares es:

$$
\boxed{
\text{factores balanceados}
\rightarrow
\text{QR/SVD rank-revealing}
\rightarrow
\text{Woodbury reducido}
\rightarrow
\text{precondicionador FGMRES}
\rightarrow
\text{refinamiento mixto}
\rightarrow
\text{residual del operador original}
}
$$

En particular:

- no invertir $A$, $C$ ni $K$;
- no encadenar actualizaciones rango uno indefinidamente;
- no confiar solo en el residual reducido;
- no aceptar compresión sin una cota de error;
- no usar `normal equations` en problemas mal condicionados;
- no declarar validez sin comprobar el operador original;
- reconstruir periódicamente la base y recomprimir los factores.

Esta es la diferencia entre una implementación Woodbury rápida y una implementación Woodbury científicamente confiable.

<span style="display:none">[^14_14][^14_15][^14_16][^14_17][^14_18][^14_19]</span>

<div align="center">⁂</div>

[^14_1]: https://arxiv.science/abs/2504.04554

[^14_2]: https://www.ijcaonline.org/archives/volume187/number54/stotsky-2025-ijca-925940.pdf

[^14_3]: https://perso.ens-lyon.fr/elisa.riccietti/doc/slides_M2/LRA.pdf

[^14_4]: https://www.edit.fis.uni-hamburg.de/ws/files/45096259/s11075-023-01548-3.pdf

[^14_5]: https://arxiv.org/pdf/2502.07993.pdf

[^14_6]: https://cmds.compute.dtu.dk/slides/yuji.pdf

[^14_7]: https://www.stat.berkeley.edu/~mmahoney/talks/randnlapack_nips21.pdf

[^14_8]: https://epubs.siam.org/doi/10.1137/25M1723724

[^14_9]: https://arxiv.org/html/2406.15120v2

[^14_10]: https://research.manchester.ac.uk/en/publications/a-sherman-morrison-woodbury-approach-to-solving-least-squares-pro/

[^14_11]: https://ar5iv.labs.arxiv.org/html/2210.12053

[^14_12]: https://academic.oup.com/imajna/article/46/4/1939/8658483?searchresult=1

[^14_13]: https://hal.science/hal-04525918v2/document

[^14_14]: https://ar5iv.labs.arxiv.org/html/2401.15758

[^14_15]: https://perso.ens-lyon.fr/elisa.riccietti/doc/projects/project_theo.pdf

[^14_16]: https://www.stat.berkeley.edu/~mmahoney/talks/RandNLA_Tutorial_ALA2015.pdf

[^14_17]: https://www-users.cse.umn.edu/~saad/PDF/ys-2014-4.pdf

[^14_18]: https://www.stat.berkeley.edu/~mmahoney/f13-stat260-cs294/Lectures/lecture19.pdf

[^14_19]: https://www.stat.berkeley.edu/~mmahoney/talks/RandNLA1.pdf

