"""Preenchimento do workflow "videos do papotechcast" (formato API) e leitura da saída."""

import copy
import json
import re
from typing import Any

from dataclasses import asdict, fields

from studio.rendering.application.ports import NarrationSettings, RenderError, RenderSubmission
from studio.rendering.domain.render_job import RenderOutput

VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".mkv")
_PATH = re.compile(r"[^\s\"'\[\],]+\.(?:mp4|webm|mov|mkv)", re.IGNORECASE)


def _link(node: dict, name: str) -> str | None:
    value = node["inputs"].get(name)
    return str(value[0]) if isinstance(value, list) and value else None


def _single(workflow: dict, class_type: str) -> tuple[str, dict]:
    found = [(nid, n) for nid, n in workflow.items() if n.get("class_type") == class_type]
    if len(found) != 1:
        raise RenderError(f"O workflow deve ter exatamente um nó {class_type} (achei {len(found)}).")
    return found[0]


def fill_workflow(template: dict, submission: RenderSubmission) -> dict:
    """Preenche roteiro, background e lista de edição. Todo o resto (voz, render, YouTube) é preservado.

    Os nós são achados pela ligação entre eles, não por id/título, então renomear/renumerar não quebra.
    """
    workflow = copy.deepcopy(template)
    _, narration = _single(workflow, "PapoNarration")
    _, assets = _single(workflow, "PapoAssets")
    _, youtube_brolls = _single(workflow, "PapoYouTubeBrolls")

    if submission.narration:  # só as entradas de voz; roteiro, arquivos e demais conexões do nó ficam como estão
        narration["inputs"].update(asdict(submission.narration))
    script_id = _link(narration, "roteiro")
    edit_id = _link(youtube_brolls, "brolls_locais")
    if _link(assets, "brolls_timeline") is None or script_id is None or edit_id is None:
        raise RenderError("Workflow inesperado: faltam as ligações roteiro → narração e lista → B-rolls → assets.")
    workflow[script_id]["inputs"]["value"] = submission.roteiro
    workflow[edit_id]["inputs"]["value"] = submission.edit_list
    assets["inputs"]["background"] = submission.background
    if submission.background_volume is not None:
        _, render = _single(workflow, "PapoRender")
        if "volume_fundo" not in render["inputs"] and submission.background_volume > 0:
            raise RenderError("O workflow atual não tem o volume do áudio do background (volume_fundo).")
        if "volume_fundo" in render["inputs"] or submission.background_volume > 0:
            render["inputs"]["volume_fundo"] = submission.background_volume
    if submission.music:  # sem trilha escolhida, preserva o que o workflow já tem
        assets["inputs"]["trilha"] = submission.music
        if submission.music_volume is not None:
            _, render = _single(workflow, "PapoRender")
            render["inputs"]["volume_trilha"] = submission.music_volume
    return workflow


def default_narration(template: dict) -> NarrationSettings:
    """Valores atuais do nó PapoNarration (achado por class_type); o que faltar usa o padrão do nó."""
    _, node = _single(template, "PapoNarration")
    base = NarrationSettings()
    values = {}
    for f in fields(base):
        raw = node["inputs"].get(f.name)
        if raw is not None and not isinstance(raw, list):
            values[f.name] = type(getattr(base, f.name))(raw)
    return NarrationSettings(**values)


def default_background(template: dict) -> str:
    _, assets = _single(template, "PapoAssets")
    return str(assets["inputs"].get("background") or "")


def default_music_volume(template: dict) -> float:
    _, render = _single(template, "PapoRender")
    return float(render["inputs"].get("volume_trilha", 0.08))


def supports_background_volume(template: dict) -> bool:
    _, render = _single(template, "PapoRender")
    return "volume_fundo" in render["inputs"]


def _output_from_path(path: str) -> RenderOutput:
    clean = path.replace("\\", "/")
    if "/output/" in clean:
        clean = clean.rsplit("/output/", 1)[1]
    clean = clean.lstrip("/")
    subfolder, _, filename = clean.rpartition("/")
    return RenderOutput(filename=filename, subfolder=subfolder, type="output")


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        name = value.get("filename")
        if isinstance(name, str) and name.lower().endswith(VIDEO_EXTENSIONS):
            return  # já é um arquivo completo; não reler o nome como caminho solto
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    elif isinstance(value, str):
        yield value


def extract_video_output(outputs: dict[str, Any]) -> RenderOutput | None:
    """Acha o MP4 final na saída do workflow: objetos {filename, subfolder, type} ou caminhos em texto.

    Percorre os nós em ordem e fica com o último vídeo (o nó final do fluxo).
    """
    found: RenderOutput | None = None
    for node_output in outputs.values():
        for item in _walk(node_output):
            if isinstance(item, dict):
                name = item.get("filename")
                if isinstance(name, str) and name.lower().endswith(VIDEO_EXTENSIONS):
                    found = RenderOutput(name, str(item.get("subfolder") or ""), str(item.get("type") or "output"))
            else:
                for match in _PATH.findall(item):
                    found = _output_from_path(match)
                # resultado em JSON como texto, ex.: {"video": "papotechcast/final.mp4"}
                if item.lstrip().startswith(("{", "[")):
                    try:
                        nested = json.loads(item)
                    except ValueError:
                        continue
                    nested_found = extract_video_output({"_": nested})
                    found = nested_found or found
    return found
