# Verificación del esquema RADAR

Se consultó `core/models.py` en el repositorio RADAR. El modelo `Oportunidad` utiliza nombres en español: `organizacion`, `titulo`, `origen`, `canal`, `nombre_consultante`, `email_consultante`, `telefono_consultante`, `necesidad` y `estado`. La versión preliminar `integration_adapters.radar_opportunity` usa nombres ingleses `organization_id`, `external_key`, `origin`, `channel`, `status`, `contact_email`, que **no son campos del modelo**. No debe usarse para crear instancias Django.

`radar_model_adapter.opportunity_fields` genera un diccionario compatible con los campos reales, pero todavía no es una integración activa. La clave externa debe mantenerse en una tabla de correspondencia con restricción única por organización; no existe campo `external_key` en `Oportunidad`. Se necesita validar autorización multiempresa, permisos, deduplicación y prueba Django antes de cualquier escritura. La operación de Sheets es distinta de la creación de oportunidades: definir explícitamente ambos destinos y recibos separados.

No se modificó `core/models.py`, ninguna base de datos ni ningún escenario de Make.
