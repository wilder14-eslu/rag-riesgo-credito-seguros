/*
================================================================================
Descripción breve : Búsqueda híbrida en la base: combina similitud vectorial y
                    texto completo en español con Reciprocal Rank Fusion (RRF),
                    filtrando por vigencia y dominio.
Input             : p_embedding VECTOR(1024), p_consulta TEXT, p_fecha DATE,
                    p_dominio TEXT (NULL = todos), p_k INT, p_rrf_k INT
Output            : Tabla (chunk_id, puntaje_rrf, rango_denso, rango_lexico)
Creado por        : Alex Espinoza
Fec Creación      : 01/10/2026
Fec Actualización : 01/10/2026
Responsable       : Wilder Espinoza Luna
Motivo            : Permitir la fusión híbrida dentro de PostgreSQL cuando el
                    volumen del corpus hace costoso traer candidatos a la aplicación.
--------------------------------------------------------------------------------
Historial:
  01/10/2026  Alex Espinoza  Creación inicial.
================================================================================
*/

DROP FUNCTION IF EXISTS rag.fnt_buscar_chunks_hibrido(VECTOR, TEXT, DATE, TEXT, INT, INT);

CREATE FUNCTION rag.fnt_buscar_chunks_hibrido(
    p_embedding VECTOR(1024),
    p_consulta  TEXT,
    p_fecha     DATE DEFAULT CURRENT_DATE,
    p_dominio   TEXT DEFAULT NULL,
    p_k         INT  DEFAULT 20,
    p_rrf_k     INT  DEFAULT 60
)
RETURNS TABLE (chunk_id TEXT, puntaje_rrf DOUBLE PRECISION, rango_denso INT, rango_lexico INT)
LANGUAGE sql STABLE
AS $$
    WITH vigentes AS (
        SELECT C.chunk_id, C.embedding, C.texto_busqueda
        FROM rag.chunk C
        WHERE (C.vigente_desde IS NULL OR C.vigente_desde <= p_fecha)
          AND (C.vigente_hasta IS NULL OR C.vigente_hasta >= p_fecha)
          AND (p_dominio IS NULL OR C.dominio = p_dominio)
    ),
    densos AS (
        SELECT V.chunk_id,
               ROW_NUMBER() OVER (ORDER BY V.embedding <=> p_embedding) AS rango
        FROM vigentes V
        ORDER BY V.embedding <=> p_embedding
        LIMIT p_k
    ),
    lexicos AS (
        SELECT V.chunk_id,
               ROW_NUMBER() OVER (ORDER BY ts_rank_cd(V.texto_busqueda, Q.consulta) DESC) AS rango
        FROM vigentes V,
             websearch_to_tsquery('spanish', p_consulta) AS Q(consulta)
        WHERE V.texto_busqueda @@ Q.consulta
        ORDER BY ts_rank_cd(V.texto_busqueda, Q.consulta) DESC
        LIMIT p_k
    )
    SELECT COALESCE(D.chunk_id, L.chunk_id)                         AS chunk_id,
           COALESCE(1.0 / (p_rrf_k + D.rango), 0)
         + COALESCE(1.0 / (p_rrf_k + L.rango), 0)                   AS puntaje_rrf,
           D.rango::INT                                             AS rango_denso,
           L.rango::INT                                             AS rango_lexico
    FROM densos D
    FULL OUTER JOIN lexicos L ON L.chunk_id = D.chunk_id
    ORDER BY puntaje_rrf DESC
    LIMIT p_k;
$$;

GRANT EXECUTE ON FUNCTION rag.fnt_buscar_chunks_hibrido(VECTOR, TEXT, DATE, TEXT, INT, INT)
    TO riskrag_lectura;
