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
