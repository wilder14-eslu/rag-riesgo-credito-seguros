// Stemmer Snowball para español (port de spanish.sbl, Snowball 3.1.1).
// Es el mismo algoritmo que usa `snowballstemmer` en Python: así los términos de la
// consulta y del índice coinciden en el navegador. Las entradas con tilde se omiten
// porque el tokenizador ya quita las tildes antes de aplicar el stemmer.

const VOWELS = "aeiouáéíóúü";
const isV = (ch) => VOWELS.includes(ch);

const PRONOUNS = ["la", "sela", "le", "me", "se", "lo", "selo", "las", "selas", "les", "los", "selos", "nos"];
// [sufijo, código]; 6 = borrar el pronombre, 7 = "yendo" precedido de "u"
const VERB_FORMS = [["ando", 6], ["iendo", 6], ["yendo", 7], ["ar", 6], ["er", 6], ["ir", 6]];
const A3 = [["ic", 0], ["ad", 0], ["os", 0], ["iv", 1]];
const A4 = ["able", "ible", "ante"];
const A5 = ["ic", "abil", "iv"];
const A6 = [
  ["ica", 1], ["ancia", 2], ["encia", 5], ["adora", 2], ["osa", 1], ["ista", 1], ["iva", 9],
  ["anza", 1], ["idad", 8], ["able", 1], ["ible", 1], ["ante", 2], ["mente", 7], ["amente", 6],
  ["acion", 2], ["ucion", 4], ["ico", 1], ["ismo", 1], ["oso", 1], ["amiento", 1], ["imiento", 1],
  ["ivo", 9], ["ador", 2], ["icas", 1], ["ancias", 2], ["encias", 5], ["adoras", 2], ["osas", 1],
  ["istas", 1], ["ivas", 9], ["anzas", 1], ["idades", 8], ["ables", 1], ["ibles", 1],
  ["aciones", 2], ["uciones", 4], ["adores", 2], ["antes", 2], ["icos", 1], ["ismos", 1],
  ["osos", 1], ["amientos", 1], ["imientos", 1], ["ivos", 9],
];
const A7 = ["ya", "ye", "yan", "yen", "yeron", "yendo", "yo", "yas", "yes", "yais", "yamos"];
const A8 = [
  ["aba", 2],
  ["ada", 2],
  ["ida", 2],
  ["ara", 2],
  ["iera", 2],
  ["ad", 2],
  ["ed", 2],
  ["id", 2],
  ["ase", 2],
  ["iese", 2],
  ["aste", 2],
  ["iste", 2],
  ["an", 2],
  ["aban", 2],
  ["aran", 2],
  ["ieran", 2],
  ["en", 1],
  ["asen", 2],
  ["iesen", 2],
  ["aron", 2],
  ["ieron", 2],
  ["ado", 2],
  ["ido", 2],
  ["ando", 2],
  ["iendo", 2],
  ["ar", 2],
  ["er", 2],
  ["ir", 2],
  ["as", 2],
  ["abas", 2],
  ["adas", 2],
  ["idas", 2],
  ["aras", 2],
  ["ieras", 2],
  ["es", 1],
  ["ases", 2],
  ["ieses", 2],
  ["abais", 2],
  ["arais", 2],
  ["ierais", 2],
  ["aseis", 2],
  ["ieseis", 2],
  ["asteis", 2],
  ["isteis", 2],
  ["ados", 2],
  ["idos", 2],
  ["amos", 2],
  ["emos", 1],
  ["aremos", 2],
  ["eremos", 2],
  ["iremos", 2],
  ["imos", 2],
];
const A9 = [["a", 1], ["e", 2], ["o", 1], ["os", 1]];

/** Sufijo más largo de `w[lb:end]` que esté en la lista. Devuelve [código, inicio] o null. */
function longest(w, end, list, lb = 0) {
  let best = null;
  for (const item of list) {
    const [suf, code] = Array.isArray(item) ? item : [item, 1];
    const start = end - suf.length;
    if (start >= lb && w.startsWith(suf, start) && (!best || suf.length > best.len)) {
      best = { code, start, len: suf.length };
    }
  }
  return best;
}

function regions(w) {
  const n = w.length;
  let pV = n, p1 = n, p2 = n;
  const v = (i) => isV(w[i]);
  const skip = (i, wantVowel) => { while (i < n && v(i) === !wantVowel) i++; return i; };
  if (n >= 2) {
    if (v(0) && v(1)) {
      const i = skip(2, false); // saltar vocales hasta una consonante
      if (i < n) pV = i + 1;
    } else if (!v(1)) {
      const i = skip(2, true); // saltar consonantes hasta una vocal
      if (i < n) pV = i + 1;
    } else if (n >= 3) {
      pV = 3; // consonante-vocal: región tras la tercera letra
    }
  }
  let i = skip(0, true);
  if (i < n) {
    i = skip(i + 1, false);
    if (i < n) {
      p1 = ++i;
      i = skip(i, true);
      if (i < n) {
        i = skip(i + 1, false);
        if (i < n) p2 = i + 1;
      }
    }
  }
  return { pV, p1, p2 };
}

export function stem(word) {
  let w = word;
  const { pV, p1, p2 } = regions(w);
  const R2 = (pos) => p2 <= pos;
  const RV = (pos) => pV <= pos;
  const cut = (start) => { w = w.slice(0, start); };

  // Paso 0: pronombres enclíticos
  {
    const pr = longest(w, w.length, PRONOUNS);
    if (pr) {
      const vb = longest(w, pr.start, VERB_FORMS);
      if (vb && RV(vb.start)) {
        if (vb.code === 6) cut(pr.start);
        else if (vb.start > 0 && w[vb.start - 1] === "u") cut(pr.start);
      }
    }
  }

  // Paso 1: sufijos estándar
  const standard = () => {
    const m = longest(w, w.length, A6);
    if (!m) return false;
    const s = m.start;
    const optional = (list, needAt) => {
      const o = longest(w, w.length, list);
      if (o && R2(o.start)) {
        const code = o.code;
        cut(o.start);
        if (needAt && code === 1) {
          const at = longest(w, w.length, ["at"]);
          if (at && R2(at.start)) cut(at.start);
        }
      }
    };
    switch (m.code) {
      case 1: if (!R2(s)) return false; cut(s); break;
      case 2:
        if (!R2(s)) return false;
        cut(s);
        { const ic = longest(w, w.length, ["ic"]); if (ic && R2(ic.start)) cut(ic.start); }
        break;
      case 3: if (!R2(s)) return false; w = w.slice(0, s) + "log"; break;
      case 4: if (!R2(s)) return false; w = w.slice(0, s) + "u"; break;
      case 5: if (!R2(s)) return false; w = w.slice(0, s) + "ente"; break;
      case 6:
        if (p1 > s) return false;
        cut(s);
        optional(A3, true);
        break;
      case 7:
        if (!R2(s)) return false;
        cut(s);
        optional(A4.map((x) => [x, 0]), false);
        break;
      case 8:
        if (!R2(s)) return false;
        cut(s);
        optional(A5.map((x) => [x, 0]), false);
        break;
      default: // 9
        if (!R2(s)) return false;
        cut(s);
        { const at = longest(w, w.length, ["at"]); if (at && R2(at.start)) cut(at.start); }
    }
    return true;
  };

  const yVerb = () => {
    if (w.length < pV) return false;
    const m = longest(w, w.length, A7, pV);
    if (!m) return false;
    if (m.start <= 0 || w[m.start - 1] !== "u") return false;
    cut(m.start);
    return true;
  };

  const verb = () => {
    if (w.length < pV) return false;
    const m = longest(w, w.length, A8, pV);
    if (!m) return false;
    if (m.code === 1) {
      // "gu" + sufijo: se borra también la u
      if (m.start >= 2 && w[m.start - 1] === "u" && w[m.start - 2] === "g") cut(m.start - 1);
      else cut(m.start);
    } else cut(m.start);
    return true;
  };

  if (!standard()) {
    if (!yVerb()) verb();
  }

  // Paso 3: sufijo residual
  {
    const m = longest(w, w.length, A9);
    if (m) {
      const s = m.start;
      if (m.code === 1) {
        if (RV(s)) cut(s);
      } else if (RV(s)) {
        cut(s);
        if (w.length > 0 && w[w.length - 1] === "u" && w.length >= 2 && w[w.length - 2] === "g") {
          if (RV(w.length - 1)) cut(w.length - 1);
        }
      }
    }
  }
  return w;
}
