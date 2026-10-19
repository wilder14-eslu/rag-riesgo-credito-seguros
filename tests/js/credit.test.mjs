// El modelo ONNX que corre en el navegador debe dar la misma probabilidad que el XGBoost original.
// credit_cases.json guarda filas y probabilidades calculadas con model.predict_proba (Python).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import * as ort from "onnxruntime-web";

import { CreditScorer } from "../../site/js/credit.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(path.join(here, p));
const meta = JSON.parse(read("../../site/models/credit_default.meta.json", "utf8"));
const cases = JSON.parse(read("credit_cases.json", "utf8"));

ort.env.wasm.numThreads = 1;
const scorer = await CreditScorer.load(ort, { model: read("../../site/models/credit_default.onnx"), meta });

test("ONNX coincide con XGBoost en filas de referencia", async () => {
  for (let i = 0; i < cases.rows.length; i++) {
    const values = Object.fromEntries(meta.features.map((f, j) => [f.name, cases.rows[i][j]]));
    const r = await scorer.score(values);
    assert.ok(Math.abs(r.probability - cases.p[i]) < 1e-5, `fila ${i}: ${r.probability} vs ${cases.p[i]}`);
  }
});

test("el archivo ONNX publicado coincide con el hash de los metadatos", async () => {
  const { createHash } = await import("node:crypto");
  assert.equal(createHash("sha256").update(read("../../site/models/credit_default.onnx")).digest("hex"), meta.onnx_sha256);
});

test("variables vacías se imputan con la mediana de entrenamiento y los rangos se validan", async () => {
  const r = await scorer.score({ age: 40 });
  assert.ok(r.probability > 0 && r.probability < 1);
  assert.equal(scorer.validate({ age: 10 }).length, 1);
  assert.equal(scorer.validate({ age: 40 }).length, 0);
});

test("banda de riesgo y decisión siguen las reglas del modelo", async () => {
  const high = Object.fromEntries(meta.features.map((f, j) => [f.name, cases.rows[1][j]]));
  const r = await scorer.score(high);
  assert.equal(r.risk_band, "alto");
  assert.equal(r.decision, "rechazar");
});
