# Piloto controlado de importación Gmail y Drive

## Condiciones de entrada
- Ejecutar `python manage.py check`, `python manage.py makemigrations --check --dry-run` y suite integral (incluyendo `integraciones_google`) con resultado exitoso.
- Crear credenciales OAuth **Web application** en Google Cloud y registrar exactamente `GOOGLE_OAUTH_REDIRECT_URI` como URI autorizada.
- Habilitar Gmail API y Google Drive API; configurar pantalla de consentimiento y agregar la cuenta piloto como usuario de prueba cuando corresponda.
- Configurar por variables de entorno `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`, `GOOGLE_OAUTH_ALLOWED_EMAILS` y `RADAR_OAUTH_TOKEN_KEY` (Fernet). No incluir secretos en GitHub ni documentación.
- Utilizar exclusivamente `gmail.readonly` y `drive.readonly`; administrador de la organización debe autorizar personalmente. No conectar ni leer datos reales sin autorización expresa.

## Prueba mínima con datos sintéticos
1. Preparar un correo y una carpeta de Drive de prueba con candidatos ficticios: CV + título, solo CV, solo título, documentos varios, mensaje sin adjuntos, duplicados y archivo ilegible.
2. Comprobar extracción de RUT con dígito verificador, nombre, dirección, email, teléfono, experiencia desde cuerpo de correo y documentos disponibles.
3. Registrar todos los candidatos sin bloquear por antecedentes ausentes; generar observaciones sobre CV, título y datos faltantes.
4. Clasificar solo CV y título; almacenar todos los demás adjuntos íntegros en «Otros documentos».
5. Verificar aislamiento por organización, deduplicación, procedencia de cada archivo y revisión/aprobación/rechazo posterior.
6. Desconectar la cuenta; comprobar eliminación de credenciales locales. Confirmar por separado la revocación remota en Google; una falla de red no equivale a revocación confirmada.
7. Revisar resultados y errores sin exponer tokens, RUT ni documentos sensibles en logs.

## Criterios de salida
- Sin pérdida de candidatos ni archivos, con observaciones no bloqueantes.
- Importación repetida sin duplicaciones inesperadas.
- Ningún acceso de escritura a Gmail o Drive.
- Pruebas automatizadas y validación integral exitosas.
- No fusionar a `main` sin aprobación explícita.

## Problema de CI conocido
El flujo heredado «Validar RADAR» ejecuta Playwright en Ubuntu 26.04, que no es compatible con la versión instalada. La validación integral alternativa fija Ubuntu 24.04 y ya existe. Corregir el flujo heredado en su archivo original cuando esté identificado; no interpretar su error de infraestructura como error de importación.
