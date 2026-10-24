# Captación comercial — motor offline

Este módulo recibe leads estructurados, normaliza correo, calcula una clave SHA-256 para deduplicación, verifica consentimiento y **devuelve un plan de acciones** para registro y notificación interna. No se conecta a Gmail, Google Sheets, Make ni RADAR; no ejecuta acciones externas.

Estados: accepted, duplicate, review, rejected. La revisión por consentimiento ausente no implica descartar el lead: debe conservarse por el sistema de entrada autorizado según su política de privacidad. La clave de email no es anonimización y debe tratarse como dato personal.

Limitaciones antes de producción:
- Dedupe por email solamente; no resuelve personas con correos diferentes.
- Idempotencia real requiere un registro persistente con operación atómica y clave única.
- No hay control de concurrencia, reintentos, cola de errores, control de cuota, consentimiento legalmente validado, ni aislamiento multiempresa.
- Las notificaciones deben ser internas y no contener datos sensibles innecesarios.
- No crear escenarios Make listos para importar ni modificar producción a partir de este prototipo.

Próximo paso: conectar adaptadores autorizados, añadir almacenamiento transaccional y pruebas integradas con datos sintéticos.
