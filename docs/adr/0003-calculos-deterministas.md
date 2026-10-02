# ADR 0003: los cálculos regulatorios los hacen herramientas, no el LLM

Estado: aceptada (01/10/2026).

## Contexto
Clasificar un deudor o calcular una provisión es aritmética sobre tablas normativas. Los LLM cometen errores de cálculo y no son reproducibles bit a bit.

## Decisión
Las tablas viven en YAML versionado con fuente, URL y fecha de verificación. Funciones Python con `Decimal` y validación de entradas hacen el cálculo y devuelven el detalle y la referencia.

## Consecuencias
- Resultados reproducibles, auditables y probados en sus bordes (8 y 9 días, 120 y 121, 365 y 366).
- Actualizar la norma es cambiar un YAML revisado, no reentrenar ni reescribir prompts.
- El alcance simplificado (sin componente procíclico ni tratamientos especiales) se informa en cada respuesta.
