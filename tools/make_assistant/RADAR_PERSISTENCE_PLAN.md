# Propuesta de persistencia RADAR: oportunidad externa

Se preparó `radar_external_mapping_proposal.py` como **propuesta aislada**, sin importar el modelo en `core/models.py`, sin migraciones y sin escribir datos. El modelo enlaza una clave externa a `Oportunidad` y `Organizacion`, con unicidad por organización, origen y clave.

Para desplegar de forma segura faltan: crear migración Django, proteger el endpoint con autenticación y membresía activa, verificar que la organización del usuario coincide, implementar una transacción que cree oportunidad y correspondencia juntas, gestionar `IntegrityError` por concurrencia y devolver la oportunidad existente, y validar pruebas de integración con PostgreSQL.

El modelo propuesto debe incluir `full_clean()` al guardar o una validación de integridad equivalente en la capa de servicio. La comprobación `clean()` no se ejecuta automáticamente con `objects.create()`. No hay garantía de idempotencia externa sin transacción y clave única aplicada en la base de datos.
