// Paridad Python <-> JavaScript del motor de RiskRAG.
// Python genera tests/js/golden.json con scripts/make_golden.py; aquí se comprueba que el
// motor del navegador produce exactamente las mismas salidas.
//
//   node --test tests/js/

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { RiskRag, tokenize, HashingEmbedder } from "../../site/js/riskrag.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const kb = JSON.parse(readFileSync(path.join(here, "../../site/data/kb.json"), "utf8"));
const golden = JSON.parse(readFileSync(path.join(here, "golden.json"), "utf8"));
const rag = new RiskRag(kb);

test("tokenizador y stemmer coinciden con Python", () => {
  for (const g of golden.tokens) assert.deepEqual(tokenize(g.text), g.tokens, g.text);
});

test("embeddings por hashing coinciden con Python (BLAKE2b idéntico)", () => {
  const emb = new HashingEmbedder(kb.meta.dim);
  for (const g of golden.vectors) {
    const v = emb.vector(g.text);
    assert.equal(v.length, g.vector.length);
    const maxDiff = Math.max(...g.vector.map((x, i) => Math.abs(x - v[i])));
    assert.ok(maxDiff < 1e-5, `${g.text}: diff ${maxDiff}`);
  }
});

test("preguntas: respuesta, fuentes y señales de seguridad iguales", () => {
  let n = 0;
  for (const g of golden.ask) {
    assert.equal(rag.ask(g.q), g.markdown, `Pregunta: ${g.q}`);
    if (g.q.trim()) {
      const r = rag.agentRun(g.q);
      assert.equal(r.intent, g.intent, `intención de: ${g.q}`);
      assert.deepEqual(r.answer.retrieved_ids, g.retrieved, `fragmentos de: ${g.q}`);
      assert.deepEqual(r.answer.security_flags, g.flags, `señales de: ${g.q}`);
    }
    n++;
  }
  assert.ok(n >= 40, `solo ${n} preguntas`);
});

test("clasificación por atraso igual en todos los tipos de crédito", () => {
  for (const g of golden.classify) assert.equal(rag.classify(g.label, g.days), g.markdown, JSON.stringify(g));
});

test("provisiones con aritmética decimal exacta", () => {
  assert.ok(golden.provision.length > 500);
  for (const g of golden.provision) {
    assert.equal(rag.provision(g.label, g.cat, g.amount, g.covered, g.guar), g.markdown, JSON.stringify(g));
  }
});
