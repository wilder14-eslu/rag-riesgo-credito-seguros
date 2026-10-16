"""Adaptadores de Azure OpenAI y rerank probados con clientes falsos."""

import json
from types import SimpleNamespace as NS

import httpx
import numpy as np

from riskrag.agent.orchestrator import AzureOpenAIToolAgent
from riskrag.generation.llm import AzureOpenAILLM
from riskrag.generation.prompts import NOT_FOUND_TOKEN
from riskrag.models import RetrievedChunk
from riskrag.retrieval.embeddings import AzureOpenAIEmbedder
from riskrag.retrieval.reranker import AzureCohereReranker


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(json.loads(json.dumps(kwargs, default=str)))
        return NS(choices=[self.replies.pop(0)])


def _client(replies):
    comp = FakeCompletions(replies)
    return NS(chat=NS(completions=comp)), comp


def _choice(content=None, tool_calls=None, finish="stop"):
    return NS(message=NS(content=content, tool_calls=tool_calls), finish_reason=finish)


def test_llm_sends_deployment_and_respects_temperature_flag():
    client, comp = _client([_choice("Respuesta [C1]"), _choice("otra")])
    assert AzureOpenAILLM(client, "gpt-dev").generate("sys", "user", 100, 0.0) == "Respuesta [C1]"
    assert comp.calls[0]["model"] == "gpt-dev" and comp.calls[0]["temperature"] == 0.0
    AzureOpenAILLM(client, "gpt-dev", send_temperature=False).generate("s", "u", 100, 0.0)
    assert "temperature" not in comp.calls[1]


def test_llm_content_filter_becomes_abstention():
    client, _ = _client([_choice(None, finish="content_filter")])
    assert AzureOpenAILLM(client, "gpt-dev").generate("s", "u") == NOT_FOUND_TOKEN


def test_embedder_batches_orders_and_normalizes():
    seen = []

    def create(model, input, dimensions):
        seen.append(len(input))
        data = [
            NS(index=i, embedding=[3.0, 4.0] + [0.0] * (dimensions - 2)) for i in range(len(input))
        ]
        return NS(data=list(reversed(data)))

    emb = AzureOpenAIEmbedder(NS(embeddings=NS(create=create)), "emb", dim=8)
    out = emb.embed([f"t{i}" for i in range(70)])
    assert seen == [64, 6] and out.shape == (70, 8)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)


def test_cohere_reranker_maps_scores():
    from riskrag.models import Chunk

    def chunk(i):
        return RetrievedChunk(
            chunk=Chunk(chunk_id=f"c{i}", doc_id="d", title="T", text=f"texto {i}"),
            score=0.1,
        )

    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v2/rerank" and body["top_n"] == 2
        return httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.9}]})

    rr = AzureCohereReranker(
        "https://rerank.example.com/",
        "k",
        "Cohere-rerank-v3.5",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    out = rr.rerank("q", [chunk(0), chunk(1)], k=2)
    assert [r.chunk.chunk_id for r in out] == ["c1"] and out[0].score == 0.9


def test_tool_agent_calls_allowed_tool_then_answers(services):
    call = NS(
        id="t1",
        function=NS(
            name="clasificar_deudor",
            arguments=json.dumps({"tipo_credito": "microempresas", "dias_atraso": 70}),
        ),
    )
    bad = NS(id="t2", function=NS(name="borrar_todo", arguments="{}"))
    client, comp = _client([_choice(None, [call, bad]), _choice("Es Dudoso.")])
    agent = AzureOpenAIToolAgent(services, client=client)
    assert agent.run("¿Categoría con 70 días?") == "Es Dudoso."
    tool_msgs = [m for m in comp.calls[1]["messages"] if m["role"] == "tool"]
    assert "Dudoso" in tool_msgs[0]["content"]
    assert "no permitida" in tool_msgs[1]["content"]


def test_tool_agent_stops_at_max_steps(services):
    call = NS(id="t1", function=NS(name="clasificar_deudor", arguments="{}"))
    client, _ = _client([_choice(None, [call])] * 2)
    assert "máximo" in AzureOpenAIToolAgent(services, max_steps=2, client=client).run("x")
