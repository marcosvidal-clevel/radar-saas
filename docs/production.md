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

El repositorio no automatiza backups. El proveedor debe respaldar PostgreSQL y
el contenido de `RADAR_MEDIA_ROOT` con cifrado, retención y pruebas periódicas.

- PostgreSQL: restaurar un dump en una instancia aislada, verificar migraciones
  y ejecutar `manage.py check --deploy` antes de cambiar tráfico.
- Documentos: restaurar el volumen privado conservando nombres y permisos;
  comprobar descargas con un usuario autorizado y rechazo de otra organización.

Los logs deben ir al stdout/stderr del proceso y a la plataforma del proveedor;
la configuración incluida no registra contraseñas ni contenido de documentos.
