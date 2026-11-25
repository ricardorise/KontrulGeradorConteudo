import json
from uuid import uuid4

import httpx
import pytest

from studio.infrastructure.youtube.oembed import YoutubeOEmbed
from studio.scripting.application.prompts import broll_prompt
from studio.scripting.application.use_cases import AddBroll, RemoveBroll, ReplaceBroll, RetryBroll, StartScriptGeneration
from studio.scripting.domain.script import BrollSuggestion
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus
from tests.fakes import FakeAgents
from tests.test_use_cases import BROLL_JSON, NEWS_JSON, SCRIPT_JSON, _scripting, _search_with_item

OLD_ID, NEW_ID, OTHER_ID = "dQw4w9WgXcQ", "abcdefghijk", "zyxwvutsrqp"


class FakeTitles:
    def __init__(self, title="Review do Quest 3S"):
        self.title, self.calls = title, []

    async def title_of(self, video_id):
        self.calls.append(video_id)
        return self.title


async def make_script(replies=None):
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: BROLL_JSON, **(replies or {})})
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id)
    await runner.drain()
    return agents, script_repo, runner, wf, await script_repo.get(script.id)


# ---- domínio ----
def test_manual_broll_accepts_youtube_links_and_rejects_others():
    s = BrollSuggestion.manual("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95", "Título")
    assert (s.video_id, s.start_seconds, s.source, s.is_manual) == ("dQw4w9WgXcQ", 95, "manual", True)
    assert s.video_url == "https://youtu.be/dQw4w9WgXcQ?t=95" and s.title == "Título" and s.description == "Título"
    assert BrollSuggestion.manual("https://youtu.be/dQw4w9WgXcQ").start_seconds is None
    assert BrollSuggestion.manual("https://youtu.be/dQw4w9WgXcQ").description == "Vídeo escolhido por você"
    for bad in ("", "https://evil.com/watch?v=dQw4w9WgXcQ", "texto qualquer", "https://youtu.be/curto"):
        with pytest.raises(InvalidInput, match="link válido"):
            BrollSuggestion.manual(bad)


async def test_add_replace_remove_manual_broll_rules():
    _, repo, _, _, script = await make_script()
    p0, p1 = script.paragraphs
    titles = FakeTitles()
    updated = await AddBroll(repo, titles)(script.id, p0.id, f"https://youtu.be/{NEW_ID}?t=30")
    added = updated.paragraphs[0].broll[-1]
    assert (added.video_id, added.start_seconds, added.source, added.title) == (NEW_ID, 30, "manual", "Review do Quest 3S")
    assert titles.calls == [NEW_ID]

    with pytest.raises(Conflict, match="já está"):
        await AddBroll(repo, titles)(script.id, p0.id, f"https://youtu.be/{NEW_ID}?t=30")
    with pytest.raises(InvalidInput):
        await AddBroll(repo, titles)(script.id, p0.id, "não é link")
    with pytest.raises(NotFound):
        await AddBroll(repo, titles)(script.id, uuid4(), f"https://youtu.be/{OTHER_ID}")

    ai = p1.broll[0]  # a sugestão automática da Lumière
    swapped = await ReplaceBroll(repo, FakeTitles(None))(script.id, ai.id, f"https://youtu.be/{OTHER_ID}")
    now = next(b for b in swapped.paragraphs[1].broll if b.id == ai.id)  # mesmo id, mesmo lugar
    assert (now.video_id, now.source, now.title) == (OTHER_ID, "manual", None)
    with pytest.raises(NotFound):
        await ReplaceBroll(repo, FakeTitles())(script.id, uuid4(), f"https://youtu.be/{OTHER_ID}")

    after = await RemoveBroll(repo)(script.id, added.id)
    assert added.id not in [b.id for p in after.paragraphs for b in p.broll]
    with pytest.raises(NotFound):
        await RemoveBroll(repo)(script.id, added.id)


def test_complete_broll_keeps_manual_and_unchanged_paragraphs():
    from studio.scripting.domain.script import Script

    script = Script.start(uuid4())
    script.complete("t", ["a", "b", "c"])
    manual = BrollSuggestion.manual(f"https://youtu.be/{OTHER_ID}")
    old = BrollSuggestion.from_scene(f"https://youtu.be/{OLD_ID}", "antiga")
    script.paragraphs[0].broll = [old, manual]
    script.paragraphs[1].broll = [BrollSuggestion.from_scene(f"https://youtu.be/{OLD_ID}", "outra antiga")]
    script.paragraphs[2].broll = [BrollSuggestion.from_scene(f"https://youtu.be/{OLD_ID}", "terceira")]
    new = BrollSuggestion.from_scene(f"https://youtu.be/{NEW_ID}", "nova")

    targets = script.begin_broll({script.paragraphs[0].id, script.paragraphs[1].id})
    assert [p.position for p in targets] == [0, 1]
    assert script.paragraphs[0].broll[0] is old  # buscar não apaga nada
    script.complete_broll({0: [new]}, {0, 1})  # só o parágrafo 0 trouxe cena
    assert [b.description for b in script.paragraphs[0].broll] == ["Vídeo escolhido por você", "nova"]  # manual fica, antiga sai
    assert [b.description for b in script.paragraphs[1].broll] == ["outra antiga"]  # sem cena nova: mantém
    assert [b.description for b in script.paragraphs[2].broll] == ["terceira"]  # fora do alvo: intacto
    assert script.broll_status is JobStatus.DONE


async def test_begin_broll_validates_selection():
    _, _, _, _, script = await make_script()
    with pytest.raises(InvalidInput, match="ao menos um parágrafo"):
        script.begin_broll(set())
    with pytest.raises(InvalidInput):
        script.begin_broll({uuid4()})
    assert script.broll_status is not JobStatus.RUNNING  # nada mudou após as recusas
    script.begin_broll({script.paragraphs[0].id})
    with pytest.raises(Conflict, match="em andamento"):
        script.begin_broll()


# ---- busca seletiva pela Lumière ----
async def test_selective_search_sends_only_chosen_paragraphs_and_avoids_used_videos():
    agents, repo, runner, wf, script = await make_script()
    p0, p1 = script.paragraphs
    old_p1 = list(p1.broll)
    await AddBroll(repo, FakeTitles(None))(script.id, p0.id, f"https://youtu.be/{OTHER_ID}")
    agents.replies[Bot.LUMIERE] = json.dumps({"scenes": [
        {"paragraph": 0, "url": f"https://youtu.be/{NEW_ID}?t=12", "description": "cena nova"},
        {"paragraph": 1, "url": f"https://youtu.be/{NEW_ID}?t=99", "description": "NÃO era para buscar este"},
    ]})
    await RetryBroll(wf)(script.id, None, [p0.id])
    await runner.drain()

    prompt = next(p for b, p in reversed(agents.calls) if b is Bot.LUMIERE)
    assert "[0] Abertura." in prompt and "[1] Desenvolvimento." not in prompt  # só o parágrafo escolhido
    assert "SOMENTE para os parágrafos listados" in prompt
    assert f"https://youtu.be/{OLD_ID}" in prompt and f"https://youtu.be/{OTHER_ID}" in prompt  # vídeos a não repetir

    saved = await repo.get(script.id)
    assert saved.broll_status is JobStatus.DONE
    assert [b.video_id for b in saved.paragraphs[0].broll] == [OTHER_ID, NEW_ID]  # a escolhida fica, a nova entra
    assert saved.paragraphs[1].broll == old_p1  # o outro parágrafo ficou como estava
    assert saved.paragraphs[0].broll[0].is_manual and not saved.paragraphs[0].broll[1].is_manual


async def test_search_without_new_scenes_keeps_existing_ones_and_reports():
    agents, repo, runner, wf, script = await make_script()
    before = [[b.video_id for b in p.broll] for p in script.paragraphs]
    agents.replies[Bot.LUMIERE] = '{"scenes":[]}'
    await RetryBroll(wf)(script.id)
    await runner.drain()
    saved = await repo.get(script.id)
    assert saved.broll_status is JobStatus.FAILED and "mantidas" in saved.broll_error
    assert [[b.video_id for b in p.broll] for p in saved.paragraphs] == before  # nada foi perdido


async def test_manual_video_added_while_lumiere_searches_is_not_lost():
    agents, repo, runner, wf, script = await make_script()
    p0 = script.paragraphs[0]

    class SlowAgents(FakeAgents):
        async def ask(self, bot, prompt):
            if bot is Bot.LUMIERE:  # o editor insere um vídeo enquanto a Lumière pesquisa
                await AddBroll(repo, FakeTitles(None))(script.id, p0.id, f"https://youtu.be/{OTHER_ID}")
            return await super().ask(bot, prompt)

    wf.agents = SlowAgents({Bot.LUMIERE: json.dumps({"scenes": [{"paragraph": 0, "url": f"https://youtu.be/{NEW_ID}", "description": "nova"}]})})
    await RetryBroll(wf)(script.id, None, [p0.id])
    await runner.drain()
    saved = await repo.get(script.id)
    assert {b.video_id for b in saved.paragraphs[0].broll} == {OTHER_ID, NEW_ID}


# ---- prompt ----
def test_broll_prompt_subset_and_avoid_list():
    full = broll_prompt("T", ["a", "b"])
    assert "[0] a" in full and "[1] b" in full and "SOMENTE para os parágrafos listados" not in full and "NÃO repita" not in full
    subset = broll_prompt("T", ["c"], indexes=[4], avoid_video_ids=[OLD_ID])
    assert "[4] c" in subset and "SOMENTE para os parágrafos listados" in subset
    assert f"NÃO repita estes vídeos (já usados ou recusados pelo editor): https://youtu.be/{OLD_ID}" in subset


# ---- título do vídeo (oEmbed) ----
async def test_oembed_returns_title_and_tolerates_failures():
    seen = {}

    def ok(req: httpx.Request):
        seen["params"] = dict(req.url.params)
        return httpx.Response(200, json={"title": "  Meta Quest 3S Review  ", "author_name": "x"})

    assert await YoutubeOEmbed(transport=httpx.MockTransport(ok)).title_of(OLD_ID) == "Meta Quest 3S Review"
    assert seen["params"]["url"] == f"https://www.youtube.com/watch?v={OLD_ID}" and seen["params"]["format"] == "json"
    assert await YoutubeOEmbed(transport=httpx.MockTransport(lambda r: httpx.Response(404))).title_of(OLD_ID) is None

    def boom(req):
        raise httpx.ConnectError("sem rede")

    assert await YoutubeOEmbed(transport=httpx.MockTransport(boom)).title_of(OLD_ID) is None
    assert await YoutubeOEmbed(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"nao json"))).title_of(OLD_ID) is None
