# Conexión de solo lectura con Gmail y Google Drive

## Estado

El módulo `talento.conectores_fuentes` recibe un cliente de Google API ya autenticado. No crea OAuth, no almacena tokens y no solicita permisos por sí solo. La integración de credenciales y la validación con una cuenta de prueba siguen pendientes.

## Permisos mínimos recomendados

- Gmail: `https://www.googleapis.com/auth/gmail.readonly`
- Drive: `https://www.googleapis.com/auth/drive.readonly` (preferir un alcance más acotado si la estrategia de acceso a carpetas lo permite).

No solicitar permisos para enviar, modificar o borrar mensajes, ni para modificar o borrar archivos. La aplicación solo debe leer fuentes y guardar copias en RADAR.

## Flujo previsto

1. Un proceso de autenticación aprobado crea el cliente API de lectura.
2. Gmail llama a `importar_gmail_api(organizacion=..., servicio=..., consulta=..., limite=...)`.
3. Drive llama a `importar_drive_api(organizacion=..., servicio=..., carpeta_id=..., limite=...)`.
4. Los adaptadores entregan registros al flujo común de importación; el identificador del mensaje/archivo permite reintentos idempotentes.
5. Los errores por registro se devuelven para revisión y no deben provocar eliminación de fuentes ni cancelación de registros ya importados.

## Restricciones actuales

- No se incluye flujo OAuth, pantalla de consentimiento, almacenamiento/renovación de tokens ni gestión de secretos.
- Los documentos nativos de Google Drive se informan como pendientes: falta implementar exportación por MIME type.
- El cuerpo de Gmail busca texto plano; los mensajes que solo tengan HTML requieren conversión segura adicional.
- Se necesita verificar cómo se limitan las carpetas visibles y los buzones autorizados antes de habilitar uso real.
- No habilitar importaciones programadas ni fusionar a `main` hasta que pruebas de integración con clientes simulados y una cuenta de prueba autorizada pasen.

## Seguridad operativa

- No incluir tokens, secretos OAuth, contenido de candidatos ni adjuntos en logs.
- Limitar el acceso por organización; revisar permisos y auditoría antes de ejecutar ingestas.
- Probar primero con una carpeta y un buzón de prueba, con pocos registros.
- La importación no debe cambiar ni eliminar los originales.
