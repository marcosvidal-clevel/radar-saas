# Bandeja privada de entradas pendientes

Ruta: `/seleccion/entradas/`. Hay un acceso desde Inicio de Selección para usuarios
con `talento.view_entradapendiente`. Se reutiliza la interfaz de administración,
la sesión de Django y las membresías de organización.

Una entrada no es un candidato. Conserva el archivo original, su SHA-256, el nombre
original y la tupla organización/fuente/procedencia/clave documental. No hay
extracción, indexación de CV, OCR, contacto automático ni candidatos ficticios
al recibir o revisar una entrada. Archivo y procedencia quedan inmutables.

## Datos y revisión

Identidad, profesión y ubicación tienen estados independientes: no consta,
no confirmado y confirmado. Región o ciudad bastan para indicar ubicación;
no se solicita domicilio completo. El nombre puede quedar vacío.

Teléfono y correo personal tienen estados independientes: disponibles, ausentes o
no confirmados. «Disponible» requiere corroborarlo como personal; la fuente de
la confirmación es obligatoria. El correo del remitente es un campo independiente
y no se copia a una persona. Se rechazan dominios de portales conocidos y buzones
genéricos como contactos personales disponibles. No se deducen nombres de correos.
Una dirección no corroborada puede conservarse con estado no confirmado.

Se guardan limitación de lectura, información por completar y seguimiento:
pendiente, requiere contactar, sin medio de contacto o resuelto. No tener texto
no invalida el archivo ni determina la identidad.

Cada recepción, edición y resolución guarda una instantánea con usuario, fecha y
fuente en `RevisionEntrada`. El historial solo se consulta dentro de la entrada
autorizada; no hay una edición ni borrado de revisiones en esta interfaz.

## Resolver

Identidad y clasificación del archivo deben estar confirmadas. La persona destino
se selecciona explícitamente o se solicita crear una nueva. Los posibles duplicados
por nombre, contacto confirmado o hash se muestran como avisos y bloquean crear
una ficha nueva sin revisión; no se asocia automáticamente por esos indicios.

Una ficha seleccionada debe ser canónica y de la misma organización. Los datos
confirmados contradictorios bloquean la operación. No se modifican campos de una
ficha existente, ni siquiera para rellenar vacíos: deben completarse por su flujo
habitual si se quiere hacerlo. Para personas nuevas se copian solo valores
confirmados y contactos disponibles.

Se conserva siempre el original de la bandeja. Se reutiliza un documento coincidente
con el mismo candidato, hash y tipo, o se crea una copia privada mediante el modelo
de documentos existente; la extracción ordinaria ocurre solamente en esa resolución.
Una limitación de extracción no impide conservar el archivo. Los principales
existentes no se sustituyen ni se desactivan documentos. Las claves de procedencia
se validan sin sobrescribir destinos anteriores. Hashes asociados a otra ficha o
contenido distinto para una clave existente bloquean la resolución.

Las evaluaciones no se reciben ni se resuelven por esta bandeja. Tampoco se permite
reclasificar por este flujo un archivo ya registrado como evaluación.

Las escrituras son transaccionales, con `full_clean()` y un bloqueo por organización
para serializar las operaciones de la bandeja. Una copia documental creada se
retira si falla la operación; nunca se elimina el original de la entrada. Resolver
una entrada ya resuelta con el mismo destino no crea registros ni revisiones extra.

## Permisos y despliegue

La consulta requiere usuario staff, permiso `view_entradapendiente` y membresía
activa en la organización; colaboradores autorizados pueden consultar.
Crear/editar/resolver requiere administrador o supervisor y los permisos de modelo
correspondientes. Resolver exige además permisos para candidato/documento y ambas
procedencias según la operación. El superusuario conserva el alcance global, pero
no permite recibir evaluaciones por este flujo. No se asignan permisos nuevos
a grupos existentes automáticamente.

Los originales se guardan en `RADAR_MEDIA_ROOT/entradas/organizacion_ID/` usando
nombres UUID, permisos de archivo 0600 y directorio 0700. No tienen URL de storage
pública: se descargan con autenticación y autorización, como adjuntos y sin caché.
El servidor de despliegue debe mantener MEDIA_ROOT fuera del servicio público.

La migración `0019_entradas_pendientes` crea exclusivamente los modelos y su
restricción de unicidad. Debe revisarse y aplicarse en cada despliegue; los permisos
se asignan explícitamente cuando corresponda. No incluye cargas iniciales,
documentos, datos personales ni configuración de una instancia concreta.

## Importación por lotes y revisión posterior

`importar_cvs carpeta manifiesto.json` sigue siendo solo previsualización; la
escritura requiere `--importar`. No llama a OCR, servicios externos ni mensajería.
Una fila clara conserva el formato anterior. Para recibir una excepción sin crear
un candidato, declare `pendiente` y la clasificación de cada documento:

```json
{
  "organizacion": "organizacion-sintetica",
  "usuario_ejecutor": "gestor-sintetico",
  "registros": [{
    "id_fila": "recepcion-1",
    "origen_importacion": "fuente-sintetica",
    "identificador_origen": "recepcion-1",
    "contexto_recepcion": {"asunto": "Postulación", "fecha": "fecha explícita"},
    "pendiente": {
      "motivo": "CV sin nombre corroborado",
      "fuente": "Resumen de recepción y encabezado del CV, página 1",
      "datos": {
        "nombre": "Nombre propuesto",
        "telefono": "123456789",
        "telefono_estado": "no_confirmado",
        "seguimiento": "pendiente"
      }
    },
    "documentos": [{
      "identificador_origen": "CV_001.pdf",
      "archivo": "recepcion-1/CV_001.pdf",
      "tipo": "curriculum"
    }]
  }]
}
```

El motivo admite hasta 300 caracteres. `datos` acepta los campos revisables de la
bandeja; recibir una fila no confirma identidad, profesión ni ubicación, incluso
si el manifiesto las declara confirmadas. Los contactos disponibles requieren una
fuente explícita y se rechazan correos genéricos de portales como personales.
El nombre puede quedar vacío sin cambiar un CV a `otro`. Profesión, contacto y
ubicación ausentes no excluyen una fila clara identificada.

Un documento sin `tipo` se conserva como `otro`, con clasificación sin confirmar,
en la bandeja protegida. Esto también ocurre con adjuntos sin clasificar dentro
de filas claras: sus documentos clasificados siguen el flujo normal. El contexto
puede contener `candidato_contexto_id`, validado en la misma organización: conserva
el contexto del remitente, **no vincula el archivo ni acredita titularidad**.
El importador conserva una referencia estable a la procedencia de la fila como
contexto cuando separa un adjunto sin clasificar, exista ya la ficha o se cree
después en el flujo claro. El contexto original es inmutable.

Las entradas sin clasificación solo son visibles para administradores y
supervisores de su organización (y superusuarios); no para colaboradores. Se
admiten PDF, DOC, DOCX, PNG, JPG, JPEG y TXT de hasta 10 MB como originales
privados. Los formatos adicionales solo se conservan para revisión, no se resuelven
hacia documentos de candidato. Las evaluaciones explícitas y los hashes ya
registrados como evaluación se rechazan; no se reclasifican por este flujo.
Un archivo desconocido no se analiza automáticamente para descartar evaluaciones:
la revisión humana es obligatoria antes de confirmar clasificación y resolver.

Cada documento pendiente se recibe en una transacción independiente usando los
servicios de la bandeja. Un error no impide conservar los otros documentos. La
previsualización incluye un balance de todos los documentos: listos, pendientes,
existentes y conflictos (incluidos inválidos o faltantes). La repetición de la
misma clave organización/fuente/procedencia/clave documental y contenido no crea
otra entrada ni revisión, ni sobrescribe una revisión manual posterior. Otro
contenido o contexto para esa clave es un conflicto. Un mismo hash en dos
recepciones distintas conserva ambas, sin fusionar identidades. Una fila clara
que encuentra un archivo en bandeja debe usar la resolución segura; no la evita
creando directamente un candidato.

Desde **Revisar y completar** se descarga el original privado y se corrigen datos,
clasificación y motivo con fuente obligatoria. Cada revisión registra usuario,
fecha, instantánea y diferencias. Después se usa **Resolver: crear o vincular**,
que exige identidad y clasificación confirmadas, comprueba duplicados y permisos
y nunca rellena ni sobrescribe silenciosamente una ficha existente. El original
no se modifica.

La migración `0020_recepcion_pendiente_contexto` añade motivo y contexto de recepción
y amplía los formatos conservables. Debe aplicarse en el despliegue antes de usar
esta versión; no procesa lotes ni añade registros de candidatos o entradas.
