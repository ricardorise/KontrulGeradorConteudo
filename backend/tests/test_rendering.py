import json
from uuid import uuid4

import httpx
import pytest

from studio.infrastructure.comfyui.renderer import DEFAULT_WORKFLOW, ComfyUiRenderer
from studio.rendering.application.ports import NarrationSettings
from studio.infrastructure.comfyui.workflow import default_narration, default_background, extract_video_output, fill_workflow
from studio.rendering.application.ports import OutputStream, RenderError, RenderProgress, RenderSubmission
from studio.rendering.application.use_cases import (
    OpenRenderVideo,
    PreviewRender,
    RenderMonitor,
    StartRender,
    resume_active,
)
from studio.rendering.domain.edit_plan import build_plan
from studio.rendering.domain.render_job import RenderJob, RenderOutput
from studio.rendering.domain.script_view import CutForRender, ScriptForRender
from studio.shared.domain.errors import InvalidInput
from studio.shared.domain.status import JobStatus
from tests.fakes import InlineRunner

TEMPLATE = json.loads(DEFAULT_WORKFLOW.read_text(encoding="utf-8"))
ROTEIRO = ["Abertura do vídeo sobre o Quest.", "O Quest 3S caiu de preço na Black Friday.", "Fechamento."]


def cut(par, text, start=326.4, end=349.2, vid="kwJ15olZCfI", at=0):
    return CutForRender(par, vid, start, end, text, at)


def script(*cuts):
    return ScriptForRender("t", ROTEIRO, list(cuts))


# ---- lista de edição ----
def test_plan_builds_lines_in_workflow_format():
    plan = build_plan(script(cut(2, "caiu de preço", at=11), cut(1, "Abertura do vídeo", start=0, end=6.2, at=0)))
    assert plan.problems == []
    assert plan.roteiro == "\n\n".join(ROTEIRO)
    assert plan.lines[0].render() == "https://www.youtube.com/watch?v=kwJ15olZCfI#t=0,7 | frase:Abertura do vídeo | 7"
    assert plan.edit_list.splitlines()[1] == (
        "https://www.youtube.com/watch?v=kwJ15olZCfI#t=326,350 | frase:caiu de preço | 24"
    )  # início arredonda p/ baixo, fim p/ cima


def test_plan_reports_missing_ambiguous_and_invalid_phrases():
    plan = build_plan(script(cut(1, None), cut(2, "Quest"), cut(2, "a|b"), cut(1, "o")))
    assert len(plan.problems) == 4 and plan.lines == []
    assert any("não tem trecho" in p for p in plan.problems)
    assert any("“Quest” aparece 3×" in p for p in plan.problems) or any("Quest" in p and "×" in p for p in plan.problems)
    assert any("“|”" in p for p in plan.problems)


def test_plan_requires_at_least_one_cut():
    assert "Não há cortes" in build_plan(script()).problems[0]


def test_phrase_matching_ignores_whitespace_differences():
    plan = ScriptForRender("t", ["Um  texto\ncom   quebras e espaços."], [cut(1, "texto com quebras")])
    assert build_plan(plan).problems == []


# ---- workflow ----
def test_fill_workflow_only_touches_script_background_and_edit_list():
    sub = RenderSubmission("ROTEIRO NOVO", "papotechcast/Outro.mp4", "https://x#t=1,2 | frase:a | 1")
    filled = fill_workflow(TEMPLATE, sub)
    assert filled["1"]["inputs"]["value"] == "ROTEIRO NOVO"
    assert filled["8"]["inputs"]["value"] == sub.edit_list
    assert filled["2"]["inputs"]["background"] == "papotechcast/Outro.mp4"
    changed = {(nid, k) for nid, n in filled.items() for k, v in n["inputs"].items() if TEMPLATE[nid]["inputs"].get(k) != v}
    assert changed == {("1", "value"), ("8", "value"), ("2", "background")}  # voz, render e YouTube intactos
    assert filled["3"]["inputs"]["provedor"] == "ElevenLabs" and filled["6"]["inputs"]["acao"] == "Preparar pacote (sem envio)"
    assert TEMPLATE["1"]["inputs"]["value"] != "ROTEIRO NOVO"  # template não é mutado
    assert default_background(TEMPLATE) == "papotechcast/Background2.mp4"


def test_fill_workflow_rejects_unexpected_graph():
    broken = {k: v for k, v in TEMPLATE.items() if v["class_type"] != "PapoYouTubeBrolls"}
    with pytest.raises(RenderError):
        fill_workflow(broken, RenderSubmission("r", "b", "e"))


@pytest.mark.parametrize(
    "outputs,expected",
    [
        ({"7": {"gifs": [{"filename": "ep.mp4", "subfolder": "papo", "type": "output"}]}}, RenderOutput("ep.mp4", "papo")),
        ({"6": {"text": ["/opt/comfy/output/papotechcast/final.mp4"]}}, RenderOutput("final.mp4", "papotechcast")),
        ({"6": {"resultado": ["{\"video\": \"papotechcast/x/final.mp4\", \"ok\": true}"]}}, RenderOutput("final.mp4", "papotechcast/x")),
        ({"6": {"text": ["pronto: ep.mp4"]}}, RenderOutput("ep.mp4", "")),
        ({"5": {"images": [{"filename": "a.png"}]}}, None),
    ],
)
def test_extract_video_output(outputs, expected):
    assert extract_video_output(outputs) == expected


# ---- casos de uso ----
class FakeRenderer:
    def __init__(self, progress=None, fail_submit=False):
        self.submitted, self.states, self.fail_submit = [], list(progress or []), fail_submit

    def default_background(self):
        return "papotechcast/Background2.mp4"

    def default_music_volume(self):
        return 0.08

    def supports_background_volume(self):
        return True

    def default_narration(self):
        return NarrationSettings()

    async def upload_input(self, path, subfolder, name):
        self.uploads = getattr(self, "uploads", []) + [(path.name, subfolder, name)]
        return f"{subfolder}/{name}"

    async def submit(self, s):
        if self.fail_submit:
            raise RenderError("ComfyUI indisponível")
        self.submitted.append(s)
        return "prompt-123"

    async def progress(self, prompt_id):
        item = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(item, Exception):
            raise item
        return item

    async def open_output(self, output):
        async def gen():
            yield b"mp4"

        return OutputStream(gen(), 3)


class MemoryRenderRepo:
    def __init__(self):
        self.data = {}

    async def add(self, j):
        self.data[j.id] = j

    async def save(self, j):
        self.data[j.id] = j

    async def get(self, i):
        return self.data.get(i)

    async def list_for_script(self, sid, limit):
        return [j for j in self.data.values() if j.script_id == sid]

    async def list_active(self):
        return [j for j in self.data.values() if not j.status.is_terminal]


class Source:
    def __init__(self, s):
        self.s = s

    async def get(self, _):
        return self.s


def _start(renderer, src):
    repo, runner = MemoryRenderRepo(), InlineRunner()
    monitor = RenderMonitor(repo, renderer, poll_interval_s=0)
    return repo, runner, monitor, StartRender(repo, PreviewRender(Source(src), renderer), renderer, runner, monitor)


async def test_start_render_submits_and_monitor_completes():
    out = RenderOutput("final.mp4", "papotechcast")
    renderer = FakeRenderer([RenderProgress("queued"), RenderProgress("running"), RenderProgress("done", out)])
    repo, runner, _, start = _start(renderer, script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4(), "papotechcast/Fundo.mp4")
    assert (job.status, job.prompt_id) == (JobStatus.RUNNING, "prompt-123")
    assert renderer.submitted[0].background == "papotechcast/Fundo.mp4"
    assert "frase:Abertura do vídeo" in renderer.submitted[0].edit_list
    await runner.drain()
    saved = repo.data[job.id]
    assert saved.status is JobStatus.DONE and saved.output == out and not saved.queued


async def test_start_render_blocks_when_plan_has_problems():
    renderer = FakeRenderer()
    _, _, _, start = _start(renderer, script(cut(1, None)))
    with pytest.raises(InvalidInput, match="não tem trecho"):
        await start(uuid4())
    assert renderer.submitted == []


async def test_submit_failure_is_recorded_not_raised():
    repo, _, _, start = _start(FakeRenderer(fail_submit=True), script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4())
    assert job.status is JobStatus.FAILED and "indisponível" in job.error and repo.data[job.id].error


async def test_monitor_reports_failure_and_tolerates_transient_errors():
    renderer = FakeRenderer([RenderError("rede"), RenderProgress("running"), RenderProgress("failed", error="boom")])
    repo, runner, _, start = _start(renderer, script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4())
    await runner.drain()
    assert repo.data[job.id].status is JobStatus.FAILED and repo.data[job.id].error == "boom"


async def test_monitor_gives_up_after_repeated_connection_errors():
    renderer = FakeRenderer([RenderError("rede")])
    repo, runner, _, start = _start(renderer, script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4())
    await runner.drain()
    assert repo.data[job.id].status is JobStatus.FAILED and "conexão" in repo.data[job.id].error


async def test_open_video_requires_finished_job_and_resume_active():
    renderer = FakeRenderer([RenderProgress("running")])
    repo, runner, monitor, start = _start(renderer, script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4())
    with pytest.raises(InvalidInput):
        await OpenRenderVideo(repo, renderer)(job.id)
    pending = RenderJob.create(uuid4(), "b", "r", "e")  # nunca chegou a ser enviado
    await repo.add(pending)
    runner.pending.clear()
    assert await resume_active(repo, runner, monitor) == 1
    assert repo.data[pending.id].status is JobStatus.FAILED
    job.complete(RenderOutput("f.mp4"))
    assert (await OpenRenderVideo(repo, renderer)(job.id)).stream.content_length == 3


# ---- adaptador ComfyUI (servidor simulado) ----
def _renderer(handler):
    return ComfyUiRenderer("http://comfy", transport=httpx.MockTransport(handler))


async def test_comfy_submit_posts_prompt_and_returns_prompt_id():
    seen = {}

    def handler(req: httpx.Request):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(200, json={"prompt_id": "abc", "number": 1})

    pid = await _renderer(handler).submit(RenderSubmission("R", "papotechcast/B.mp4", "L"))
    assert pid == "abc" and seen["path"] == "/prompt" and set(seen["body"]) == {"prompt"}
    assert seen["body"]["prompt"]["1"]["inputs"]["value"] == "R"


async def test_comfy_submit_explains_rejection():
    body = {"error": {"message": "Prompt outputs failed validation"},
            "node_errors": {"2": {"class_type": "PapoAssets", "errors": [{"message": "Value not in list", "details": "background"}]}}}
    with pytest.raises(RenderError, match="PapoAssets.*Value not in list"):
        await _renderer(lambda r: httpx.Response(400, json=body)).submit(RenderSubmission("R", "x", "L"))


async def test_comfy_progress_states_and_output():
    state = {"history": {}, "queue": {"queue_running": [], "queue_pending": []}}

    def handler(req):
        if req.url.path == "/history/abc":
            return httpx.Response(200, json=state["history"])
        return httpx.Response(200, json=state["queue"])

    r = _renderer(handler)
    assert (await r.progress("abc")).state == "lost"  # nem no histórico nem na fila
    state["queue"]["queue_pending"] = [[2, "abc", {}]]
    assert (await r.progress("abc")).state == "queued"
    state["queue"]["queue_running"] = [[1, "abc", {}]]
    assert (await r.progress("abc")).state == "running"
    state["history"] = {"abc": {"status": {"status_str": "success", "completed": True},
                                "outputs": {"6": {"text": ["/x/output/papotechcast/final.mp4"]}}}}
    done = await r.progress("abc")
    assert done.state == "done" and done.output == RenderOutput("final.mp4", "papotechcast")
    state["history"] = {"abc": {"status": {"status_str": "error", "completed": False,
                                           "messages": [["execution_error", {"node_id": "5", "node_type": "PapoRender", "exception_message": "sem GPU"}]]}}}
    failed = await r.progress("abc")
    assert failed.state == "failed" and "PapoRender" in failed.error and "sem GPU" in failed.error


async def test_comfy_view_streams_video_with_query_params():
    seen = {}

    def handler(req):
        seen["q"] = dict(req.url.params)
        return httpx.Response(200, content=b"0123456789")

    stream = await _renderer(handler).open_output(RenderOutput("final.mp4", "papotechcast"))
    data = b"".join([c async for c in stream.chunks])
    assert data == b"0123456789" and stream.content_length == 10
    assert seen["q"] == {"filename": "final.mp4", "subfolder": "papotechcast", "type": "output"}
    with pytest.raises(RenderError):
        await _renderer(lambda r: httpx.Response(404)).open_output(RenderOutput("x.mp4"))


async def test_monitor_fails_when_comfy_lost_the_prompt():
    renderer = FakeRenderer([RenderProgress("lost")])
    repo, runner, _, start = _start(renderer, script(cut(1, "Abertura do vídeo")))
    job = await start(uuid4())
    await runner.drain()
    assert repo.data[job.id].status is JobStatus.FAILED and "não tem mais este envio" in repo.data[job.id].error


def test_plan_blocks_phrases_with_digits_or_symbols():
    roteiro = ScriptForRender("t", ["O modelo de 128 GB cai de 349 pra menos de 50%.", "Fim."], [
        cut(1, "O modelo de 128 GB cai de 349"), cut(1, "menos de 50%", at=30), cut(2, "Fim.")])
    plan = build_plan(roteiro)
    assert len(plan.problems) == 2 and all("número ou símbolo" in p for p in plan.problems)
    assert [l.phrase for l in plan.lines] == ["Fim."]


def test_narration_settings_fill_only_voice_inputs_found_by_class_type():
    import copy
    import json
    from dataclasses import replace

    from studio.infrastructure.comfyui.renderer import DEFAULT_WORKFLOW

    template = json.loads(open(DEFAULT_WORKFLOW, encoding="utf-8").read())
    # renumerar o nó não pode quebrar: localizado por class_type
    renumbered = {("99" if n.get("class_type") == "PapoNarration" else k): n for k, n in copy.deepcopy(template).items()}
    for n in renumbered.values():
        for key, value in n["inputs"].items():
            if isinstance(value, list) and value[0] == next(k for k, v in template.items() if v["class_type"] == "PapoNarration"):
                n["inputs"][key] = ["99", value[1]]
    settings = replace(default_narration(template), voz_elevenlabs="", velocidade_elevenlabs=1.15, estilo_elevenlabs=0.5)
    filled = fill_workflow(renumbered, RenderSubmission("R", "b.mp4", "L", narration=settings))["99"]["inputs"]
    assert (filled["voz_elevenlabs"], filled["velocidade_elevenlabs"], filled["estilo_elevenlabs"]) == ("", 1.15, 0.5)
    original = renumbered["99"]["inputs"]
    for kept in ("roteiro", "arquivos", "voz_salva", "descricao_voz", "seed", "idioma"):
        assert filled[kept] == original[kept]  # demais inputs e conexões preservados
    untouched = fill_workflow(renumbered, RenderSubmission("R", "b.mp4", "L"))["99"]["inputs"]
    assert untouched["voz_elevenlabs"] == original["voz_elevenlabs"]  # sem narration, preserva a voz do workflow


def test_narration_limits_are_validated():
    assert NarrationSettings().problems() == []
    assert NarrationSettings(velocidade_elevenlabs=1.3).problems()
    assert NarrationSettings(velocidade_elevenlabs=0.69).problems()
    assert NarrationSettings(estilo_elevenlabs=1.01).problems()
    assert NarrationSettings(modelo_elevenlabs="x").problems()
    assert NarrationSettings(velocidade_elevenlabs=1.2, estabilidade_elevenlabs=0).problems() == []


def test_narration_http_bounds():
    from studio.interfaces.http.schemas import NarrationIO
    import pydantic

    assert NarrationIO().to_domain() == NarrationSettings()
    for bad in ({"velocidade_elevenlabs": 1.21}, {"estabilidade_elevenlabs": -0.01}, {"provedor": "Outro"}):
        with pytest.raises(pydantic.ValidationError):
            NarrationIO(**bad)
