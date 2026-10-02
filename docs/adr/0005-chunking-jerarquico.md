# ADR 0005: chunking jerárquico según la estructura legal

Estado: aceptada (01/10/2026).

## Contexto
Cortar por número fijo de tokens separa reglas de sus excepciones y pierde la ubicación exacta (capítulo y numeral) que el usuario necesita para citar.

## Decisión
Detectar encabezados por nivel (Título, Capítulo o Anexo, Artículo o Numeral, Subnumeral), crear un fragmento por sección hoja, conservar el texto de la sección padre como contexto y dividir por oraciones con solapamiento solo si una sección es demasiado larga.

## Consecuencias
- Cada cita indica la ruta exacta, por ejemplo `Capítulo II, Numeral 3`.
- Las reglas de detección dependen del formato del documento; documentos con otra estructura requieren patrones adicionales, cubiertos por pruebas.
