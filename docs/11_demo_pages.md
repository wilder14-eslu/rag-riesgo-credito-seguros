# Demo en GitHub Pages

Enlace: [https://wilder14-eslu.github.io/rag-riesgo-credito-seguros/](https://wilder14-eslu.github.io/rag-riesgo-credito-seguros/)

La demo corre completa en el navegador: no hay servidor, no hay arranque en frío y las consultas no salen de la pestaña. Reemplaza a la versión de Render ([10_demo_render.md](10_demo_render.md)), que se dormía a los 15 minutos y tardaba cerca de un minuto en despertar.

## Qué corre en el navegador

| Pieza | Cómo |
|---|---|
| Recuperación | Port a JavaScript del modo local: embeddings por hashing (BLAKE2b), BM25 con stemmer Snowball en español, fusión RRF y reranker léxico (`site/js/riskrag.js`) |
| Seguridad | Detección de inyección de prompt, enmascarado de PII, verificación de fidelidad y abstención, con las mismas reglas que `src/riskrag/security` |
| Cálculos | Clasificación por atraso y provisión SBS con aritmética decimal exacta (sin `float`) |
| Score de default | XGBoost exportado a ONNX (271 KB) y ejecutado con `onnxruntime-web` (`site/js/credit.js`) |

El índice (`site/data/kb.json`, unos 240 KB) se genera en cada despliegue con `scripts/build_pages.py`: re-indexa el corpus, respeta la cuarentena de documentos envenenados y exporta fragmentos, vectores, glosario y tablas.

## Cómo se publica

`.github/workflows/pages.yml` corre en cada push a `main` y solo publica si pasan, en orden:

1. La evaluación del RAG (`eval.run_eval`) con sus umbrales.
2. La paridad con Python: `scripts/make_golden.py` ejecuta el agente real sobre más de 700 casos (preguntas, ataques, clasificaciones, provisiones) y `tests/js/parity.test.mjs` exige que el motor JavaScript responda carácter por carácter igual.
3. La fidelidad del modelo ONNX: `tests/js/credit.test.mjs` compara la probabilidad con la de XGBoost y verifica el hash del archivo.

Configuración, una sola vez: en GitHub, **Settings > Pages > Source: GitHub Actions**.

## Modelo ONNX

Se exporta desde `credit-risk-ml-platform` con `scripts/export_onnx.py`, que además comprueba la equivalencia contra el modelo original en 4,000 filas (diferencia máxima 4.8×10⁻⁷) y escribe `credit_default.meta.json` con rangos, medianas de entrenamiento y umbral.

```bash
# en credit-risk-ml-platform
pip install onnx onnxmltools onnxruntime
python -m src.ml.train                      # reentrena el champion con el esquema actual de 10 variables
python -m scripts.export_onnx --model data/processed/model.joblib --out site/models
# copiar credit_default.onnx y credit_default.meta.json a site/models/ de este repo
```

Notas:

- El umbral de decisión es 0.155, el de mínimo costo (FN:FP = 5:1) de la Model Card, no el 0.5 por defecto de la API.
- Los factores que muestra la página se calculan por oclusión (cuánto baja la probabilidad si la variable toma la mediana de entrenamiento). No son valores SHAP.
- `onnxruntime-web` se carga desde jsDelivr con versión fija y verificación de integridad (SRI). El archivo WebAssembly pesa unos 11 MB y solo se descarga al abrir la pestaña del score. Para no depender de la CDN, se puede copiar `node_modules/onnxruntime-web/dist/` dentro de `site/` y cambiar `ORT_BASE` en `site/js/app.js`.

## Probarla en local

```bash
pip install -e ".[dev]"
python -m riskrag.cli ingest data/sample
python scripts/build_pages.py --sin-ingesta
python -m http.server -d site 8000            # abrir http://127.0.0.1:8000

npm ci
python scripts/make_golden.py
npm test
```

## Límites

- El corpus es de ejemplo y las cifras sirven para mostrar el funcionamiento, no como referencia regulatoria.
- El LLM es extractivo: copia y cita las oraciones más relevantes, no redacta. La versión generativa usa Azure OpenAI ([09_despliegue_azure.md](09_despliegue_azure.md)).
- La limitación por IP de la demo en Render no aplica aquí: el cómputo ocurre en el equipo de quien visita la página.
