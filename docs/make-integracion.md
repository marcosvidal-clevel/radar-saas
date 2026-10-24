# Make, RADAR/My Ally y C-Level Partners

Estado comprobado el 24/10/2026. Este adaptador consulta Make desde RADAR;
no es todavía la recepción de oportunidades en RADAR ni un despliegue.

## Inventario observado en Make

Organización 1442596 (Marcos Vidal), equipo 576170, zona US1.

| ID | Nombre | Estado observado |
| --- | --- | --- |
| 4996755 | C-Level · SEO · Monitor Google | Activo |
| 4996645 | C-Level · Comercial · PRUEBAS sin envíos | Inactivo |
| 4967558 | Integration RSS | Inactivo |
| 2266448 | New scenario | Inactivo |

El navegador tiene sesión válida. API access muestra **No items found** en
Tokens. Por tanto, no hay autenticación API comprobada. Se preparó un formulario
de token limitado a la organización Marcos Vidal y `scenarios:read`, sin
crearlo. Un test local no constituye verificación de acceso real.

## Verificación reproducible

Guardar `MAKE_API_TOKEN` en el gestor de secretos del entorno que ejecute
RADAR, nunca en Git, ZIP, frontend, una hoja, un correo o logs. No pasar el
token por argumentos de terminal. Variables no secretas: `MAKE_ZONE=us1` y
`MAKE_TEAM_ID=576170`. Con el entorno Django ya configurado:

```bash
python manage.py verificar_make
```

Solo envía GET a `/api/v2/scenarios`, con paginación y columnas mínimas.
Comprueba la presencia de los escenarios SEO y comercial. Solo tras respuesta
válida marca `authentication=verified` y fecha UTC. Errores HTTP, ausencia de
escenarios, páginas incompletas o datos inconsistentes fallan sin imprimir
cuerpos de respuestas ni credenciales. No usa la sesión del navegador, no
ejecuta escenarios, no escribe en base de datos y no envía comunicaciones.

Pruebas sin red ni base de datos:

```bash
python -m unittest core.test_make_api -v
```

Documentación primaria usada:
- https://developers.make.com/api-documentation/authentication
- https://developers.make.com/api-documentation/authentication/api-scopes-overview
- https://developers.make.com/api-documentation/api-reference/scenarios

## Conexión comercial pendiente

La web V29 usa FormSubmit hacia Gmail corporativo. El escenario comercial
ya lee ese buzón, extrae HTML y escribe en Pruebas_Make con deduplicación por
ID Gmail; permanece inactivo. Sheets es el destino probado. RADAR aún no tiene
una ruta API de recepción desplegada ni credencial de ingreso configurada.

Para el siguiente tramo se necesita una URL HTTPS estable de RADAR y un
receptor autenticado con identidad de sitio/organización fijada en servidor,
clave idempotente única por buzón/mensaje y transacción. Conservar datos
incompletos para revisión y consentimiento original, sin inferir permisos de
marketing. Empezar con datos sintéticos y modo prueba separado; no convertir
la consulta controlada de Marcos en una oportunidad real. Mantener captura
incremental, cola y recuperación de fallos antes de activar Make. No enviar
respuestas a clientes en pruebas ni publicar cambios web.

La credencial Make de lectura permite inspeccionar escenarios; no sirve como
credencial para ingresar oportunidades en RADAR. Son conexiones diferentes.
