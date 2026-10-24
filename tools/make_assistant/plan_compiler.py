"""Compile a constrained declarative automation plan into a draft Make blueprint.
No live API calls, no credentials, and no deployment.
"""
import json

SUPPORTED = {
    "webhook": "gateway:CustomWebHook",
    "google_sheets_add_row": "google-sheets:addRow",
    "email_notify": "email:ActionSendEmail",
}
class PlanError(ValueError): pass

def compile_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("name"), str) or not plan["name"].strip():
        raise PlanError("Plan requires a name")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PlanError("Plan requires nonempty steps")
    flow = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("action") not in SUPPORTED:
            raise PlanError(f"Unsupported action at step {index}")
        # Intentionally exclude connection IDs, mappings and live webhook IDs.
        flow.append({"id": index, "module": SUPPORTED[step["action"]], "version": 1,
                     "metadata": {"designer": {"x": index * 240, "y": 0}}})
    return {"name": plan["name"], "flow": flow,
            "_draft": {"requires_manual_mapping": True, "not_import_ready": True}}

def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("output")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    result = compile_plan(plan)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
