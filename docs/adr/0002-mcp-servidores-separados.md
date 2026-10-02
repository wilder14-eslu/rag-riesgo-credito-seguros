# ADR 0002: dos servidores MCP separados por permiso

Estado: aceptada (01/10/2026).

## Contexto
Las herramientas tienen riesgos distintos: leer el índice es inocuo; llamar a la API del modelo de default envía datos de un solicitante a otro sistema.

## Decisión
`rag-normativa` agrupa herramientas de solo lectura sobre el corpus. `riesgo-credito` agrupa cálculos y la llamada externa.

## Consecuencias
- Un cliente puede habilitar solo la lectura de normativa.
- Permisos de red e IAM distintos por servidor en el despliegue.
- Dos procesos que mantener; se acepta por el aislamiento que ganan.
