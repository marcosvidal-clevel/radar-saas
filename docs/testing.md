# Ejecutar las pruebas de RADAR

La suite usa el ejecutor de Django y requiere una base PostgreSQL dedicada,
distinta de la base de desarrollo `radar`. Antes de ejecutar:

1. Crea un usuario PostgreSQL exclusivo para pruebas y usa una base de
   conexión administrativa/desarrollo de pruebas (por ejemplo `postgres`).
   El usuario necesita permiso para crear y eliminar la base `test_<nombre>`
   que Django usa durante la ejecución.
2. Copia `.env.test.example` a `.env.test`, reemplaza los valores de ejemplo y
   carga las variables en la terminal. No guardes contraseñas en Git:

   ```bash
   set -a
   source .env.test
   set +a
   ./scripts/test_suite.sh
   ```

El script selecciona `config.settings_test`, verifica que la base de conexión
no sea `radar`, que no se confunda con el nombre temporal `test_<nombre>` y que
host, puerto y credenciales no coincidan juntos con desarrollo. Django crea
una base aislada llamada `test_<RADAR_TEST_DB_NAME>` y la elimina al terminar.
`MEDIA_ROOT` se crea en un directorio temporal del sistema y se elimina al
terminar el proceso. No apunta a `media_privada`.

El ejecutor usa `TEST.NAME` explícitamente para que la base sobre la que aplica
migraciones y ejecuta pruebas sea `test_<RADAR_TEST_DB_NAME>`. No ejecutes
migraciones con los settings de desarrollo para preparar la base.

La suite incluye pruebas de migraciones. Estas se ejecutan dentro de la base
de pruebas y restauran el estado más reciente del esquema al terminar cada
caso.
