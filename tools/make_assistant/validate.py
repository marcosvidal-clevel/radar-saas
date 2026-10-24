"""Validador local y sin efectos secundarios de diseños Make."""
import json
import sys
from pathlib import Path


def validate_plan(data):
    errors = []
    if not isinstance(data, dict):
        return ["El plan debe ser un objeto JSON"]
    for key in ("name", "steps"):
        if key not in data:
            errors.append(f"Falta campo: {key}")
    steps = data.get("steps", [])
    if not isinstance(steps, list) or not steps:
        errors.append("steps debe ser una lista no vacía")
    else:
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict) or not step.get("action"):
                errors.append(f"Paso {i}: falta action")
    return errors


def validate_blueprint(data):
    if not isinstance(data, dict):
        return ["Blueprint debe ser un objeto JSON"]
    flow = data.get("flow")
    if not isinstance(flow, list) or not flow:
        return ["Blueprint sin lista flow no vacía"]
    errors = []
    for i, module in enumerate(flow, 1):
        if not isinstance(module, dict):
            errors.append(f"Módulo {i}: formato inválido")
        elif not module.get("module"):
            errors.append(f"Módulo {i}: falta module")
    return errors


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 2 or argv[0] not in ("plan", "blueprint"):
        print("Uso: validate.py [plan|blueprint] archivo.json")
        return 2
    try:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    errors = validate_plan(data) if argv[0] == "plan" else validate_blueprint(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Estructura válida; no implica que el escenario funcione en Make.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
