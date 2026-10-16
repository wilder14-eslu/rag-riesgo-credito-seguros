# Demo pública en Render

Enlace: [https://riskrag-demo.onrender.com](https://riskrag-demo.onrender.com)

La demo corre gratis en Render con los **backends locales**: embeddings por hashing, índice en memoria, LLM extractivo y guardrails por reglas, sobre el corpus de ejemplo. No usa Azure ni tiene costo. Expone:

- `/demo`: interfaz Gradio con tres pestañas (preguntar, clasificar deudor, calcular provisión) y ejemplos listos, incluido un ataque de inyección y una pregunta fuera del corpus para ver la abstención. La raíz `/` redirige aquí.
- `/docs`: la API REST con Swagger.

La interfaz llama a las mismas piezas que la API (`LocalAgent` y las herramientas deterministas) y tiene su propio límite por IP. La lógica está en `src/riskrag/demo/handlers.py`, sin depender de Gradio, y se prueba en `tests/test_demo.py`.

## Configuración (una sola vez)

1. En [dashboard.render.com](https://dashboard.render.com), elegir **New > Blueprint**.
2. Conectar el repositorio `rag-riesgo-credito-seguros` de GitHub. Render lee `render.yaml` y propone el servicio `riskrag-demo` con el plan **Free**.
3. Confirmar con **Deploy Blueprint**. La primera construcción tarda unos minutos.
4. Si Render asigna otra URL (por ejemplo con un sufijo, porque el nombre ya existía), actualizar el enlace en el README y en este documento.

## Cómo se publica

`render.yaml` define un servicio web Docker que construye `Dockerfile.demo`. Con `autoDeployTrigger: checksPass`, Render solo despliega un commit de `main` cuando los checks de CI pasan. Al arrancar, el contenedor indexa el corpus de ejemplo (unos segundos) y luego sirve la app en el puerto que define Render.

## Probarla en local

```bash
pip install -e ".[demo]"
python -m riskrag.cli ingest data/sample
RISKRAG_HOME_PATH=/demo uvicorn riskrag.demo.app:app --port 7860
# abrir http://127.0.0.1:7860
```

## Límites del plan gratuito

- El servicio se duerme tras 15 minutos sin visitas; la siguiente visita lo despierta en cerca de un minuto.
- 750 horas gratis al mes por workspace, compartidas con otros servicios gratuitos de la misma cuenta.
- 0.1 CPU y 512 MB de memoria: suficiente para el corpus de ejemplo.
- El LLM extractivo no redacta: copia las oraciones más relevantes de la fuente y las cita. La versión generativa usa Azure OpenAI ([09_despliegue_azure.md](09_despliegue_azure.md)).
- El corpus es de ejemplo; las cifras sirven para mostrar el funcionamiento, no como referencia regulatoria.
