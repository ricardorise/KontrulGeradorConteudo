import pytest

from studio.discovery.application.parsing import parse_news
from studio.scripting.application.parsing import parse_broll, parse_script
from studio.scripting.domain.script import parse_youtube_url
from studio.shared.application.json_extract import extract_json_object
from studio.shared.application.ports import AgentOutputError


def test_extract_json_tolerates_chatter_and_fences():
    raw = 'Claro! Aqui está:\n```json\n{"news": [{"title": "a", "summary": "b"}]}\n```\nAbraço'
    assert extract_json_object(raw, "news")["news"][0]["title"] == "a"


def test_extract_json_skips_objects_without_key():
    raw = '{"x": 1} e depois {"news": []}'
    assert extract_json_object(raw, "news") == {"news": []}


def test_extract_json_fails_without_valid_json():
    with pytest.raises(AgentOutputError):
        extract_json_object("sem json", "news")


def test_parse_news_keeps_valid_entries_and_nulls():
    raw = (
        '{"news":[{"title":"T1","summary":"S1","details":"D1","source_url":"null","published_at":"2026-11-19"},'
        '{"title":"","summary":"sem título"},{"title":"T2","summary":"S2","source_url":"https://x.com/a"}]}'
    )
    items = parse_news(raw)
    assert [i.title for i in items] == ["T1", "T2"]
    assert [i.position for i in items] == [0, 1]
    assert items[0].source_url is None and items[0].details == "D1"
    assert items[1].source_url == "https://x.com/a"


def test_parse_news_empty_is_error():
    with pytest.raises(AgentOutputError):
        parse_news('{"news": []}')


def test_parse_script():
    title, texts = parse_script('{"title":"Vídeo","paragraphs":["um"," dois ",""]}')
    assert title == "Vídeo" and texts == ["um", "dois"]


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://youtu.be/dQw4w9WgXcQ?t=43", ("dQw4w9WgXcQ", 43)),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s", ("dQw4w9WgXcQ", 65)),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("dQw4w9WgXcQ", None)),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", ("dQw4w9WgXcQ", None)),
        ("https://evil.com/watch?v=dQw4w9WgXcQ", None),
        ("javascript:alert(1)", None),
        ("https://youtu.be/curto", None),
    ],
)
def test_parse_youtube_url(url, expected):
    assert parse_youtube_url(url) == expected


def test_parse_broll_filters_invalid_and_out_of_range():
    raw = """{"scenes":[
      {"paragraph":0,"url":"https://youtu.be/dQw4w9WgXcQ?t=10","description":"cena A","title":"V"},
      {"paragraph":0,"url":"https://evil.com/x","description":"link falso"},
      {"paragraph":7,"url":"https://youtu.be/dQw4w9WgXcQ","description":"fora do roteiro"},
      {"paragraph":"1","url":"https://youtu.be/abcdefghijk","description":"cena B","justification":"ok"}]}"""
    scenes = parse_broll(raw, paragraph_count=2)
    assert set(scenes) == {0, 1}
    assert scenes[0][0].video_url == "https://youtu.be/dQw4w9WgXcQ?t=10" and scenes[0][0].start_seconds == 10
    assert scenes[1][0].justification == "ok" and len(scenes[0]) == 1

@pytest.mark.parametrize('suffix,seconds', [('?t=326s',326),('#t=5m26s',326),('?start=05:26',326),('?t=0',0)])
def test_broll_preserves_source_start_formats(suffix, seconds):
    assert parse_youtube_url('https://youtu.be/dQw4w9WgXcQ'+suffix) == ('dQw4w9WgXcQ',seconds)


def test_broll_structured_start_builds_clickable_link():
    scenes = parse_broll('{"scenes":[{"paragraph":0,"url":"https://youtu.be/dQw4w9WgXcQ","start_seconds":326,"description":"Trecho no meio do vídeo"}]}',1)
    assert scenes[0][0].start_seconds == 326
    assert scenes[0][0].video_url.endswith('?t=326')


def test_radar_keeps_official_analysis_in_api_and_writer_material():
    from studio.interfaces.http.schemas import NewsItemOut
    raw = '{"news":[{"title":"Sinal emergente","summary":"Resumo","radar":{"status":"EMERGING","why_now":"Duas fontes independentes","velocity":"não confirmada","evidence":["Fonte A, 24h","Fonte B, 24h"],"sources":["https://example.com/a"],"divergences":"Métrica indisponível"}}]}'
    item = parse_news(raw)[0]
    output = NewsItemOut.of(item).model_dump()
    assert output['radar']['status'] == 'EMERGING'
    assert len(output['radar']['evidence']) == 2
    assert output['radar']['divergences'] == 'Métrica indisponível'


def test_radar_prompt_preserves_official_method_without_generic_count():
    from studio.discovery.application.prompts import news_search_prompt
    prompt = news_search_prompt('Radar de Tendências')
    assert 'SOUL.md' in prompt and 'memórias persistentes' in prompt
    assert 'entre 5 e 8' not in prompt
    assert 'divergences' in prompt and 'evidence' in prompt


def test_radar_rejects_duplicate_rank_instead_of_silently_renumbering():
    with pytest.raises(AgentOutputError, match='ranking'):
        parse_news('{"news":[{"rank":1,"title":"A","summary":"A"},{"rank":1,"title":"B","summary":"B"}]}', ranked=True)


def test_radar_window_rejects_future_dates_and_empty_scope():
    from datetime import datetime, timezone, timedelta
    from studio.discovery.application.radar import plan
    now = datetime(2026,11,24,12,tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='futuro'):
        plan(now, end=now+timedelta(hours=1))
    with pytest.raises(ValueError, match='escopo'):
        plan(now, scope='   ')


def test_radar_rejects_publications_after_cutoff_and_reindexes_remaining_items():
    from datetime import datetime, timezone
    from studio.discovery.application.radar import plan, validate_window
    context = plan(datetime(2026,11,24,tzinfo=timezone.utc), end=datetime(2026,11,23,14,30,tzinfo=timezone.utc))
    items = parse_news('{"news":[{"rank":1,"title":"Futuro para a janela","summary":"s","published_at":"2026-11-23T20:30:00Z","radar":{"ranking_reason":"r"}},{"rank":2,"title":"Dentro da janela","summary":"s","published_at":"2026-11-23T10:30:00Z","radar":{"ranking_reason":"r"}}]}',ranked=True)
    result=validate_window(items,context)
    assert len(result)==1 and result[0].position==0 and result[0].title=='Dentro da janela'
    assert 'Futuro para a janela' in context['discarded'][0]
