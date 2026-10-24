"""Offline read-only Make blueprint inspector."""
import json
import sys
from pathlib import Path

def inspect_blueprint(data):
    errors, warnings, ids, modules = [], [], set(), []
    if not isinstance(data, dict) or not isinstance(data.get("flow"), list):
        return {"valid": False, "errors": ["Missing flow list"], "warnings": [], "modules": []}
    def walk(flow, path="flow"):
        if not isinstance(flow, list):
            errors.append(f"{path} is not a list")
            return
        for index, item in enumerate(flow):
            loc = f"{path}[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{loc} is not an object")
                continue
            mid = item.get("id")
            if mid is None:
                warnings.append(f"{loc} missing id")
            elif mid in ids:
                errors.append(f"{loc} duplicate id {mid}")
            else:
                ids.add(mid)
            kind = item.get("module")
            if not isinstance(kind, str) or not kind.strip():
                errors.append(f"{loc} missing module")
            modules.append({"id": mid, "type": kind})
            if "routes" in item:
                routes = item["routes"]
                if not isinstance(routes, list):
                    errors.append(f"{loc}.routes is not a list")
                else:
                    for j, route in enumerate(routes):
                        if not isinstance(route, dict):
                            errors.append(f"{loc}.routes[{j}] invalid")
                        else:
                            walk(route.get("flow"), f"{loc}.routes[{j}].flow")
    walk(data["flow"])
    if not modules:
        errors.append("Empty flow")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "modules": modules}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python make_inspector.py blueprint.json")
    try:
        result = inspect_blueprint(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not inspect blueprint: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["valid"] else 1)
