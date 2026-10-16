"""Aplicación de la demo: la API de FastAPI con una interfaz Gradio montada en /demo.

Uso local:  uvicorn riskrag.demo.app:app --port 7860
En Hugging Face Spaces la arranca space/Dockerfile.
"""

from __future__ import annotations

import gradio as gr

from riskrag.api.main import app as api_app
from riskrag.config import get_settings
from riskrag.demo.handlers import CATEGORIES, CREDIT_TYPES, EXAMPLES, GUARANTEES, DemoHandlers
from riskrag.factory import get_services

INTRO = """
# RiskRAG · asistente de riesgo crediticio y seguros

Responde preguntas de normativa **citando el capítulo y numeral**, se **abstiene** cuando no tiene
sustento, **calcula** clasificación y provisiones con herramientas deterministas (nunca con el LLM)
y **bloquea** intentos de inyección de prompt.

> **Demo en modo local, sin costo:** embeddings por hashing, LLM extractivo (copia oraciones de la
> fuente, no redacta) y un corpus **de ejemplo** basado en la Res. SBS 11356-2008, IFRS 9 e IFRS 17.
> La versión con Azure OpenAI y Content Safety está en el repositorio. No es asesoría regulatoria.

[Código en GitHub](https://github.com/wilder14-eslu/rag-riesgo-credito-seguros) ·
[API (Swagger)](/docs)
"""


def _client_id(request: gr.Request | None) -> str:
    if request is None:
        return "anon"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anon"


def build_demo(handlers: DemoHandlers) -> gr.Blocks:
    with gr.Blocks(title="RiskRAG") as demo:
        gr.Markdown(INTRO)
        with gr.Tab("Preguntar"):
            question = gr.Textbox(label="Pregunta", lines=2, max_length=2000)
            ask_btn = gr.Button("Responder", variant="primary")
            answer = gr.Markdown()
            gr.Examples(EXAMPLES, inputs=question, label="Ejemplos")

            def _ask(q: str, request: gr.Request) -> str:
                return handlers.ask(q, _client_id(request))

            ask_btn.click(_ask, question, answer)
            question.submit(_ask, question, answer)

        with gr.Tab("Clasificar deudor"):
            c_type = gr.Dropdown(list(CREDIT_TYPES), label="Tipo de crédito", value="Microempresas")
            c_days = gr.Number(label="Días de atraso", value=70, precision=0, minimum=0)
            c_btn = gr.Button("Clasificar", variant="primary")
            c_out = gr.Markdown()

            def _classify(t: str, d: float, request: gr.Request) -> str:
                return handlers.classify(t, d, _client_id(request))

            c_btn.click(_classify, [c_type, c_days], c_out)

        with gr.Tab("Calcular provisión"):
            p_type = gr.Dropdown(list(CREDIT_TYPES), label="Tipo de crédito", value="Microempresas")
            p_cat = gr.Dropdown(CATEGORIES, label="Categoría", value="Dudoso")
            p_amount = gr.Number(label="Monto (S/)", value=10000, minimum=0)
            p_cov = gr.Number(label="Monto cubierto por garantía (S/)", value=0, minimum=0)
            p_guar = gr.Dropdown(list(GUARANTEES), label="Garantía", value="Sin garantía preferida")
            p_btn = gr.Button("Calcular", variant="primary")
            p_out = gr.Markdown()

            def _provision(t: str, c: str, a: float, cv: float, g: str, request: gr.Request) -> str:
                return handlers.provision(t, c, a, cv, g, _client_id(request))

            p_btn.click(_provision, [p_type, p_cat, p_amount, p_cov, p_guar], p_out)
    return demo


settings = get_settings()
handlers = DemoHandlers(get_services(), per_minute=settings.rate_limit_per_minute)
app = gr.mount_gradio_app(api_app, build_demo(handlers), path="/demo", footer_links=["api"])
