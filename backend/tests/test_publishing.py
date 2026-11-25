import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from studio.infrastructure.persistence.publication_source import RenderPublicationSource
from studio.infrastructure.publishing.hermes_publisher import HermesYoutubePublisher, publish_prompt
from studio.publishing.application.parsing import parse_description, parse_title
from studio.publishing.application.ports import PublicationMaterial, PublishError, PublishRequest, PublishResult
from studio.publishing.application.prompts import description_prompt, title_prompt
from studio.publishing.application.use_cases import (
    EditPublication,
    PreparePublication,
    PublicationWorkflow,
    PublishToYoutube,
    RegeneratePublication,
    RevisePublication,
)
from studio.publishing.domain.publication import (
    DESCRIPTION_MAX,
    Link,
    Publication,
    PublicationStatus,
    compose_description,
    normalize_tags,
)
from studio.rendering.application.ports import OutputStream
from studio.rendering.application.use_cases import VideoSource
from studio.rendering.domain.render_job import RenderJob, RenderOutput
from studio.shared.application.ports import AgentError, AgentOutputError
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus
from tests.fakes import FakeAgents, FakeGuidelines, InlineRunner, MemoryNewsRepo, MemoryScriptRepo

JULES_OK = '{"description": "Gancho forte sobre o Quest 3S.\\n\\nResumo do vídeo."}'
YOUTOBA_OK = json.dumps({"title": "Quest 3S caiu abaixo de US$ 300: vale comprar?", "alternatives": ["Black Friday do Quest 3S", "Quest 3S: o melhor preço do ano"],
                         "tags": ["Meta Quest 3S", "#realidade virtual", "meta quest 3s", "Black Friday"], "rationale": "Pergunta + preço"})


def material(**over) -> PublicationMaterial:
    base = dict(script_id=uuid4(), topic="Meta Quest", script_title="Quest 3S em oferta", paragraphs=["Primeiro.", "Segundo."],
                news_title="Meta corta preço do Quest 3S", news_summary="Desconto de 15%.", news_details="US$ 296,99 até 30/11.",
                links=[Link("theverge.com", "https://theverge.com/a", "source"), Link("Review do Quest 3S", "https://youtu.be/abcdefghijk", "broll")])
    return PublicationMaterial(**{**base, **over})


class MemoryPubRepo:
    def __init__(self):
        self.data = {}

    async def add(self, p):
        self.data[p.id] = p

    async def save(self, p):
        self.data[p.id] = p

    async def get(self, i):
        return self.data.get(i)

    async def latest_for_render(self, rid):
        mine = [p for p in self.data.values() if p.render_id == rid]
        return max(mine, key=lambda p: p.created_at, default=None)

    async def fail_interrupted(self):
        return 0


class FakeSource:
    def __init__(self, m=None):
        self.m = m

    async def material(self, render_id):
        return self.m


class FakePublisher:
    def __init__(self, result="dQw4w9WgXcQ", error=None):
        self.requests, self.result, self.error = [], result, error

    async def publish(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return PublishResult(self.result)


def setup(m="default", replies=None, publisher=None):
    repo, runner = MemoryPubRepo(), InlineRunner()
    agents = FakeAgents({Bot.JULESVERNE: JULES_OK, Bot.YOUTOBA: YOUTOBA_OK, **(replies or {})})
    pub = publisher or FakePublisher()
    wf = PublicationWorkflow(repo, FakeSource(material() if m == "default" else m), agents, runner, pub, FakeGuidelines())
    return repo, runner, agents, pub, wf


# ---- domínio ----
def test_tags_and_title_rules():
    assert normalize_tags(["#Quest 3S", "quest 3s", " VR ", "", "a,b", "<x>"]) == ["Quest 3S", "VR", "a b", "x"]
    assert len(normalize_tags([f"tag{i}" for i in range(50)])) <= 20
    long = normalize_tags(["x" * 100] * 10)
    assert sum(len(t) + 1 for t in long) <= 450


def test_compose_description_adds_sources_and_credits_blocks():
    text = compose_description("Corpo.", material().links)
    assert text.startswith("Corpo.\n\nFontes:\n• theverge.com — https://theverge.com/a")
    assert "Vídeos usados nas cenas:\n• Review do Quest 3S — https://youtu.be/abcdefghijk" in text
    assert compose_description("Só corpo.", []) == "Só corpo."


def test_publication_lifecycle_rules():
    p = Publication.start(uuid4(), uuid4(), material().links)
    with pytest.raises(Conflict, match="gerado ou revisado"):
        p.edit(title="x")
    p.apply_generated("T" * 140, ["alt", "alt", "T" * 140], "Desc <b>negrito</b>", ["a"], None)
    assert p.status is PublicationStatus.READY and len(p.title) <= 100 and "<" not in p.description  # < e > removidos
    assert p.title_alternatives == ["alt"]

    p.edit(title="Novo título", privacy="unlisted", notify_subscribers=True)
    assert (p.title, p.privacy, p.notify_subscribers) == ("Novo título", "unlisted", True)
    for bad in ({"title": "  "}, {"title": "x" * 101}, {"privacy": "public"}, {"description": "y" * (DESCRIPTION_MAX + 1)}):
        with pytest.raises(InvalidInput):
            p.edit(**bad)
    assert p.title == "Novo título"  # edição recusada não altera nada

    p.begin_publish()
    assert p.status is PublicationStatus.PUBLISHING
    with pytest.raises(Conflict):
        p.begin_publish()  # não publica duas vezes
    with pytest.raises(Conflict):
        p.edit(title="outro")
    p.fail("recusou", "publish")
    assert p.status is PublicationStatus.READY and p.error_stage == "publish"  # volta a poder tentar, rascunho intacto
    p.begin_publish()
    with pytest.raises(InvalidInput):
        p.mark_published("curto")
    p.mark_published("dQw4w9WgXcQ")
    assert p.video_url == "https://youtu.be/dQw4w9WgXcQ" and p.status is PublicationStatus.PUBLISHED
    with pytest.raises(Conflict, match="já foi publicado"):
        p.begin_publish()


def test_generation_failure_is_terminal_but_revision_failure_keeps_the_draft():
    p = Publication.start(uuid4(), uuid4(), [])
    p.fail("sem resposta", "generation")
    assert p.status is PublicationStatus.FAILED
    with pytest.raises(Conflict, match="Gerar de novo"):
        p.edit(title="x")
    p.begin_generation()
    p.apply_generated("Título", [], "Descrição", [], None)
    p.begin_revision()
    p.fail("o bot caiu", "revision")
    assert p.status is PublicationStatus.READY and p.title == "Título" and p.error == "o bot caiu"


def test_publish_requires_title_and_description():
    p = Publication.start(uuid4(), uuid4(), [])
    p.apply_generated("Título", [], "Descrição", [], None)
    p.description = ""
    with pytest.raises(InvalidInput, match="descrição"):
        p.begin_publish()


# ---- parsing e prompts ----
def test_parsing_tolerates_chatter_and_rejects_empty():
    assert parse_description('Aqui está:\n```json\n{"description":"Texto"}\n```') == "Texto"
    title, alts, tags, why = parse_title(YOUTOBA_OK)
    assert title.startswith("Quest 3S") and len(alts) == 2 and "Black Friday" in tags and why == "Pergunta + preço"
    for bad in ('{"description": ""}', "sem json"):
        with pytest.raises(AgentOutputError):
            parse_description(bad)
    with pytest.raises(AgentOutputError):
        parse_title('{"title": ""}')


def test_prompts_carry_material_rules_and_forbid_links_in_description():
    d = description_prompt(material(), ["Tom informal"], "mais curta")
    assert "Meta corta preço do Quest 3S" in d and "Tom informal" in d and "mais curta" in d and "NÃO inclua links" in d
    assert "5,49%" in d and "FALADO" in d  # números em formato de leitura, não por extenso
    t = title_prompt(material(), "DESCRIÇÃO JÁ ESCRITA", None, "all")
    assert "DESCRIÇÃO JÁ ESCRITA" in t and "NUNCA mais de 100" in t and "UCq86_sw4NzNUDQ0j_FZRr8g" in t
    assert "SOMENTE o título" in title_prompt(material(), "d", "x", "title") and "SOMENTE as tags" in title_prompt(material(), "d", "x", "tags")


# ---- orquestração ----
async def test_generation_jules_writes_description_then_youtoba_makes_title():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    assert pub.status is PublicationStatus.DRAFTING and pub.links  # os links já vêm da notícia e das cenas
    await runner.drain()
    saved = await repo.get(pub.id)
    assert [b for b, _ in agents.calls] == [Bot.JULESVERNE, Bot.YOUTOBA]  # Jules primeiro; o Youtoba vê a descrição dele
    assert "Gancho forte sobre o Quest 3S." in agents.calls[1][1]
    assert saved.status is PublicationStatus.READY and saved.title.startswith("Quest 3S caiu")
    assert saved.tags == ["Meta Quest 3S", "realidade virtual", "Black Friday"]  # sem #, sem duplicata (maiúsc./minúsc.)
    assert saved.full_description.endswith("https://youtu.be/abcdefghijk")


async def test_prepare_is_idempotent_and_requires_a_finished_video():
    repo, runner, _, _, wf = setup()
    render = uuid4()
    first = await PreparePublication(wf)(render)
    again = await PreparePublication(wf)(render)
    assert again.id == first.id and len(repo.data) == 1
    assert (await PreparePublication(wf)(render, force=True)).id != first.id
    _, _, _, _, empty = setup(m=None)
    with pytest.raises(Conflict, match="ainda não está pronto"):
        await PreparePublication(empty)(uuid4())


async def test_generation_failures_are_recorded_with_the_reason():
    repo, runner, _, _, wf = setup(replies={Bot.YOUTOBA: AgentError("youtoba indisponível")})
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    assert (await repo.get(pub.id)).status is PublicationStatus.FAILED and "indisponível" in (await repo.get(pub.id)).error
    repo, runner, _, _, wf = setup(replies={Bot.JULESVERNE: "sem json nenhum"})
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    assert (await repo.get(pub.id)).status is PublicationStatus.FAILED
    # e dá para gerar de novo depois
    wf.agents.replies[Bot.JULESVERNE] = JULES_OK
    again = await RegeneratePublication(wf)(pub.id)
    await runner.drain()
    assert (await repo.get(again.id)).status is PublicationStatus.READY


async def test_revision_routes_each_field_to_the_right_specialist():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    before = await repo.get(pub.id)
    title0, desc0, tags0 = before.title, before.description, list(before.tags)
    agents.calls.clear()

    new_title = json.dumps({"title": "Título mais curto", "alternatives": ["Outro"], "tags": ["ignorada"], "rationale": "curto"})
    agents.replies[Bot.YOUTOBA] = new_title
    await RevisePublication(wf)(pub.id, "title", "deixe mais curto")
    assert (await repo.get(pub.id)).status is PublicationStatus.DRAFTING
    with pytest.raises(Conflict):  # enquanto revisam, não dá para editar nem publicar
        await EditPublication(repo)(pub.id, title="x")
    await runner.drain()
    after = await repo.get(pub.id)
    assert [b for b, _ in agents.calls] == [Bot.YOUTOBA]  # só o Youtoba
    assert (after.title, after.description, after.tags) == ("Título mais curto", desc0, tags0)  # tags e descrição intactas

    agents.calls.clear()
    agents.replies[Bot.JULESVERNE] = '{"description": "Descrição nova e curta."}'
    await RevisePublication(wf)(pub.id, "description", "mais curta")
    await runner.drain()
    assert [b for b, _ in agents.calls] == [Bot.JULESVERNE]
    assert (await repo.get(pub.id)).description == "Descrição nova e curta." and (await repo.get(pub.id)).title == "Título mais curto"

    agents.calls.clear()
    agents.replies[Bot.YOUTOBA] = json.dumps({"title": "x", "alternatives": [], "tags": ["Nova tag", "VR"]})
    await RevisePublication(wf)(pub.id, "tags", "mais tags de VR")
    await runner.drain()
    final = await repo.get(pub.id)
    assert final.tags == ["Nova tag", "VR"] and final.title == "Título mais curto"  # título preservado

    with pytest.raises(InvalidInput):
        await RevisePublication(wf)(pub.id, "tudo", "x")
    with pytest.raises(InvalidInput):
        await RevisePublication(wf)(pub.id, "title", "  ")


async def test_failed_revision_returns_to_ready_without_losing_the_draft():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    title = (await repo.get(pub.id)).title
    agents.replies[Bot.YOUTOBA] = AgentError("timeout")
    await RevisePublication(wf)(pub.id, "title", "outro")
    await runner.drain()
    saved = await repo.get(pub.id)
    assert saved.status is PublicationStatus.READY and saved.title == title and "timeout" in saved.error and saved.error_stage == "revision"


async def test_manual_edit_between_agent_calls_is_not_lost():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    assert await repo.get(pub.id)

    class Editing(FakeAgents):
        async def ask(self, bot, prompt):  # o editor mexe nas tags enquanto o Jules revisa a descrição
            p = await repo.get(pub.id)
            p.tags = ["tag do editor"]
            await repo.save(p)
            return await super().ask(bot, prompt)

    wf.agents = Editing({Bot.JULESVERNE: '{"description": "Descrição revisada"}'})
    p = await repo.get(pub.id)
    p.status = PublicationStatus.READY
    await RevisePublication(wf)(pub.id, "description", "x")
    await runner.drain()
    saved = await repo.get(pub.id)
    assert saved.description == "Descrição revisada" and saved.tags == ["tag do editor"]


# ---- publicação ----
async def test_publish_sends_exactly_what_the_summary_shows_and_records_the_video():
    publisher = FakePublisher("dQw4w9WgXcQ")
    repo, runner, _, _, wf = setup(publisher=publisher)
    render = uuid4()
    pub = await PreparePublication(wf)(render)
    await runner.drain()
    await EditPublication(repo)(pub.id, privacy="unlisted", tags=["VR", "Quest"])
    published = await PublishToYoutube(wf)(pub.id)
    assert published.status is PublicationStatus.PUBLISHING
    await runner.drain()
    saved = await repo.get(pub.id)
    assert saved.status is PublicationStatus.PUBLISHED and saved.video_url == "https://youtu.be/dQw4w9WgXcQ"
    sent = publisher.requests[0]
    assert (sent.render_id, sent.title, sent.privacy, sent.tags, sent.category_id, sent.language) == (render, saved.title, "unlisted", ["VR", "Quest"], "28", "pt")
    assert sent.description == saved.full_description and "Fontes:" in sent.description and sent.notify_subscribers is False
    with pytest.raises(Conflict):
        await PublishToYoutube(wf)(pub.id)  # já publicado


async def test_publish_failure_keeps_the_draft_and_allows_retry():
    publisher = FakePublisher(error=PublishError("A política do Hermes recusou"))
    repo, runner, _, _, wf = setup(publisher=publisher)
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    await PublishToYoutube(wf)(pub.id)
    await runner.drain()
    saved = await repo.get(pub.id)
    assert saved.status is PublicationStatus.READY and saved.error_stage == "publish" and "recusou" in saved.error
    publisher.error = None
    await PublishToYoutube(wf)(pub.id)
    await runner.drain()
    assert (await repo.get(pub.id)).status is PublicationStatus.PUBLISHED


async def test_cannot_publish_while_drafting_or_unknown():
    repo, runner, _, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    with pytest.raises(Conflict):  # ainda gerando
        await PublishToYoutube(wf)(pub.id)
    with pytest.raises(NotFound):
        await PublishToYoutube(wf)(uuid4())


# ---- HTTP: o botão "Publicar" exige confirmação explícita ----
def test_http_publish_requires_explicit_confirmation():
    from studio.interfaces.http.app import build_app

    calls = []

    async def publish(pid):
        calls.append(pid)
        p = Publication.start(uuid4(), uuid4(), [])
        p.apply_generated("T", [], "D", [], None)
        p.begin_publish()
        return p

    app = build_app(SimpleNamespace(publish_publication=publish), api_key=None, cors_origins=())
    client = TestClient(app)
    pid = uuid4()
    assert client.post(f"/api/publications/{pid}/publish", json={}).status_code == 422
    assert client.post(f"/api/publications/{pid}/publish", json={"confirm": False}).status_code == 422
    assert calls == []  # nada foi publicado
    ok = client.post(f"/api/publications/{pid}/publish", json={"confirm": True})
    assert ok.status_code == 202 and ok.json()["status"] == "publishing" and calls == [pid]


# ---- adaptador: entrega do arquivo e agente publicador ----
class LocalShell(HermesYoutubePublisher):
    """Executa os comandos "remotos" num shell local para exercitar a entrega do arquivo de verdade."""

    async def _ssh(self, command, stdin=False):
        return await asyncio.create_subprocess_exec(
            "bash", "-c", command, stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )


def request(render_id=None) -> PublishRequest:
    return PublishRequest(render_id or uuid4(), "Título", "Descrição\n\nFontes:\n• a — https://a.com", ["VR"], "28", "pt", "private", False)


PUB_OK = '{"published": true, "video_id": "dQw4w9WgXcQ", "privacy": "private", "error": null}'


async def test_publisher_delivers_file_runs_agent_and_cleans_up(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"MP4DATA" * 1000)
    shared = tmp_path / "shared" / "youtube"
    seen = {}

    class Agents(FakeAgents):
        async def ask(self, bot, prompt):
            seen["bot"], seen["prompt"], seen["existed"] = bot, prompt, [p.name for p in shared.iterdir()]
            seen["size"] = (shared / seen["existed"][0]).stat().st_size
            return PUB_OK

    async def open_video(render_id):
        return VideoSource(path=video)

    req = request()
    publisher = LocalShell(Agents({}), open_video, ssh_target="x", ssh_key=None, host_dir=str(shared), agent_dir="/opt/data/shared/youtube")
    result = await publisher.publish(req)
    assert result.video_id == "dQw4w9WgXcQ" and seen["bot"] is Bot.SNIPER
    assert seen["existed"] == [f"studio-{req.render_id}.mp4"] and seen["size"] == 7000  # o arquivo chegou inteiro antes do agente agir
    assert f"/opt/data/shared/youtube/studio-{req.render_id}.mp4" in seen["prompt"] and "yt_upload_video" in seen["prompt"]
    assert '"privacy_status": "private"' in seen["prompt"] and "CONFIRMOU" in seen["prompt"]
    assert list(shared.iterdir()) == []  # cópia temporária apagada


async def test_publisher_streams_video_from_comfyui_and_reports_refusals(tmp_path):
    shared = tmp_path / "yt"

    async def gen():
        for part in (b"abc", b"def"):
            yield part

    async def open_video(render_id):
        return VideoSource(stream=OutputStream(gen(), 6))

    refused = '{"published": false, "video_id": null, "error": "policy: privacy public not allowed"}'
    p = LocalShell(FakeAgents({Bot.SNIPER: refused}), open_video, ssh_target="x", ssh_key=None, host_dir=str(shared), agent_dir="/a")
    with pytest.raises(PublishError, match="privacy public not allowed"):
        await p.publish(request())
    assert list(shared.iterdir()) == []  # limpa mesmo quando recusado

    timeout = LocalShell(FakeAgents({Bot.SNIPER: AgentError("não respondeu em 1800s")}), open_video, ssh_target="x", ssh_key=None, host_dir=str(shared), agent_dir="/a")
    with pytest.raises(PublishError, match="Confira no YouTube Studio"):  # timeout: pode ter chegado ao canal
        await timeout.publish(request())

    for garbage in ("sem json", '{"published": true, "video_id": null}', '{"published": true}'):
        bad = LocalShell(FakeAgents({Bot.SNIPER: garbage}), open_video, ssh_target="x", ssh_key=None, host_dir=str(shared), agent_dir="/a")
        with pytest.raises(PublishError):
            await bad.publish(request())  # nunca dá por publicado sem um video_id real


async def test_publisher_requires_ssh_and_reports_delivery_failure(tmp_path):
    async def open_video(render_id):
        return VideoSource(path=tmp_path / "nao-existe.mp4")

    no_ssh = HermesYoutubePublisher(FakeAgents({}), open_video, ssh_target=None, ssh_key=None, host_dir="/x", agent_dir="/y")
    with pytest.raises(PublishError, match="STUDIO_HERMES_SSH"):
        await no_ssh.publish(request())

    async def broken(render_id):
        raise RuntimeError("arquivo sumiu")

    missing = LocalShell(FakeAgents({Bot.SNIPER: PUB_OK}), broken, ssh_target="x", ssh_key=None, host_dir=str(tmp_path / "d"), agent_dir="/y")
    with pytest.raises(PublishError, match="arquivo sumiu"):
        await missing.publish(request())


def test_publish_prompt_has_the_exact_parameters():
    req = request()
    prompt = publish_prompt(req, "/opt/data/shared/youtube/x.mp4")
    params = json.loads(prompt[prompt.index("{") : prompt.index("}\n\nSe a ferramenta") + 1])
    assert params == {"local_path": "/opt/data/shared/youtube/x.mp4", "title": "Título", "description": req.description, "tags": ["VR"],
                      "category_id": "28", "default_language": "pt", "privacy_status": "private", "notify_subscribers": False}


# ---- fonte do material ----
async def test_material_source_collects_sources_and_only_the_scenes_actually_cut():
    from studio.discovery.domain.news_search import NewsItem, NewsSearch
    from studio.scripting.domain.script import Script
    from tests.test_rendering import MemoryRenderRepo

    searches, scripts, renders = MemoryNewsRepo(), MemoryScriptRepo(), MemoryRenderRepo()
    search = NewsSearch.start("Meta Quest")
    item = NewsItem(uuid4(), 0, "Quest em oferta", "Resumo", "Fatos", "https://www.theverge.com/x",
                    radar={"sources": ["https://roadtovr.com/y", "https://www.theverge.com/x", "javascript:alert(1)"]})
    search.complete([item])
    await searches.add(search)
    script = Script.start(item.id)
    script.complete("Roteiro", ["Um.", "Dois."])
    p0 = script.paragraphs[0]
    script.add_cut(p0.id, "https://youtu.be/dQw4w9WgXcQ", 1, 5, " Review do Quest ")
    script.add_cut(p0.id, "https://youtu.be/dQw4w9WgXcQ", 10, 15)  # mesmo vídeo: um crédito só
    await scripts.add(script)
    job = RenderJob.create(script.id, "b", "r", "e")
    await renders.add(job)
    source = RenderPublicationSource(renders, scripts, searches)

    assert await source.material(job.id) is None  # ainda sem vídeo pronto
    assert await source.material(uuid4()) is None
    job.complete(RenderOutput("final.mp4", "papotechcast"))
    m = await source.material(job.id)
    assert (m.topic, m.news_title, m.script_title, m.paragraphs, m.video_name) == ("Meta Quest", "Quest em oferta", "Roteiro", ["Um.", "Dois."], "final.mp4")
    assert [(l.label, l.url, l.kind) for l in m.links] == [
        ("theverge.com", "https://www.theverge.com/x", "source"),
        ("roadtovr.com", "https://roadtovr.com/y", "source"),  # javascript: descartado; duplicata unida
        ("Review do Quest", "https://youtu.be/dQw4w9WgXcQ", "broll"),
    ]


# ---- chat: ajustes por prompt ----
from studio.conversation.application.actions import PROTOCOL, ActionExecutor, parse_actions, render_snapshot  # noqa: E402
from studio.conversation.application.ports import ScreenContext, ScreenSnapshot  # noqa: E402
from studio.conversation.application.use_cases import OpenConversation, SendMessage  # noqa: E402
from studio.infrastructure.studio_gateway import StudioUseCaseGateway  # noqa: E402
from tests.fakes import FakeStudio, MemoryConversationRepo  # noqa: E402


def test_chat_protocol_documents_publication_actions_and_never_publishes():
    assert "set_publication" in PROTOCOL and "revise_publication" in PROTOCOL
    assert "Você NUNCA publica no YouTube" in PROTOCOL and 'clicando em "Publicar"' in PROTOCOL
    text, actions = parse_actions('Ok.<acao>{"action":"publish_publication"}</acao>')  # não existe ação de publicar
    assert actions == [{"action": "publish_publication"}]


async def test_executor_routes_publication_actions_and_rejects_empty_or_unknown():
    studio = FakeStudio()
    ctx = ScreenContext(publication_id=uuid4())
    out = await ActionExecutor(studio).run(
        [
            {"action": "set_publication", "title": "Novo título", "tags": ["a"], "privacy": "unlisted", "extra": "ignorado"},
            {"action": "revise_publication", "target": "title", "instructions": "mais curto"},
            {"action": "revise_publication", "target": "description"},  # sem instruções
            {"action": "set_publication"},  # nenhum campo
            {"action": "publish_publication"},  # o chat não publica
        ],
        ctx,
    )
    assert [o.status.value for o in out] == ["done", "done", "failed", "failed", "failed"]
    assert studio.calls[0] == ("edit_publication", {"title": "Novo título", "tags": ["a"], "privacy": "unlisted"})
    assert studio.calls[1] == ("revise_publication", "title", "mais curto")


async def test_real_gateway_edits_and_revises_the_open_draft_and_shows_it_in_the_snapshot():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    noop = SimpleNamespace()
    gateway = StudioUseCaseGateway(noop, noop, noop, noop, noop, noop, EditPublication(repo), RevisePublication(wf), GetPublicationUC(repo))
    ctx = ScreenContext(publication_id=pub.id)

    snapshot = await gateway.snapshot(ctx)
    assert "RASCUNHO" not in (snapshot.publication or "") and "título (" in snapshot.publication and "estado: ready" in snapshot.publication
    assert "RASCUNHO DE PUBLICAÇÃO NO YOUTUBE" in render_snapshot(snapshot)  # o bot enxerga o rascunho

    outcome = await gateway.edit_publication(ctx, {"title": "Título ditado pelo usuário", "tags": ["x", "y"]})
    assert outcome.refs == {"publication_id": str(pub.id)} and "title, tags" in outcome.label
    saved = await repo.get(pub.id)
    assert (saved.title, saved.tags) == ("Título ditado pelo usuário", ["x", "y"])

    with pytest.raises(InvalidInput, match="rascunho de publicação aberto"):
        await gateway.edit_publication(ScreenContext(), {"title": "x"})
    with pytest.raises(InvalidInput):
        await gateway.edit_publication(ctx, {"privacy": "public"})  # a política recusa público

    revised = await gateway.revise_publication(ctx, "title", "gere outro título")
    assert "Youtoba" in revised.label and (await repo.get(pub.id)).status is PublicationStatus.DRAFTING


from studio.publishing.application.use_cases import GetPublication as GetPublicationUC  # noqa: E402


async def test_chat_message_with_open_draft_flows_through_sendmessage():
    repo, runner, agents, _, wf = setup()
    pub = await PreparePublication(wf)(uuid4())
    await runner.drain()
    chat_repo, chat_runner = MemoryConversationRepo(), InlineRunner()
    noop = SimpleNamespace()
    gateway = StudioUseCaseGateway(noop, noop, noop, noop, noop, noop, EditPublication(repo), RevisePublication(wf), GetPublicationUC(repo))
    reply = 'Troquei o título.\n<acao>{"action":"set_publication","title":"Título pelo chat"}</acao>'
    chat_agents = FakeAgents({Bot.BARU: reply})
    conversation = await OpenConversation(chat_repo)(Bot.BARU)
    await SendMessage(chat_repo, chat_agents, chat_runner, gateway)(conversation.id, "mude o título para Título pelo chat", ScreenContext(publication_id=pub.id))
    await chat_runner.drain()
    assert (await repo.get(pub.id)).title == "Título pelo chat"
    message = conversation.messages[-1]
    assert message.actions[0].type == "set_publication" and message.actions[0].refs["publication_id"] == str(pub.id)
    assert "RASCUNHO DE PUBLICAÇÃO NO YOUTUBE" in chat_agents.calls[0][1]  # o bot recebeu o rascunho atual no contexto
