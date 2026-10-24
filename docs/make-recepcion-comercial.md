# Recepción comercial de Make en RADAR/My Ally

Código preparado para pruebas y revisión; no desplegado. La configuración
predeterminada está vacía: la ruta responde 404 hasta habilitar un sitio.
No requiere la API de administración de Make ni el token `scenarios:read`.

## Contrato

`POST /integraciones/make/comercial/c-level-web/`, exclusivamente HTTPS.
Cabeceras: `Content-Type: application/json` y `Authorization: Bearer <secreto>`.
El secreto es nuevo e independiente del token API Make. No crearlo ni guardarlo
en código, frontend, una hoja, bitácora o respaldo. Configurarlo en el almacén
de credenciales HTTP de Make y en el gestor de secretos del servidor.

Ejemplo sintético, nunca una consulta real:

```json
{
  "schema_version": 1,
  "source_message_id": "synthetic-001",
  "received_at": "2026-10-24T12:00:00Z",
  "test_mode": true,
  "nombre": "Contacto ficticio",
  "empresa": "Empresa de prueba",
  "email": "prueba@example.test",
  "telefono": "+56000000000",
  "necesidad": "Gerencia técnica",
  "sector": "Infraestructura",
  "consulta": "Solo prueba; no contactar",
  "autorizacion_contacto": "Texto original de autorización del formulario"
}
```

Campos personales ausentes pueden omitirse; se conservan como vacíos con
observaciones. Identificador, versión y modo son obligatorios. Se rechazan
tipos incorrectos, campos desconocidos, NUL y excesos de tamaño (máximo 32 KiB).
No se clasifica un mensaje como comercial por su contenido: Make debe mantener
su filtro de asunto/remitente y exclusiones de CV antes de llamar a esta ruta.

En producción, `RADAR_MAKE_INGRESS_JSON` contiene un objeto por sitio:

```json
{
  "c-level-web": {
    "organizacion_id": 123,
    "buzon": "formularios@example.test",
    "token_sha256": "REEMPLAZAR_POR_HASH_SHA256_DEL_SECRETO",
    "test_mode": true
  }
}
```

El ID es ilustrativo: resolver la organización real antes de configurar. Usar
un secreto aleatorio distinto por sitio, con al menos 32 caracteres. Solo su
hash SHA256 va en esta configuración; el valor completo va en la credencial
HTTP de Make. La configuración nunca se toma del cuerpo de la solicitud.
La misma identidad de mensaje en el mismo buzón/organización/modo es única.

## Resultados y controles

- 201: recepción persistida; guardar `recepcion_id` como comprobante.
- 200 y `duplicado=true`: mismo mensaje/contenido ya recibido; no repetir alta.
- 409: contenido distinto para el mismo ID o modo distinto al del servidor;
  conservar el mensaje para revisión, sin sobrescribir.
- 400/401/404/413/415/503: consulta o configuración inválida; no marcar entregado.
- Error del servidor o timeout: reintento acotado con el mismo ID y contenido,
  usando recuperación de ejecuciones incompletas en Make.

Modo prueba crea solo una recepción, sin oportunidad comercial. El cliente no
puede elegir el modo de servidor. Modo real crea recepción y oportunidad en
una sola transacción; un fallo revierte ambas. Bloqueo por organización y
restricción única protegen los reintentos. Otro ID con contenido similar se
conserva y se observa, sin descartarlo. No se infiere autorización de marketing
ni se envían correos. La autorización original queda en la recepción.

Las recepciones solo son consultables en admin por superusuarios, con campos
de solo lectura. No se publican rutas de listado ni datos personales en la
respuesta API. La oportunidad comercial mantiene los permisos existentes por
organización. Preparar luego una bandeja específica para gestores autorizados.

## Antes de conectar el escenario existente

1. Revisar la propuesta y validar migración/pruebas con PostgreSQL.
2. Desplegar RADAR en HTTPS estable y aplicar migración en el entorno de prueba.
3. Configurar identidad, secreto y `test_mode=true`; mantener el escenario
   comercial 4996645 inactivo mientras se hace una ejecución manual sintética.
4. Mapear `7.id` a source_message_id y la colección del parser a los campos.
   El teléfono viaja como cadena; usar módulo de creación de JSON, sin interpolar
   texto libre dentro de JSON manual. Registrar el recibo sin exponer el secreto.
5. Probar repetición, timeout y falta de campos. Añadir limitación de peticiones
   y tamaño de cuerpo en el proxy de despliegue; el endpoint solo limita tamaño.
6. Resolver captura incremental y recuperación de cola; coordinar el destino
   Sheets y RADAR para no detener la entrega a RADAR cuando Sheets ya registró
   el ID. La deduplicación de cada destino debe tener su propio comprobante.
7. Habilitar modo real solo después de validar el piloto; no reutilizar las
   consultas de prueba de Marcos como oportunidades comerciales reales.

No cambiar la web V29 ni enviar comunicaciones a clientes durante pruebas.
