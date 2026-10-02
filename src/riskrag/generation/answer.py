"""Pipeline RAG completo con seguridad y verificación.

Flujo de ``RAGPipeline.ask``:

1. Validar y sanear la consulta (tamaño, caracteres invisibles).
2. Guardrail de entrada (inyección, PII). Si bloquea, se responde sin LLM.
3. Expandir la consulta léxica con el glosario.
4. Recuperar (denso + BM25 + RRF + filtro de vigencia + rerank).
5. Abstenerse si la evidencia es débil.
6. Generar con citas [C#] sobre documentos delimitados.
7. Manejo de salida: quitar citas inexistentes, verificar respaldo de cada
   oración, guardrail de salida (PII) y abstención si no hay sustento.
"""

from __future__ import annotations

import re
from datetime import date

from riskrag.generation.llm import LLM
from riskrag.generation.prompts import (
    NOT_FOUND_TOKEN,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    citation_keys,
)
from riskrag.models import Answer, Citation
from riskrag.nlp.query_expansion import GlossaryEntry, expand_query
from riskrag.nlp.verifier import LexicalSupportVerifier, SupportVerifier, claim_sentences
from riskrag.retrieval.hybrid import HybridRetriever
from riskrag.security.audit import AuditLogger
from riskrag.security.guardrails import Guardrail
from riskrag.security.validation import sanitize_query

_CIT_RE = re.compile(r"\[(C\d+)\]")

ABSTAIN_MESSAGE = (
    "No encontré sustento suficiente en los documentos indexados para responder con "
    "seguridad. Reformula la pregunta o indica la norma o el tema específico."
)
BLOCKED_MESSAGE = (
    "No puedo procesar esta solicitud porque parece intentar cambiar mis reglas o "
    "extraer información protegida. Puedo ayudarte con preguntas de riesgo crediticio y seguros."
)


class RAGPipeline:
    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLM,
        guardrail: Guardrail,
        glossary: dict[str, GlossaryEntry] | None = None,
        verifier: SupportVerifier | None = None,
        audit: AuditLogger | None = None,
        min_relevance: float = 0.45,
        max_query_chars: int = 2000,
        max_unsupported_ratio: float = 0.5,
        max_answer_tokens: int = 900,
        temperature: float = 0.0,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.guardrail = guardrail
        self.glossary = glossary or {}
        self.verifier = verifier or LexicalSupportVerifier()
        self.audit = audit
        self.min_relevance = min_relevance
        self.max_query_chars = max_query_chars
        self.max_unsupported_ratio = max_unsupported_ratio
        self.max_answer_tokens = max_answer_tokens
        self.temperature = temperature

    def _log(self, event: str, actor: str | None, **fields: object) -> None:
        if self.audit:
            self.audit.log(event, actor=actor, **fields)

    def ask(
        self,
        question: str,
        *,
        actor: str | None = None,
        on: date | None = None,
        domain: str | None = None,
        intent: str | None = None,
    ) -> Answer:
        question = sanitize_query(question, self.max_query_chars)
        decision = self.guardrail.check(question, "INPUT")
        if not decision.allowed:
            self._log("query_blocked", actor, flags=decision.flags, question=question)
            return Answer(
                question=question,
                answer=BLOCKED_MESSAGE,
                abstained=True,
                intent=intent,
                security_flags=decision.flags,
            )
        safe_question = decision.text
        flags = list(decision.flags)

        lexical = expand_query(safe_question, self.glossary)
        retrieved = self.retriever.retrieve(
            safe_question, lexical_query=lexical, on=on, domain=domain
        )
        retrieved_ids = [r.chunk.chunk_id for r in retrieved]

        if not retrieved or retrieved[0].score < self.min_relevance:
            self._log(
                "abstain_low_evidence", actor, question=safe_question, retrieved=retrieved_ids
            )
            return Answer(
                question=safe_question,
                answer=ABSTAIN_MESSAGE,
                abstained=True,
                intent=intent,
                security_flags=flags,
                retrieved_ids=retrieved_ids,
            )

        keyed = citation_keys(retrieved)
        raw = self.llm.generate(
            SYSTEM_PROMPT,
            build_user_prompt(safe_question, keyed),
            self.max_answer_tokens,
            self.temperature,
        )

        if NOT_FOUND_TOKEN in raw:
            self._log("abstain_model", actor, question=safe_question, retrieved=retrieved_ids)
            return Answer(
                question=safe_question,
                answer=ABSTAIN_MESSAGE,
                abstained=True,
                intent=intent,
                security_flags=flags,
                retrieved_ids=retrieved_ids,
            )

        # Manejo seguro de salida (OWASP LLM05): solo citas que existen
        used = [k for k in dict.fromkeys(_CIT_RE.findall(raw)) if k in keyed]
        cleaned = _CIT_RE.sub(lambda m: m.group(0) if m.group(1) in keyed else "", raw).strip()
        if not used:
            flags.append("output:no_citations")
            self._log("abstain_no_citations", actor, question=safe_question)
            return Answer(
                question=safe_question,
                answer=ABSTAIN_MESSAGE,
                abstained=True,
                intent=intent,
                security_flags=flags,
                retrieved_ids=retrieved_ids,
            )

        evidence = [keyed[k].chunk.text for k in used]
        unsupported = self.verifier.unsupported(cleaned, evidence)
        n_sentences = max(1, len(claim_sentences(cleaned)))
        if len(unsupported) / n_sentences > self.max_unsupported_ratio:
            flags.append("output:low_faithfulness")
            self._log(
                "abstain_unsupported", actor, question=safe_question, unsupported=len(unsupported)
            )
            return Answer(
                question=safe_question,
                answer=ABSTAIN_MESSAGE,
                abstained=True,
                intent=intent,
                security_flags=flags,
                unsupported_claims=unsupported,
                retrieved_ids=retrieved_ids,
            )

        out_decision = self.guardrail.check(
            cleaned, "OUTPUT", query=safe_question, evidence=evidence
        )
        flags += out_decision.flags
        if not out_decision.allowed:
            return Answer(
                question=safe_question,
                answer=out_decision.text,
                abstained=True,
                intent=intent,
                security_flags=flags,
                retrieved_ids=retrieved_ids,
            )

        citations = [
            Citation(
                chunk_id=keyed[k].chunk.chunk_id,
                label=f"{k}: {keyed[k].chunk.citation_label()}",
                source_url=keyed[k].chunk.source_url,
            )
            for k in used
        ]
        self._log(
            "answer",
            actor,
            question=safe_question,
            citations=[c.chunk_id for c in citations],
            prompt_version=PROMPT_VERSION,
            unsupported=len(unsupported),
        )
        return Answer(
            question=safe_question,
            answer=out_decision.text,
            citations=citations,
            intent=intent,
            unsupported_claims=unsupported,
            security_flags=flags,
            retrieved_ids=retrieved_ids,
        )
