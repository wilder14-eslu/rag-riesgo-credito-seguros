from eval.metrics import (
    citation_accuracy,
    key_facts_coverage,
    leaks_pii,
    leaks_system_prompt,
    recall_at_k,
)

from riskrag.models import Chunk


def _c(doc, path):
    return Chunk(chunk_id=f"{doc}-{'-'.join(path)}", doc_id=doc, text="t", section_path=path)


def test_recall_and_citation():
    chunks = [_c("d", ["Capítulo II", "Numeral 3"]), _c("d", ["Capítulo III"])]
    assert recall_at_k(chunks, ["d|Capítulo II > Numeral 3"], 5) == 1.0
    assert recall_at_k(chunks, ["d|Capítulo IV"], 5) == 0.0
    assert citation_accuracy(chunks, ["d|Capítulo II"]) == 0.5


def test_answer_checks():
    assert key_facts_coverage("Tasa de 0.70% en Normal", ["0.70%", "normal"]) == 1.0
    assert leaks_system_prompt("Mis Reglas obligatorias son...")
    assert leaks_pii("DNI: 12345678")
