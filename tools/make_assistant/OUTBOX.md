# Cola transaccional de acciones comerciales (offline)

`commercial_outbox.py` guarda el lead y sus acciones `append_lead` y `notify_internal` en una misma transacción SQLite. Un email normalizado solo puede insertarse una vez; los trabajos permanecen pendientes hasta recibir confirmación del ejecutor. Cada error aumenta el contador; al quinto fallo pasa a `failed` para revisión.

**Importante:** no hay todavía un ejecutor externo, política de backoff, lease de concurrencia, protección ante caída entre efecto externo y confirmación, cifrado de datos en reposo, ni verificación de permisos RADAR. No garantiza entrega exactamente una vez a servicios externos. El contenido almacenado es dato personal: usar únicamente datos sintéticos hasta implementar seguridad, retención y borrado. No conectar a producción.
