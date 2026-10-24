"""Static checks for Make blueprints, with no external effects."""
from make_inspector import inspect_blueprint

def diagnose(data):
    report = inspect_blueprint(data)
    findings = [{"severity": "error", "message": e} for e in report["errors"]]
    findings.extend({"severity": "warning", "message": w} for w in report["warnings"])
    module_types = [m["type"] or "" for m in report["modules"]]
    if not any("error" in m.lower() or "handler" in m.lower() for m in module_types):
        findings.append({"severity": "advisory", "message": "Review error handling in Make; not verified by static scan"})
    return {"valid_structure": report["valid"], "module_count": len(module_types), "findings": findings}
