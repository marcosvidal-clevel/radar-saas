# Ruta de autonomía — Make / C-Level Partners / RADAR

Estado: desarrollo offline, **sin acceso en vivo a Make**.

## Entregado
- Inspector estático de blueprints.
- Cliente API solo lectura, pendiente de credencial y ejecución en entorno autorizado.
- Compilador de planes restringidos a **borradores no importables**.
- Diagnóstico estático y pruebas unitarias.

## Próximos hitos
1. Leer los dos blueprints exportados y construir una matriz de módulos, rutas, dependencias, conexiones y errores.
2. Extender el compilador a un formato de Make verificable contra exportaciones reales; nunca inventar conexiones, identificadores ni mappings.
3. Añadir lógica de deduplicación de leads, validación de consentimiento, alertas, reintentos y registro de auditoría.
4. Crear adaptadores configurables por sitio (C-Level Partners) y aplicación (RADAR), con aislamiento de datos.
5. Ejecutar pruebas de extremo a extremo en un entorno de pruebas aislado.
6. Vincular credencial API con alcance mínimo en un almacén de secretos; primero GET, después escrituras solo con autorización explícita.
7. Desplegar un ejecutor persistente programado, monitorizado y con alertas. **GitHub por sí solo no equivale a un agente siempre activo**.

No introducir datos personales, claves API o tokens en el repositorio. No modificar web ni escenarios de producción sin permiso específico.
