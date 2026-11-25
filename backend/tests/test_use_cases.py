import pytest

from studio.conversation.application.use_cases import OpenConversation, SendMessage, build_prompt
from studio.conversation.domain.conversation import Conversation, Role
from studio.discovery.application.use_cases import GetNewsSearch, StartNewsSearch
from studio.scripting.application.use_cases import RetryBroll, ScriptWorkflow, StartScriptGeneration
from studio.shared.application.ports import AgentError
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus
from tests.fakes import (
    FakeAgents,
    FakeGuidelines,
    FakeStudio,
    InlineRunner,
    MemoryConversationRepo,
    MemoryNewsReader,
    MemoryNewsRepo,
    MemoryScriptRepo,
)

NEWS_JSON = '{"news":[{"title":"Quest 3S em promoção","summary":"Preço caiu.","details":"US$ 297."}]}'
SCRIPT_JSON = '{"title":"Quest em oferta","paragraphs":["Abertura.","Desenvolvimento."]}'
BROLL_JSON = '{"scenes":[{"paragraph":1,"url":"https://youtu.be/dQw4w9WgXcQ?t=5","description":"headset"}]}'


async def _search_with_item(agents, runner, repo):
    search = await StartNewsSearch(repo, agents, runner, FakeGuidelines())("Meta Quest")
    await runner.drain()
    return await GetNewsSearch(repo)(search.id)


async def test_news_search_success():
    repo, runner = MemoryNewsRepo(), InlineRunner()
    agents = FakeAgents({Bot.TONTON: NEWS_JSON})
    started = await StartNewsSearch(repo, agents, runner, FakeGuidelines())("  Meta   Quest ")
    assert started.status is JobStatus.RUNNING and started.topic == "Meta Quest"
    await runner.drain()
    done = await GetNewsSearch(repo)(started.id)
    assert done.status is JobStatus.DONE and done.items[0].title == "Quest 3S em promoção"
    assert "Meta Quest" in agents.calls[0][1]


async def test_news_search_agent_failure_is_recorded():
    repo, runner = MemoryNewsRepo(), InlineRunner()
    agents = FakeAgents({Bot.TONTON: AgentError("tonton fora do ar")})
    search = await StartNewsSearch(repo, agents, runner, FakeGuidelines())("x")
    await runner.drain()
    assert (await repo.get(search.id)).status is JobStatus.FAILED
    assert "fora do ar" in (await repo.get(search.id)).error


async def test_news_search_rejects_blank_topic():
    with pytest.raises(InvalidInput):
        await StartNewsSearch(MemoryNewsRepo(), FakeAgents({}), InlineRunner(), FakeGuidelines())("   ")


def _scripting(agents):
    news_repo, runner = MemoryNewsRepo(), InlineRunner()
    script_repo = MemoryScriptRepo()
    wf = ScriptWorkflow(script_repo, MemoryNewsReader(news_repo), agents, runner, FakeGuidelines())
    return news_repo, script_repo, runner, wf


async def test_script_then_broll_pipeline():
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: BROLL_JSON})
    news_repo, script_repo, runner, wf = _scripting(agents)
    search = await _search_with_item(agents, runner, news_repo)
    item = search.items[0]

    script = await StartScriptGeneration(wf)(item.id)
    assert script.status is JobStatus.RUNNING
    await runner.drain()

    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.DONE and saved.broll_status is JobStatus.DONE
    assert [p.text for p in saved.paragraphs] == ["Abertura.", "Desenvolvimento."]
    assert saved.paragraphs[0].broll == [] and saved.paragraphs[1].broll[0].video_id == "dQw4w9WgXcQ"
    jules_prompt = next(p for b, p in agents.calls if b is Bot.JULESVERNE)
    assert "US$ 297." in jules_prompt  # o material pesquisado pelo Tonton chega ao redator

    # idempotente: segunda chamada devolve o mesmo roteiro; force cria outro
    assert (await StartScriptGeneration(wf)(item.id)).id == script.id
    assert (await StartScriptGeneration(wf)(item.id, force=True)).id != script.id


async def test_broll_failure_keeps_script_and_can_be_retried():
    agents = FakeAgents(
        {Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: AgentError("youtube bloqueou")}
    )
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id)
    await runner.drain()

    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.DONE and saved.broll_status is JobStatus.FAILED
    assert saved.broll_error == "youtube bloqueou"

    agents.replies[Bot.LUMIERE] = BROLL_JSON
    await RetryBroll(wf)(script.id)
    await runner.drain()
    assert (await script_repo.get(script.id)).broll_status is JobStatus.DONE


async def test_script_failure_skips_broll():
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: "não sei", Bot.LUMIERE: BROLL_JSON})
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id)
    await runner.drain()
    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.FAILED and saved.broll_status is JobStatus.PENDING
    assert all(b is not Bot.LUMIERE for b, _ in agents.calls)
    with pytest.raises(Conflict):
        await RetryBroll(wf)(script.id)


async def test_script_for_unknown_news_item():
    _, _, _, wf = _scripting(FakeAgents({}))
    from uuid import uuid4

    with pytest.raises(NotFound):
        await StartScriptGeneration(wf)(uuid4())


async def test_chat_roundtrip_with_history():
    repo, runner = MemoryConversationRepo(), InlineRunner()
    agents = FakeAgents({Bot.BARU: "Olá, sou o Baru."})
    conversation = await OpenConversation(repo)(Bot.BARU)
    send = SendMessage(repo, agents, runner, FakeStudio())

    await send(conversation.id, "Quem é você?")
    with pytest.raises(Conflict):  # resposta ainda pendente
        await send(conversation.id, "outra")
    await runner.drain()
    assert conversation.messages[-1].content == "Olá, sou o Baru."
    assert conversation.title == "Quem é você?"

    agents.replies[Bot.BARU] = "Segunda resposta"
    await send(conversation.id, "E agora?")
    await runner.drain()
    second_prompt = agents.calls[-1][1]
    assert "Usuário: Quem é você?" in second_prompt and "Você: Olá, sou o Baru." in second_prompt
    assert second_prompt.rstrip().endswith("E agora?")


async def test_chat_failure_is_recorded_and_unblocks():
    repo, runner = MemoryConversationRepo(), InlineRunner()
    agents = FakeAgents({Bot.TONTON: AgentError("timeout")})
    conversation = await OpenConversation(repo)(Bot.TONTON)
    await SendMessage(repo, agents, runner, FakeStudio())(conversation.id, "oi")
    await runner.drain()
    assert conversation.messages[-1].status is JobStatus.FAILED and not conversation.has_pending_reply


async def test_lumiere_chat_roundtrip_and_command_protocol():
    repo, runner = MemoryConversationRepo(), InlineRunner()
    agents = FakeAgents({Bot.LUMIERE: 'Posso ajudar com os B-rolls.'})
    conversation = await OpenConversation(repo)(Bot.LUMIERE)
    await SendMessage(repo, agents, runner, FakeStudio())(conversation.id, 'Quero cenas com início confirmado')
    await runner.drain()
    assert agents.calls[-1][0] is Bot.LUMIERE
    assert 'rebuild_broll' in agents.calls[-1][1]
    assert 'save_guideline' in agents.calls[-1][1]
    assert conversation.messages[-1].content == 'Posso ajudar com os B-rolls.'
    assert conversation.messages[-1].status is JobStatus.DONE


def test_build_prompt_without_history_is_plain_message():
    assert build_prompt([], "oi") == "oi"
    assert Role.USER.value == "user"


async def test_broll_without_any_scene_is_reported_as_failure():
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: '{"scenes":[]}'})
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id)
    await runner.drain()
    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.DONE and saved.broll_status is JobStatus.FAILED
    assert "não encontrou" in saved.broll_error


async def test_broll_prompt_allows_scene_without_timestamp():
    from studio.scripting.application.prompts import broll_prompt

    assert "SEM" in broll_prompt("t", ["a"]) and "timestamp não confirmado" in broll_prompt("t", ["a"])


# ---- orientações, instruções e ações do chat ----
from studio.conversation.application.actions import ActionExecutor, parse_actions  # noqa: E402
from studio.conversation.application.ports import ScreenContext  # noqa: E402
from studio.guidance.application.use_cases import ActiveGuidelineTexts, AddGuideline, SetGuidelineActive  # noqa: E402
from studio.guidance.domain.guideline import Guideline  # noqa: E402
from studio.shared.domain.guidance import GuidelineScope  # noqa: E402


class MemoryGuidelineRepo:
    def __init__(self):
        self.data: dict = {}

    async def add(self, g):
        self.data[g.id] = g

    async def get(self, gid):
        return self.data.get(gid)

    async def set_active(self, gid, active):
        self.data[gid].active = active

    async def delete(self, gid):
        self.data.pop(gid, None)

    async def list_all(self):
        return list(self.data.values())

    async def find_duplicate(self, scope, text):
        return next((g for g in self.data.values() if g.scope == scope and g.text.lower() == text.lower()), None)


async def test_guidelines_are_scoped_deduplicated_and_toggleable():
    repo = MemoryGuidelineRepo()
    add, texts = AddGuideline(repo), ActiveGuidelineTexts(repo)
    first = await add(GuidelineScope.SCRIPT, "Use tom informal")
    assert (await add(GuidelineScope.SCRIPT, "use  tom informal")).id == first.id  # duplicada
    await add(GuidelineScope.ALL, "Sem emojis")
    await add(GuidelineScope.NEWS, "Só fontes em inglês")
    assert await texts.texts_for(GuidelineScope.SCRIPT) == ["Use tom informal", "Sem emojis"]
    await SetGuidelineActive(repo)(first.id, False)
    assert await texts.texts_for(GuidelineScope.SCRIPT) == ["Sem emojis"]


def test_guideline_rejects_blank():
    with pytest.raises(InvalidInput):
        Guideline.create(GuidelineScope.ALL, "   ", None)


async def test_guidelines_and_instructions_reach_the_prompts():
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: BROLL_JSON})
    news_repo, runner = MemoryNewsRepo(), InlineRunner()
    rules = FakeGuidelines({GuidelineScope.NEWS: ["Priorize fontes oficiais"], GuidelineScope.SCRIPT: ["Tom informal"]})
    await StartNewsSearch(news_repo, agents, runner, rules)("IA", "últimos 7 dias")
    await runner.drain()
    tonton_prompt = agents.calls[0][1]
    assert "Priorize fontes oficiais" in tonton_prompt and "últimos 7 dias" in tonton_prompt

    wf = ScriptWorkflow(MemoryScriptRepo(), MemoryNewsReader(news_repo), agents, runner, rules)
    item = (await news_repo.list_recent(1))[0].items[0]
    script = await StartScriptGeneration(wf)(item.id, instructions="seja bem curto")
    await runner.drain()
    jules_prompt = next(p for b, p in agents.calls if b is Bot.JULESVERNE)
    assert "Tom informal" in jules_prompt and "seja bem curto" in jules_prompt
    assert script.instructions == "seja bem curto"
    # pedido específico gera novo roteiro mesmo já existindo um
    again = await StartScriptGeneration(wf)(item.id, instructions="outro tom")
    assert again.id != script.id


def test_parse_actions_strips_blocks_and_ignores_garbage():
    reply = (
        'Certo, buscando!\n<acao>{"action":"search_news","topic":"IA"}</acao>\n'
        '<acao>{nao é json}</acao><acao>{"foo":1}</acao>'
    )
    text, actions = parse_actions(reply)
    assert text == "Certo, buscando!" and actions == [{"action": "search_news", "topic": "IA"}]


async def test_executor_validates_and_reports_failures():
    studio = FakeStudio()
    out = await ActionExecutor(studio).run(
        [
            {"action": "search_news", "topic": "IA", "instructions": "recentes"},
            {"action": "generate_script", "news_number": "2", "instructions": "curto"},
            {"action": "generate_script"},
            {"action": "save_guideline", "scope": "inventado", "text": "x"},
            {"action": "rm_rf"},
        ],
        ScreenContext(),
    )
    assert [o.status.value for o in out] == ["done", "done", "failed", "failed", "failed"]
    assert studio.calls == [("search_news", "IA", "recentes"), ("generate_script", 2, "curto")]


async def test_chat_executes_actions_requested_by_the_bot():
    repo, runner, studio = MemoryConversationRepo(), InlineRunner(), FakeStudio()
    reply = (
        'Vou buscar e guardar sua preferência.\n<acao>{"action":"search_news","topic":"Vision Pro"}</acao>\n'
        '<acao>{"action":"save_guideline","scope":"script","text":"Roteiros sempre informais"}</acao>'
    )
    agents = FakeAgents({Bot.BARU: reply})
    conversation = await OpenConversation(repo)(Bot.BARU)
    await SendMessage(repo, agents, runner, studio)(conversation.id, "busque Vision Pro e sempre use tom informal")
    await runner.drain()

    message = conversation.messages[-1]
    assert message.content == "Vou buscar e guardar sua preferência."  # blocos não aparecem para o usuário
    assert [a.type for a in message.actions] == ["search_news", "save_guideline"]
    assert message.actions[0].refs == {"search_id": "s1"}
    assert studio.calls == [("search_news", "Vision Pro", None), ("remember", "script", "Roteiros sempre informais")]
    prompt = agents.calls[0][1]
    assert "Notícia A" in prompt and "search_news" in prompt  # protocolo + estado da tela chegam ao bot


async def test_chat_with_only_an_action_gets_default_text():
    repo, runner = MemoryConversationRepo(), InlineRunner()
    agents = FakeAgents({Bot.TONTON: '<acao>{"action":"rebuild_broll"}</acao>'})
    conversation = await OpenConversation(repo)(Bot.TONTON)
    await SendMessage(repo, agents, runner, FakeStudio())(conversation.id, "refaça o b-roll")
    await runner.drain()
    assert conversation.messages[-1].content and conversation.messages[-1].actions[0].type == "rebuild_broll"


async def test_radar_coordinates_specialists_with_one_window_and_preserves_rank():
    from datetime import datetime, timezone
    from studio.discovery.application.use_cases import StartNewsSearch
    import json
    result = json.dumps({'news': [
        {'rank': 2, 'title': 'Segundo', 'summary': 'Sinal de comunidade', 'radar': {'ranking_reason': 'Uma fonte'}},
        {'rank': 1, 'title': 'Primeiro', 'summary': 'Sinal cruzado', 'radar': {'ranking_reason': 'Três fontes'}}],
        'google_trends_note': 'Indisponível: HTTP 429', 'discarded': ['Assunto fora da janela']})
    agents = FakeAgents({Bot.TONTON: result, Bot.YOUTOBA: '{"videos":[]}'})
    repo, runner = MemoryNewsRepo(), InlineRunner()
    end = datetime(2026,11,23,14,30,tzinfo=timezone.utc)
    search = await StartNewsSearch(repo,agents,runner,FakeGuidelines())('RADAR DE TENDÊNCIAS',window_end=end)
    await runner.drain()
    assert search.status is JobStatus.DONE
    assert [b for b,_ in agents.calls] == [Bot.TONTON,Bot.YOUTOBA,Bot.TONTON]
    assert all('2026-11-20T14:30:00+00:00' in prompt and '2026-11-23T14:30:00+00:00' in prompt for _,prompt in agents.calls)
    assert [i.title for i in search.items] == ['Primeiro','Segundo']
    assert search.report_context['scope'] == 'VR/XR'
    assert '429' in search.report_context['google_trends_note']
    assert search.report_context['discarded'] == ['Assunto fora da janela']


async def test_radar_does_not_claim_youtoba_results_when_unavailable():
    from studio.discovery.application.use_cases import StartNewsSearch
    result = '{"news":[{"rank":1,"title":"Sinal","summary":"Resumo","radar":{"ranking_reason":"Fonte única"}}]}'
    agents = FakeAgents({Bot.TONTON: result,Bot.YOUTOBA: AgentError('indisponível')})
    repo,runner = MemoryNewsRepo(),InlineRunner()
    search = await StartNewsSearch(repo,agents,runner,FakeGuidelines())('Radar')
    await runner.drain()
    assert search.status is JobStatus.DONE
    assert 'indisponível' in search.report_context['coverage']['youtoba']
    assert search.report_context['coverage_note'].startswith('Parcial')


# ---- cortes ----
from studio.scripting.application.use_cases import AddCut, DeleteCut  # noqa: E402


async def _script_with_paragraphs():
    agents = FakeAgents({Bot.TONTON: NEWS_JSON, Bot.JULESVERNE: SCRIPT_JSON, Bot.LUMIERE: BROLL_JSON})
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id)
    await runner.drain()
    return script_repo, await script_repo.get(script.id)


async def test_add_and_delete_cuts_with_validation():
    repo, script = await _script_with_paragraphs()
    para = script.paragraphs[1].id
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=99"
    updated = await AddCut(repo)(script.id, para, url, 65.04, 72.5, " Review ")
    cut = updated.cuts[0]
    assert (cut.video_url, cut.start_seconds, cut.end_seconds, cut.duration) == ("https://youtu.be/dQw4w9WgXcQ", 65.0, 72.5, 7.5)
    assert cut.video_title == "Review"

    for bad in [(10, 10), (10, 9), (10, 10.2), (-1, 5)]:
        with pytest.raises(InvalidInput):
            await AddCut(repo)(script.id, para, url, *bad)
    with pytest.raises(InvalidInput):
        await AddCut(repo)(script.id, para, "https://evil.com/x", 1, 5)
    with pytest.raises(Conflict):
        await AddCut(repo)(script.id, para, url, 65.0, 72.5)  # duplicado
    with pytest.raises(NotFound):
        from uuid import uuid4

        await AddCut(repo)(script.id, uuid4(), url, 1, 5)  # parágrafo de outro roteiro

    await AddCut(repo)(script.id, script.paragraphs[0].id, url, 1, 5)
    assert len(script.cuts) == 2
    after = await DeleteCut(repo)(script.id, cut.id)
    assert [c.start_seconds for c in after.cuts] == [1.0]
    with pytest.raises(NotFound):
        await DeleteCut(repo)(script.id, cut.id)


async def test_cut_linked_to_text_excerpt_blocks_overlaps():
    repo, script = await _script_with_paragraphs()
    para = script.paragraphs[1]  # "Desenvolvimento."
    url = "https://youtu.be/dQw4w9WgXcQ"
    updated = await AddCut(repo)(script.id, para.id, url, 1, 5, None, (0, 5))
    ex = updated.cuts[0].excerpt
    assert (ex.start, ex.end, ex.text, ex.paragraph_id) == (0, 5, "Desen", para.id)

    with pytest.raises(Conflict, match="outro corte"):  # sobrepõe 3..8 com 0..5
        await AddCut(repo)(script.id, para.id, url, 10, 15, None, (3, 8))
    await AddCut(repo)(script.id, para.id, url, 10, 15, None, (5, 9))  # adjacente (5..9) é permitido
    await AddCut(repo)(script.id, script.paragraphs[0].id, url, 1, 5, None, (0, 5))  # outro parágrafo: ok
    await AddCut(repo)(script.id, para.id, url, 20, 25)  # sem trecho: não conflita

    for bad in [(5, 5), (7, 3), (-1, 4), (0, 999)]:
        with pytest.raises(InvalidInput):
            await AddCut(repo)(script.id, para.id, url, 30, 35, None, bad)


from studio.scripting.application.use_cases import SetCutExcerpt  # noqa: E402


async def test_set_cut_excerpt_replaces_validates_and_clears():
    repo, script = await _script_with_paragraphs()
    para = script.paragraphs[1]  # "Desenvolvimento."
    url = "https://youtu.be/dQw4w9WgXcQ"
    first = (await AddCut(repo)(script.id, para.id, url, 1, 5, None, (0, 5))).cuts[-1]
    other = (await AddCut(repo)(script.id, para.id, url, 10, 15, None, (8, 12))).cuts[-1]
    nocut = (await AddCut(repo)(script.id, para.id, url, 20, 25)).cuts[-1]  # sem trecho

    set_excerpt = SetCutExcerpt(repo)
    updated = await set_excerpt(script.id, nocut.id, (5, 8))  # corte antigo ganha trecho
    assert next(c for c in updated.cuts if c.id == nocut.id).excerpt.text == "vol"
    await set_excerpt(script.id, first.id, (0, 4))  # encolhe o próprio trecho sem conflitar consigo mesmo
    with pytest.raises(Conflict):  # invade o trecho do outro corte
        await set_excerpt(script.id, first.id, (6, 10))
    with pytest.raises(InvalidInput):
        await set_excerpt(script.id, first.id, (0, 999))
    cleared = await set_excerpt(script.id, other.id, None)
    assert next(c for c in cleared.cuts if c.id == other.id).excerpt is None
    with pytest.raises(NotFound):
        from uuid import uuid4

        await set_excerpt(script.id, uuid4(), (0, 3))


from studio.scripting.application.use_cases import GetLatestScript  # noqa: E402


async def test_latest_script_follows_the_newest_one_and_never_creates():
    repo, script = await _script_with_paragraphs()
    latest = GetLatestScript(repo)
    assert (await latest(script.news_item_id)).id == script.id
    from uuid import uuid4

    assert await latest(uuid4()) is None
    from studio.scripting.domain.script import Script

    newer = Script.start(script.news_item_id)
    await repo.add(newer)
    assert (await latest(script.news_item_id)).id == newer.id
