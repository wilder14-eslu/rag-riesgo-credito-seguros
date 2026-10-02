from riskrag.config import Settings
from riskrag.nlp.entities import extract_cross_references, extract_entities
from riskrag.nlp.intent import classify_intent
from riskrag.nlp.normalize import clean_text, split_sentences, tokenize
from riskrag.nlp.query_expansion import expand_query, load_glossary, lookup


def test_tokenize_keeps_numbers_and_stems_words():
    toks = tokenize("La Resolución 11356-2008 exige provisiones del 0,70%")
    assert "11356-2008" in toks
    assert "0,70%" in toks
    assert "la" not in toks  # stopword
    assert any(t.startswith("provision") for t in toks)


def test_clean_text_joins_hyphenated_words():
    assert clean_text("clasifi-\ncación  del   deudor") == "clasificación del deudor"


def test_split_sentences_respects_abbreviations():
    parts = split_sentences("Ver el Art. 5 del reglamento. Luego aplica la Tabla 1.")
    assert parts == ["Ver el Art. 5 del reglamento.", "Luego aplica la Tabla 1."]


def test_entities_extract_regulatory_items():
    text = (
        "Según la Resolución SBS N° 11356-2008, Capítulo II, la categoría Deficiente "
        "aplica con treinta y uno (31) a sesenta (60) días calendario y una tasa de 25.00%."
    )
    ents = extract_entities(text)
    assert ents["NORMA"] == ["11356-2008"]
    assert "II" in ents["CAPITULO"]
    assert "Deficiente" in ents["CATEGORIA_DEUDOR"]
    assert "25.00" in ents["PORCENTAJE"]
    assert "60" in ents["DIAS_ATRASO"]


def test_cross_references():
    refs = extract_cross_references("conforme al numeral 2.1 del Capítulo III y al artículo 4")
    assert any("numeral 2.1" in r for r in refs)


def test_intent_classification():
    assert (
        classify_intent("¿Qué categoría tiene un crédito de consumo con 45 días de atraso?").intent
        == "calculo"
    )
    assert (
        classify_intent("¿Qué establece la resolución SBS sobre garantías?").intent == "normativa"
    )
    assert (
        classify_intent("¿Cuál es la probabilidad de default de este cliente?").intent
        == "prediccion"
    )
    assert classify_intent("¿Quién ganó el mundial?").intent == "fuera_de_dominio"


def test_glossary_expansion_and_lookup():
    glossary = load_glossary(str(Settings().glossary_path))
    assert "Con Problemas Potenciales" in expand_query("deudores en CPP", glossary)
    assert lookup("niif 9", glossary).term == "IFRS 9"
