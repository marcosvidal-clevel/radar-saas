# Servicio transaccional RADAR — borrador sin despliegue

`radar_transaction_service.py` propone un único punto de entrada para importar oportunidades desde Make. Requiere usuario autenticado y membresía activa como administrador o supervisor; valida los campos permitidos, obliga a origen consulta entrante y canal web, bloquea la fila de organización y crea oportunidad y referencia externa en la misma transacción. Si la referencia existe, devuelve la oportunidad anterior.

**No es código desplegable todavía.** El modelo `OportunidadExterna` está únicamente en una propuesta y no existe en `core.models`; primero requiere revisión, migración y pruebas Django/PostgreSQL. El bloqueo por organización reduce paralelismo de importaciones; puede sustituirse más adelante por un mecanismo de bloqueo por clave. Se debe validar la política de servicio a servicio: un usuario de Make no debería ser una cuenta personal ni recibir permisos administrativos innecesarios. No se debe exponer este método directamente a una solicitud pública. La verificación de consentimiento y la autenticación del emisor deben estar en el endpoint.

Faltan pruebas de integración para rollback, concurrencia, aislamiento entre organizaciones, reintentos, y recuperación tras respuesta perdida. Ningún sistema externo fue modificado.
