"""Converte um workflow do ComfyUI do formato VISUAL (nodes/links) para o formato API.

Uso: python scripts/convert_workflow.py "videos do papotechcast.json" [URL_COMFY] > papotechcast_api.json

A ordem dos widgets vem do /object_info do servidor; valores de widgets ligados a um link são
descartados (o link vence), e o valor extra de `control_after_generate` (seed) é pulado.
Se você tiver o export "API" original do ComfyUI, pode usá-lo no lugar deste (STUDIO_COMFY_WORKFLOW_PATH).
"""

import json
import sys
import urllib.request

WIDGET_PRIMITIVES = {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}


def widget_names(info: dict) -> list[tuple[str, bool]]:
    """[(nome, tem_control_after_generate)] dos inputs que são widgets, na ordem do node."""
    names = []
    for section in ("required", "optional"):
        for name, spec in (info["input"].get(section) or {}).items():
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if opts.get("forceInput"):  # só aceita link, não gera widget
                continue
            if isinstance(kind, list) or kind in WIDGET_PRIMITIVES:  # lista = COMBO
                names.append((name, bool(opts.get("control_after_generate")) or name == "seed"))
    return names


def convert(visual: dict, object_info: dict) -> dict:
    links = {link[0]: link for link in visual["links"]}
    api: dict[str, dict] = {}
    for node in visual["nodes"]:
        cls = node["type"]
        if cls not in object_info:
            print(f"  ignorando nó sem classe no servidor: {cls}", file=sys.stderr)
            continue
        if node.get("mode", 0) in (2, 4):
            print(f"  aviso: nó {node['id']} ({cls}) está mudo/bypass no workflow", file=sys.stderr)
        inputs: dict = {}
        linked = set()
        for slot in node.get("inputs", []):
            if slot.get("link") is not None:
                _, origin, origin_slot, *_ = links[slot["link"]]
                inputs[slot["name"]] = [str(origin), origin_slot]
                linked.add(slot["name"])
        values = list(node.get("widgets_values") or [])
        for name, has_control in widget_names(object_info[cls]):
            if not values:
                break
            value = values.pop(0)
            if has_control and values and isinstance(values[0], str) and values[0] in ("fixed", "increment", "decrement", "randomize"):
                values.pop(0)
            if name not in linked and value is not None:
                inputs[name] = value
        api[str(node["id"])] = {"class_type": cls, "inputs": inputs, "_meta": {"title": node.get("title") or cls}}
    missing = [
        (nid, name)
        for nid, n in api.items()
        for name in (object_info[n["class_type"]]["input"].get("required") or {})
        if name not in n["inputs"]
    ]
    if missing:
        raise SystemExit(f"inputs obrigatórios sem valor: {missing}")
    return api


def main() -> None:
    path = sys.argv[1]
    base = (sys.argv[2] if len(sys.argv) > 2 else "http://rises:8188").rstrip("/")
    visual = json.load(open(path, encoding="utf-8"))
    info = {}
    for cls in {n["type"] for n in visual["nodes"]}:
        with urllib.request.urlopen(f"{base}/object_info/{cls}", timeout=15) as r:
            info.update(json.load(r))
    json.dump(convert(visual, info), sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
