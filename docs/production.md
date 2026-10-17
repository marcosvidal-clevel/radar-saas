# Configuración de producción

El desarrollo local continúa usando `config.settings`. Producción usa
`DJANGO_SETTINGS_MODULE=config.settings_production` y variables `RADAR_*`.

1. Copia `.env.example` a un gestor de secretos o al entorno del proveedor y
   sustituye todos los valores ficticios. No guardes el archivo real en Git.
2. Define una clave secreta larga, `RADAR_ALLOWED_HOSTS`, los orígenes CSRF y
   la conexión PostgreSQL del proveedor. La configuración de producción falla
   al iniciar si faltan clave, hosts, orígenes CSRF o credenciales de base.
3. Monta `RADAR_MEDIA_ROOT` como almacenamiento privado y persistente. No
   publiques esa ruta como estáticos: las descargas de CV pasan por la vista
   autorizada de documentos.
4. Ejecuta las comprobaciones y estáticos:

   ```bash
   export DJANGO_SETTINGS_MODULE=config.settings_production
   .venv/bin/python manage.py check --deploy
   .venv/bin/python manage.py migrate
   .venv/bin/python manage.py collectstatic --noinput
   ```

5. Sirve `config.wsgi:application` con un servidor WSGI/ASGI detrás de HTTPS.
   Si existe un proxy TLS, define `RADAR_TRUST_PROXY_HEADERS=true` y sus redes
   CIDR en `RADAR_TRUSTED_PROXY_IPS`; de lo contrario, Django no confía en
   `X-Forwarded-Proto`.

## Backups y restauración

`scripts/radar_backup.py` prepara un respaldo manual conjunto de PostgreSQL y
`RADAR_MEDIA_ROOT`. Es una herramienta, no un servicio programado: no elimina
respaldos ni configura almacenamiento externo. El destino debe estar fuera del
repositorio y se crea con permisos restrictivos (`0700` para directorios,
`0600` para archivos). Nunca se copian `.env`, credenciales o secretos.

Para coherencia entre relaciones y documentos, pausa las escrituras de RADAR
(modo mantenimiento o detén el proceso de aplicación), espera a que terminen
las transacciones en curso y ejecuta ambos pasos en la misma pausa:

```bash
export RADAR_DB_NAME=radar_production
export RADAR_DB_USER=radar_app
export RADAR_DB_PASSWORD='(secreto del proveedor, no lo escribas en logs)'
export RADAR_DB_HOST=postgres.internal.example.test
export RADAR_DB_PORT=5432
./.venv/bin/python scripts/radar_backup.py backup \
  --destination /var/backups/radar/2026-10-17T120000Z \
  --media-root "$RADAR_MEDIA_ROOT" \
  --schema-version "talento.0011_entrevista_recomendacion_entrevista_resultado"
```

El manifiesto contiene versión, fecha UTC, versión del esquema, rutas relativas,
tamaños y SHA-256 del dump y cada documento. La herramienta rechaza archivos
ausentes, symlinks, rutas fuera de `MEDIA_ROOT`, destinos dentro del repositorio
y errores de `pg_dump`.

La restauración exige una base nueva y un directorio nuevo y vacío; valida el
manifiesto y las sumas antes de crear la base:

```bash
./.venv/bin/python scripts/radar_backup.py restore \
  --backup /var/backups/radar/2026-10-17T120000Z \
  --database radar_restore_20261017 \
  --media-root /var/lib/radar/restore-20261017
```

No se sobrescriben destinos existentes, no se siguen symlinks y no se eliminan
respaldos automáticamente. Después de restaurar, valida migraciones, relaciones,
descargas autorizadas y acceso cruzado entre organizaciones antes de promover
la instancia restaurada.

Los logs deben ir al stdout/stderr del proceso y a la plataforma del proveedor;
la configuración incluida no registra contraseñas ni contenido de documentos.
