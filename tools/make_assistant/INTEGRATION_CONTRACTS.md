# Contratos de integración comercial (preparación, sin conexión)

## Google Sheets
Operación prevista: `append_lead`. Entrada: clave idempotente, email normalizado, nombre, fuente, fecha de recepción y consentimiento confirmado. Salida exigida: `{status:"confirmed", idempotency_key:"<clave>:append_lead", external_id:"<id fila verificable>"}`. Antes de marcar completado: verificar que el identificador existe y corresponde al mismo lead. La API de Sheets no ofrece por sí sola garantía de escritura exactamente una vez: será necesario un registro de operaciones con reconciliación y protección de concurrencia.

## RADAR
Operación prevista: crear o actualizar una oportunidad comercial, no un candidato. Campos preliminares: `origin=consulta_entrante`, `channel=web`, `status=nueva`; confirmar los campos y permisos reales del modelo. Requiere organización autorizada, deduplicación por clave externa y aislamiento entre organizaciones. No almacenar ni transmitir datos de prueba reales.

## Correo
`notify_internal` debe enviarse solo después de confirmar la persistencia de lead. Debe evitar datos sensibles innecesarios y usar una clave idempotente por acción. El contrato no implica que Gmail garantice deduplicación.

## Seguridad y operaciones
Credenciales solo en gestor de secretos. Los registros no deben exponer datos personales. Incorporar leases para varios workers, reintentos con backoff, dead-letter, reconciliación y pruebas integradas antes de ejecutar acciones externas.

**Estado:** los contratos son validaciones locales; no se ha probado acceso real a Google Sheets, RADAR ni Make.
