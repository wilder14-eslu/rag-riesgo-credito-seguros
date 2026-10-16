# Demo pública en Hugging Face Spaces

La demo corre gratis en un Space de Hugging Face con los **backends locales**: embeddings por hashing, índice en memoria, LLM extractivo y guardrails por reglas, sobre el corpus de ejemplo. No usa Azure ni tiene costo. Expone:

- `/demo`: interfaz Gradio con tres pestañas (preguntar, clasificar deudor, calcular provisión) y ejemplos listos, incluido un ataque de inyección y una pregunta fuera del corpus para ver la abstención.
- `/docs`: la API REST con Swagger.

La interfaz llama a las mismas piezas que la API (`LocalAgent` y las herramientas deterministas) y tiene su propio límite por IP. La lógica está en `src/riskrag/demo/handlers.py`, sin depender de Gradio, y se prueba en `tests/test_demo.py`.

## Configuración (una sola vez)

1. En Hugging Face, crear un Space nuevo: **SDK Docker**, plantilla en blanco, hardware **CPU basic (gratis)**, visibilidad pública. Nombre sugerido: `riskrag`.
2. Crear un token de acceso con permiso de escritura en *Settings > Access Tokens*.
3. En GitHub, en *Settings > Secrets and variables > Actions* del repositorio:
   - Secreto `HF_TOKEN` con el token.
   - Variable `HF_SPACE` con `<usuario-de-hugging-face>/riskrag`.
4. Ejecutar el workflow **Demo en Hugging Face** desde la pestaña *Actions* (o hacer push a `main`).

## Cómo se publica

El workflow `.github/workflows/deploy-space.yml` corre cuando CI pasa en `main`. Arma una carpeta solo con lo que necesita la demo (`src/`, `configs/`, `data/sample/`, `pyproject.toml`), usa `space/Dockerfile` como `Dockerfile` y `space/README.md` como tarjeta del Space, y la publica en el Space. Hugging Face construye la imagen y arranca el contenedor, que primero indexa el corpus de ejemplo y luego sirve la app en el puerto 7860.

## Probarla en local

```bash
pip install -e ".[demo]"
python -m riskrag.cli ingest data/sample
RISKRAG_HOME_PATH=/demo uvicorn riskrag.demo.app:app --port 7860
# abrir http://127.0.0.1:7860
```

## Límites

- El Space gratuito se suspende tras un periodo sin visitas y despierta al entrar (la primera carga tarda un poco).
- El LLM extractivo no redacta: copia las oraciones más relevantes de la fuente y las cita. La versión generativa usa Azure OpenAI ([09_despliegue_azure.md](09_despliegue_azure.md)).
- El corpus es de ejemplo; las cifras sirven para mostrar el funcionamiento, no como referencia regulatoria.
