# Asistente Make (prototipo seguro)

Valida planes JSON y blueprints exportados de Make sin acceder a cuentas ni consumir sesiones Work para revisión estructural. No ejecuta escenarios, no gestiona secretos y no sustituye pruebas reales.

Uso:
```bash
python tools/make_assistant/validate.py plan tools/make_assistant/example_plan.json
python tools/make_assistant/validate.py blueprint exportado_make.json
python -m unittest discover -s tools/make_assistant -p 'test_*.py'
```

Próxima etapa: adaptar el validador a blueprints reales de C-Level, detectar referencias y conexiones faltantes, y evaluar integración API con permisos mínimos. No publicar ni activar escenarios sin autorización específica.
