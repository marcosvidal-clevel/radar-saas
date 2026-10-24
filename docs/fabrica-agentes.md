# Fábrica de Agentes — Supervisor (prototipo)

Implementación local sin conexiones externas ni ejecución de escenarios.

## Pruebas
`python -m unittest agent_factory.test_supervisor -v`

## Alcance
- Cola SQLite de trabajos y deduplicación determinista.
- Aprobación previa para acciones sensibles.
- Registro de estados y resultados.

## Limitaciones antes de producción
- No hay ejecutor de tareas ni conexión a Make.
- La aprobación es una primitiva interna sin autenticación o autorización por usuario.
- No se deben incluir secretos o datos personales en payloads sin controles adicionales.
- Falta implementar leasing transaccional, reintentos, auditoría de eventos y permisos.
- No desplegar ni conectar a producción.
