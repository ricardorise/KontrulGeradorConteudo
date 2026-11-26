from uuid import uuid4

import pytest

from studio.scripting.application.parsing import parse_script_lines
from studio.scripting.application.prompts import script_prompt
from studio.scripting.application.use_cases import (
    AddScriptProfile,
    DeleteScriptProfile,
    ScriptConfigOptions,
    StartScriptGeneration,
)
from studio.scripting.domain.config import BUILTIN_PROFILES, DURATIONS, ScriptConfig, ScriptProfile
from studio.shared.domain.bots import Bot
from studio.shared.domain.errors import Conflict, InvalidInput, NotFound
from studio.shared.domain.status import JobStatus
from tests.fakes import FakeAgents, InlineRunner
from tests.test_use_cases import NEWS_JSON, _scripting, _search_with_item


class MemoryProfiles:
    def __init__(self):
        self.items: dict[str, ScriptProfile] = {}

    async def list_custom(self):
        return list(self.items.values())

    async def get(self, profile_id):
        return self.items.get(profile_id)

    async def add(self, profile):
        self.items[profile.id] = profile

    async def delete(self, profile_id):
        return self.items.pop(profile_id, None) is not None


class SequenceAgents(FakeAgents):
    """Devolve as respostas do Jules Verne em sequência (para testar o pedido de encurtar)."""

    def __init__(self, scripts, **other):
        super().__init__({Bot.TONTON: NEWS_JSON, Bot.LUMIERE: '{"scenes":[]}', **other})
        self.scripts = list(scripts)

    async def ask(self, bot, prompt):
        if bot is Bot.JULESVERNE:
            self.calls.append((bot, prompt))
            return self.scripts.pop(0)
        return await super().ask(bot, prompt)


def test_durations_and_four_basic_profiles():
    assert DURATIONS == {5: 630, 8: 800, 12: 1200, 20: 2000}
    assert [p.name for p in BUILTIN_PROFILES] == [
        "Jornalístico & Investigativo", "Storytelling & Curiosidades", "Tech & Analítico", "Opinião & Debate Construtivo",
    ]  # fmt: skip


def test_config_validation():
    tech = BUILTIN_PROFILES[2]
    cfg = ScriptConfig.build(tech, 8, ["  Ana ", "Beto"])
    assert (cfg.max_chars, cfg.presenters, cfg.is_dialogue, cfg.profile_name) == (800, ("Ana", "Beto"), True, "Tech & Analítico")
    assert not cfg.fits(900) and cfg.fits(840)  # tolerância de 5%
    assert ScriptConfig.build(None, None, []).is_empty
    assert ScriptConfig.build(None, None, ["Ana"]).is_dialogue is False
    for bad in (dict(duration_minutes=7), dict(presenters=["Ana", ""]), dict(presenters=["Ana", "ana"]), dict(presenters=["a", "b", "c"]), dict(presenters=["x" * 41])):
        with pytest.raises(InvalidInput):
            ScriptConfig.build(None, **bad)


def test_prompt_carries_profile_time_and_presenters():
    from studio.scripting.application.ports import NewsSource

    news = NewsSource(id=uuid4(), topic="VR", title="Quest", summary="s", details="d", source_url=None)
    cfg = ScriptConfig.build(BUILTIN_PROFILES[0], 5, ["Ana", "Beto"])
    prompt = script_prompt(news, [], None, cfg)
    assert "Jornalístico & Investigativo" in prompt and "NO MÁXIMO 630 caracteres" in prompt
    assert "Ana e Beto" in prompt and '"speaker"' in prompt and "6 e 10" not in prompt
    plain = script_prompt(news)
    assert "6 e 10" in plain and "CONFIGURAÇÃO" not in plain  # sem configuração, o comportamento antigo


def test_parse_two_presenters_assigns_and_alternates():
    cfg = ScriptConfig.build(None, None, ["Ana", "Beto"])
    raw = '{"title":"T","paragraphs":[{"speaker":"ana","text":"Oi"},{"speaker":"Beto","text":"Olá"},{"text":"sem nome"},"texto solto"]}'
    _, lines = parse_script_lines(raw, cfg)
    assert [s for s, _ in lines] == ["Ana", "Beto", "Ana", "Beto"]  # sem nome válido alterna
    _, single = parse_script_lines('{"paragraphs":["a","b"]}', ScriptConfig.build(None, None, ["Ana"]))
    assert [s for s, _ in single] == [None, None]


async def test_generation_stores_config_and_speakers():
    two = '{"title":"V","paragraphs":[{"speaker":"Ana","text":"Abertura."},{"speaker":"Beto","text":"Resposta."}]}'
    agents = SequenceAgents([two])
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    cfg = ScriptConfig.build(BUILTIN_PROFILES[1], 5, ["Ana", "Beto"])
    script = await StartScriptGeneration(wf)(item.id, False, None, cfg)
    await runner.drain()
    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.DONE and saved.config.max_chars == 630
    assert [p.speaker for p in saved.paragraphs] == ["Ana", "Beto"] and saved.total_chars < 630


async def test_config_always_creates_new_script_but_empty_config_reuses():
    agents = SequenceAgents(['{"paragraphs":["Um."]}', '{"paragraphs":["Dois."]}'])
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    start = StartScriptGeneration(wf)
    first = await start(item.id)
    await runner.drain()
    assert (await start(item.id, False, None, ScriptConfig())).id == first.id  # vazia = reaproveita
    second = await start(item.id, False, None, ScriptConfig.build(None, 8, []))
    assert second.id != first.id


async def test_too_long_script_is_shortened_once_then_fails():
    long_text = "x" * 700
    agents = SequenceAgents([f'{{"paragraphs":["{long_text}"]}}', '{"paragraphs":["curto e dentro do limite."]}'])
    news_repo, script_repo, runner, wf = _scripting(agents)
    item = (await _search_with_item(agents, runner, news_repo)).items[0]
    script = await StartScriptGeneration(wf)(item.id, False, None, ScriptConfig.build(None, 5, []))
    await runner.drain()
    assert (await script_repo.get(script.id)).status is JobStatus.DONE
    jules = [p for b, p in agents.calls if b is Bot.JULESVERNE]
    assert len(jules) == 2 and "MAIS CURTA" in jules[1] and "700 caracteres" in jules[1]

    stubborn = SequenceAgents([f'{{"paragraphs":["{long_text}"]}}'] * 2)
    news_repo, script_repo, runner, wf = _scripting(stubborn)
    item = (await _search_with_item(stubborn, runner, news_repo)).items[0]
    failed = await StartScriptGeneration(wf)(item.id, False, None, ScriptConfig.build(None, 5, []))
    await runner.drain()
    saved = await script_repo.get(failed.id)
    assert saved.status is JobStatus.FAILED and "630" in saved.error


async def test_custom_profiles_lifecycle():
    repo = MemoryProfiles()
    options, add, delete = ScriptConfigOptions(repo), AddScriptProfile(repo), DeleteScriptProfile(repo)
    created = await add("Humor ácido", "Tom bem-humorado, sarcástico mas respeitoso, com piadas curtas.")
    assert [p.name for p in await options.profiles()][-1] == "Humor ácido" and len(await options.profiles()) == 5
    assert (await options.resolve(created.id)).name == "Humor ácido"
    assert (await options.resolve("tech")).builtin
    with pytest.raises(Conflict):
        await add("humor ácido", "Outra descrição qualquer aqui.")
    with pytest.raises(InvalidInput):
        await add("Tech & Analítico", "Duplicando um perfil básico qualquer.")
    with pytest.raises(InvalidInput):
        await add("Curto", "curto")
    with pytest.raises(InvalidInput):
        await delete("tech")
    await delete(created.id)
    with pytest.raises(NotFound):
        await delete(created.id)
    with pytest.raises(InvalidInput):
        await options.resolve(created.id)


def test_config_roundtrip_json():
    cfg = ScriptConfig.build(BUILTIN_PROFILES[3], 12, ["A", "B"])
    assert ScriptConfig.from_json(cfg.to_json()) == cfg
    assert ScriptConfig.from_json(None) is None


NEWS_TWO = (
    '{"news":[{"title":"Quest 3S em promoção","summary":"Preço caiu.","details":"US$ 297."},'
    '{"title":"Steam Frame vaza","summary":"Novo headset da Valve.","details":"Eye tracking."}]}'
)


async def _two_items():
    agents = SequenceAgents(['{"paragraphs":["Texto agregado."]}'], **{Bot.TONTON.value and Bot.TONTON: NEWS_TWO})
    news_repo, script_repo, runner, wf = _scripting(agents)
    search = await _search_with_item(agents, runner, news_repo)
    return agents, script_repo, runner, wf, search.items


async def test_merged_script_uses_all_selected_news_and_theme():
    from studio.scripting.domain.config import ScriptConfig

    agents, script_repo, runner, wf, items = await _two_items()
    cfg = ScriptConfig.build(None, None, [], theme="  Headsets   de VR em 2026 ")
    assert cfg.theme == "Headsets de VR em 2026" and not cfg.is_empty
    script = await StartScriptGeneration(wf)(items[0].id, False, None, cfg, [items[1].id, items[1].id, items[0].id])
    await runner.drain()
    saved = await script_repo.get(script.id)
    assert saved.status is JobStatus.DONE and saved.extra_news_item_ids == [items[1].id]  # sem repetir nem incluir a principal
    prompt = next(p for b, p in agents.calls if b is Bot.JULESVERNE)
    assert "[NOTÍCIA 1]" in prompt and "[NOTÍCIA 2]" in prompt and "Quest 3S" in prompt and "Steam Frame" in prompt
    assert "ÚNICO vídeo" in prompt and "Headsets de VR em 2026" in prompt and "as notícias abaixo" in prompt


async def test_merge_always_creates_new_script_and_validates():
    agents, script_repo, runner, wf, items = await _two_items()
    start = StartScriptGeneration(wf)
    first = await start(items[0].id)
    await runner.drain()
    merged = await start(items[0].id, False, None, None, [items[1].id])
    assert merged.id != first.id  # agregar nunca reaproveita o roteiro simples
    with pytest.raises(NotFound):
        await start(items[0].id, False, None, None, [uuid4()])
    with pytest.raises(InvalidInput):
        await start(items[0].id, False, None, None, [uuid4() for _ in range(6)])


async def test_single_news_prompt_unchanged_by_merge_support():
    from studio.scripting.application.ports import NewsSource

    news = NewsSource(id=uuid4(), topic="VR", title="Quest", summary="s", details=None, source_url=None)
    prompt = script_prompt(news)
    assert "a notícia abaixo" in prompt and "[NOTÍCIA" not in prompt and "ÚNICO" not in prompt
