// Score de default con el modelo XGBoost exportado a ONNX (credit-risk-ml-platform).
// Corre en el navegador con onnxruntime-web: sin API, sin cold-start y sin enviar datos a nadie.

const BANDS = (p, bands) => (p < bands.bajo_menor_a ? "bajo" : p < bands.medio_menor_a ? "medio" : "alto");

export class CreditScorer {
  /**
   * @param ort   runtime de onnxruntime-web (global `ort` en el navegador)
   * @param files { model: Uint8Array | ArrayBuffer, meta: object }
   */
  constructor(ort, session, meta) {
    this.ort = ort;
    this.session = session;
    this.meta = meta;
    this.features = meta.features;
  }

  static async load(ort, { model, meta }) {
    const session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"] });
    return new CreditScorer(ort, session, meta);
  }

  /** Valida el formulario con los mismos rangos del esquema del modelo. Devuelve [] si es válido. */
  validate(values) {
    const errors = [];
    for (const f of this.features) {
      const v = values[f.name];
      if (v === undefined || v === null || Number.isNaN(v)) continue; // se imputa con la mediana de entrenamiento
      if (f.min !== null && v < f.min) errors.push(`${f.label}: debe ser al menos ${f.min}.`);
      if (f.max !== null && v > f.max) errors.push(`${f.label}: debe ser como máximo ${f.max}.`);
    }
    return errors;
  }

  async _run(rows) {
    const n = rows.length, d = this.features.length;
    const data = new Float32Array(n * d);
    rows.forEach((r, i) => r.forEach((x, j) => { data[i * d + j] = x; }));
    const input = new this.ort.Tensor("float32", data, [n, d]);
    const out = await this.session.run({ [this.meta.input_name]: input });
    const probs = out[this.meta.output_name].data; // [n, 2]: P(no default), P(default)
    return Array.from({ length: n }, (_, i) => probs[i * 2 + 1]);
  }

  /**
   * Probabilidad de default, decisión y factores principales.
   * Los factores son una aproximación por oclusión: cuánto baja la probabilidad si esa
   * variable toma la mediana de entrenamiento. No son valores SHAP.
   */
  async score(values) {
    const row = this.features.map((f) => {
      const v = values[f.name];
      return v === undefined || v === null || Number.isNaN(v) ? f.median : v;
    });
    const variants = [row, ...row.map((_, j) => row.map((x, k) => (k === j ? this.features[j].median : x)))];
    const probs = await this._run(variants);
    const p = probs[0];
    const factors = this.features
      .map((f, j) => ({ name: f.name, label: f.label, value: row[j], impact: p - probs[j + 1] }))
      .filter((x) => Math.abs(x.impact) > 1e-4)
      .sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))
      .slice(0, 5);
    return {
      probability: p,
      decision: p >= this.meta.threshold ? "rechazar" : "aprobar",
      risk_band: BANDS(p, this.meta.risk_bands),
      threshold: this.meta.threshold,
      factors,
    };
  }
}
