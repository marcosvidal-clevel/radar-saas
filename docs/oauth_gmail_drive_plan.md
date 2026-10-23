# OAuth Gmail y Google Drive

## Alcance
Conexión de lectura únicamente. No enviar, editar ni borrar mensajes o archivos de origen.

## Scopes requeridos
Gmail readonly y Drive readonly. Solicitar solo los alcances necesarios.

## Configuración externa
Configurar en el gestor de secretos del entorno:
- GOOGLE_OAUTH_CLIENT_ID
- GOOGLE_OAUTH_CLIENT_SECRET
- GOOGLE_OAUTH_REDIRECT_URI
- GOOGLE_OAUTH_TOKEN_KEY
- GOOGLE_OAUTH_ALLOWED_EMAILS

No guardar valores reales en Git ni imprimirlos en logs.

## Flujo requerido
1. Solo un administrador autenticado puede iniciar la vinculación.
2. Generar state aleatorio, asociarlo a la sesión y validarlo en el callback.
3. Mostrar consentimiento explícito de Google.
4. Validar state, cuenta permitida y scopes devueltos.
5. Cifrar los tokens antes de persistirlos; la clave de cifrado debe permanecer fuera de la base de datos.
6. Asociar la conexión a una organización y una cuenta, aplicando aislamiento por organización.
7. Permitir revocación y eliminación segura de los tokens.
8. Auditar eventos sin guardar contenido de correos, documentos, tokens ni secretos.

## Pruebas previas a habilitar
- State inválido, ausente o reutilizado.
- Cuenta no autorizada y scopes insuficientes.
- Cifrado, descifrado, renovación y revocación.
- Separación entre organizaciones.
- Errores 401/403 y fallos de red.
- Prueba piloto con buzón y carpeta autorizados de pocos registros.

No activar ingestas programadas ni importar datos reales hasta superar las pruebas y aprobar la autorización del administrador.
