# Make API — habilitación segura (pendiente)

Estado: cliente GET implementado, 15 pruebas locales aprobadas; **sin conexión real**. No existe credencial API disponible en este proyecto.

1. Obtener credencial desde la cuenta Make, con el alcance mínimo para consultar escenarios; guardar en un almacén de secretos del entorno ejecutor, nunca en GitHub ni en un chat.
2. Configurar MAKE_API_TOKEN y MAKE_API_HOST con el host regional correspondiente.
3. Probar GET para escenarios 4996755 (SEO) y 4996645 (comercial), primero sin cambios de estado.
4. Comparar resultados con los blueprints respaldados y generar informe sin datos personales ni secretos.
5. Solo después de verificar el alcance de permisos, decidir si habilitar acciones de escritura bajo aprobación específica.

No ejecutar activaciones, ediciones, ni publicar el sitio. La existencia del código no implica ejecución autónoma continua. Requiere un entorno de ejecución programado y credenciales seguras.
