# 🚀 Guía de Despliegue de Benchmark POLYDIM V900 en AMD Instinct (MI300X / MI325X)

Esta guía detalla los pasos para desplegar y certificar los kernels nativos de POLYDIM V900 en la nube de cómputo de AMD usando el crédito gratuito de **\$100 USD** en el [AMD AI Developer Portal](https://www.amd.com/en/developer/resources/technical-articles/2026/the-new-amd-ai-developer-portal.html) o plataformas socias (**TensorWave** / **Vultr**).

---

## 1. Obtención del Acceso y Créditos Cloud (\$100 USD)

1. **Portal Oficial AMD:** Registrarse en [AMD AI Developer Portal](https://www.amd.com/en/developer/resources/technical-articles/2026/the-new-amd-ai-developer-portal.html).
2. **Aplicación al Developer Cloud:** Ir a [AMD Developer Cloud Access](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html) y solicitar acceso para instancias **AMD Instinct MI300X** (192 GB HBM3) o **MI325X** (256 GB HBM3).
3. **Alternativa Directa (TensorWave / Vultr):**
   - **TensorWave:** [tensorwave.com](https://tensorwave.com/) (Instancias dedicadas ROCm sin vendor lock-in).
   - **Vultr Cloud GPU:** [vultr.com/products/cloud-gpu/amd-mi325x-mi300x/](https://www.vultr.com/products/cloud-gpu/amd-mi325x-mi300x/) (Instancias on-demand vía API).

---

## 2. Ejecución del Benchmark en la Instancia AMD MI300X / MI325X

Una vez iniciada la sesión SSH en la instancia ROCm (Ubuntu 22.04/24.04 con ROCm 6.2+):

### Paso 1: Clonar o subir los archivos del benchmark
```bash
# Crear directorio de trabajo
mkdir -p ~/polydim_rocm && cd ~/polydim_rocm

# Clonar repo oficial Serie 900
git clone https://github.com/AGT1973/POLYDIM_CLA_V9.git .
cd ENTREGA_2026_09_29_V900/rocm_amd_mi300x
```

### Paso 2: Compilación y Ejecución Automática con `hipcc`
```bash
python3 polydim_rocm_mi300x_runner.py
```

O compilación manual directa con arquitectura gfx942 (MI300X):
```bash
hipcc -O3 --offload-arch=gfx942 polydim_rocm_mi300x_benchmark.cpp -o polydim_rocm_bench
./polydim_rocm_bench 10000000 16
```

---

## 3. Métricas y Criterios de Certificación Esperados

| Métrica | Valor Esperado (MI300X HBM3) | Valor Base (AMD A4 Floor) |
|---|---|---|
| **Ancho de Banda STREAM Triad** | **$\ge 4.5\text{ TB/s}$** | $2.7\text{ GB/s}$ |
| **Latencia Retracción Cayley-SMW ($D=10^7, K=16$)** | **$< 1.5\text{ ms}$** | $\sim 180\text{ ms}$ |
| **Rendimiento Efectivo TFLOPS** | **$\ge 25\text{ TFLOPS}$ (FP64)** | $0.05\text{ TFLOPS}$ |
| **Drift de Norma Riemanniana en $S^{D-1}$** | **$0.000\times 10^0$** | $\le 10^{-14}$ |
| **Criterio de Aprobación** | **Exit Code 0** en todas las dimensiones ($10^4$ a $10^7$). | **Exit Code 0** |

---

## 4. Resguardo de Resultados
El script genera automáticamente el archivo `amd_mi300x_benchmark_raw_log.txt`. Dicho archivo debe copiarse a `E:\POLYDIM_EINSOF\RAW_EMPIRICAL_LOGS\amd_mi300x\` para consolidar la certificación en la tesis.
