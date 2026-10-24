"""Revisión estática de blueprints Make; nunca ejecuta ni publica escenarios."""
import json
import sys
from pathlib import Path

def validate_plan(data):
    if not isinstance(data, dict):
        return ["El plan debe ser un objeto JSON"]
    errors = []
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("Falta name")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps debe ser una lista no vacía")
    else:
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict) or not isinstance(step.get("action"), str) or not step["action"].strip():
                errors.append(f"Paso {i}: falta action")
    return errors

def validate_blueprint(data):
    if not isinstance(data, dict):
        return ["Blueprint debe ser un objeto JSON"]
    errors = []
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("Blueprint sin name")
    flow = data.get("flow")
    if not isinstance(flow, list) or not flow:
        return errors + ["Blueprint sin lista flow no vacía"]
    seen = set()
    def inspect(items, prefix=""):
        for i, module in enumerate(items, 1):
            where = f"{prefix}{i}"
            if not isinstance(module, dict):
                errors.append(f"Módulo {where}: formato inválido")
                continue
            if not isinstance(module.get("module"), str) or not module["module"].strip():
                errors.append(f"Módulo {where}: falta module")
            module_id = module.get("id")
            if module_id is not None:
                if module_id in seen:
                    errors.append(f"Módulo {where}: id duplicado {module_id}")
                seen.add(module_id)
            for route in module.get("routes", []):
                if isinstance(route, dict) and isinstance(route.get("flow"), list):
                    inspect(route["flow"], where + ".")
    inspect(flow)
    return errors

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("plan", "blueprint"):
        print("Uso: validate.py [plan|blueprint] archivo.json")
        return 2
    try:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    errors = validate_plan(data) if argv[0] == "plan" else validate_blueprint(data)
    for error in errors:
        print("ERROR:", error)
    if not errors:
        print("Estructura válida; conexiones, filtros y ejecución real NO verificados.")
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
