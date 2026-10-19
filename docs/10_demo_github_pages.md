# Demo pública en GitHub Pages (Cero Cold-Start)

Enlace: [https://wilder14-eslu.github.io/rag-riesgo-credito-seguros/](https://wilder14-eslu.github.io/rag-riesgo-credito-seguros/)

Esta demo corre **directamente en el navegador del usuario** gracias a **Gradio-Lite** y **Pyodide** (WebAssembly), alojada en la red de distribución de contenidos (CDN) de **GitHub Pages**.

## Ventajas clave frente a Render

| Característica | Render (Plan Free) | GitHub Pages (Gradio-Lite) |
| :--- | :--- | :--- |
| **Tiempo de arranque (Cold-Start)** | 50 a 90 segundos al despertar | **0 segundos** (carga instantánea desde CDN) |
| **Tiempo de indexación al iniciar** | 10 a 20 s (`ingest` en cada inicio) | **0 s** (índice pre-cargado de ~94 KB) |
| **Límites de tiempo activo** | Se suspende tras 15 min | **Siempre activo 24/7** |
| **Consumo de servidor / Costo** | 0.1 CPU / 512 MB | **0 servidores / 100% gratuito** |
| **Privacidad** | Las consultas viajan a un servidor | Las consultas se ejecutan en el navegador del usuario |

---

## Cómo funciona la arquitectura

```
  +-------------------------------------------------------+
  |                   GitHub Actions                      |
  |  1. Indexa corpus: python -m riskrag.cli ingest       |
  |  2. Empaqueta bundle (código + configs + index.json)  |
  |  3. Despliega a GitHub Pages (deploy-pages.yml)       |
  +---------------------------+---------------------------+
                              | Publica
                              v
  +-------------------------------------------------------+
  |              GitHub Pages (CDN Global)                |
  |       HTML + Gradio-Lite + riskrag_bundle.zip         |
  +---------------------------+---------------------------+
                              | Descarga única (~94 KB)
                              v
  +-------------------------------------------------------+
  |                 Navegador del Usuario                 |
  |  - Pyodide (Python en WebAssembly)                    |
  |  - HashingEmbedder + ExtractiveLLM                    |
  |  - Búsqueda híbrida (BM25 + Cosine) sobre index.json  |
  |  - Cálculos regulatorios deterministas (SBS)          |
  +-------------------------------------------------------+
```

1. **GitHub Actions (`.github/workflows/deploy-pages.yml`):**
   * En cada `push` a la rama `main`, ejecuta `scripts/build_pages.py`.
   * Empaqueta el código fuente de `src/riskrag`, las configuraciones en `configs/` y el índice pre-vectorizado en `data/processed/index.json` en un archivo ligero `riskrag_bundle.zip` (**~94 KB**).
   * Genera el `index.html` optimizado con Gradio-Lite.
   * Publica el sitio en GitHub Pages mediante `actions/deploy-pages@v4`.

2. **Ejecución en el cliente:**
   * Al abrir la URL, el navegador descarga el bundle pre-cargado.
   * La interfaz Gradio se monta en el navegador con las tres pestañas:
     - **Preguntar:** búsqueda RAG híbrida contra el índice pre-cargado con citas exactas.
     - **Clasificar deudor:** clasificación de créditos por días de atraso según Res. SBS 11356-2008.
     - **Calcular provisión:** cálculo determinista de provisiones según categoría y garantías.

---

## Cómo activar GitHub Pages en el repositorio

Si aún no está habilitado GitHub Pages en el repositorio de GitHub:

1. Ve a **Settings** en el repositorio `rag-riesgo-credito-seguros`.
2. En la barra lateral izquierda, haz clic en **Pages**.
3. En la sección **Build and deployment > Source**, selecciona:
   * **GitHub Actions**.
4. Haz push a `main` o ejecuta manualmente el workflow **"Desplegar Demo en GitHub Pages"** desde la pestaña **Actions**.
5. ¡Listo! La demo estará accesible en segundos en `https://<tu-usuario>.github.io/rag-riesgo-credito-seguros/`.

---

## Probar la versión estática localmente

Puedes probar la versión estática en tu máquina antes de subirla:

```bash
# 1. Generar el bundle
python scripts/build_pages.py

# 2. Iniciar un servidor HTTP local
python -m http.server 8000 --directory site

# 3. Abrir en el navegador: http://localhost:8000
```
