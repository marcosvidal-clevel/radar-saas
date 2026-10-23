# Importación masiva sin bloqueos

Reglas aprobadas:
- Crear la ficha incluso con antecedentes incompletos; si no se conoce el nombre, usar un identificador provisional trazable y registrar observación.
- Identificar primero CV y título. Los demás archivos se guardan como OTRO sin clasificación iterativa.
- Extraer RUT, nombre, dirección, correo y celular de CV, título, adjuntos relevantes y cuerpo del correo cuando exista; no inventar datos.
- Ausencias o errores de lectura producen observaciones, nunca descarte automático.
- Mantener documentos originales, procedencia, identificador de origen, hash y separación por organización; evitar duplicados verificables.
- Permitir revisión, aprobación o rechazo posterior y registrar auditoría.
- Ingesta desde Drive y correo debe ser idempotente, tolerante a fallos por registro y con permisos mínimos.
- No cambiar registros existentes ni desplegar sin pruebas.

Criterios de aceptación: carga de lote mixto con archivos legibles/ilegibles y datos faltantes; todos los elementos trazables quedan registrados; CV/título reconocidos cuando es posible; demás adjuntos tipo OTRO; reimportación no duplica; controles de organización respetados.