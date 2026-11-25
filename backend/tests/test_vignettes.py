import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from studio.infrastructure.media.ffmpeg import (
    FfmpegProbe,
    FfmpegVideoComposer,
    Segment,
    build_compose_args,
    parse_media_info,
)
from studio.infrastructure.media.store import LocalMediaStore
from studio.rendering.application.ports import MediaError, MediaInfo, OutputStream, RenderProgress
from studio.rendering.application.use_cases import (
    OpenRenderVideo,
    PreviewRender,
    RenderFinisher,
    RenderMonitor,
    StartRender,
    UploadRenderAsset,
)
from studio.rendering.domain.asset import AssetKind
from studio.rendering.domain.render_job import RenderOutput
from studio.shared.domain.errors import InvalidInput
from studio.shared.domain.status import JobStatus
from tests.fakes import InlineRunner
from tests.test_rendering import FakeRenderer, MemoryRenderRepo, Source, cut, script

FFMPEG_OUT = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'Intro.mp4':
  Duration: 00:00:06.02, start: 0.000000, bitrate: 2139 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 2000 kb/s, 29.97 fps, 29.97 tbr
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706d), 48000 Hz, stereo, fltp, 128 kb/s"""


def test_parse_media_info():
    info = parse_media_info(FFMPEG_OUT)
    assert (info.duration, info.width, info.height, info.fps) == (6.02, 1920, 1080, 29.97)
    assert info.has_video and info.has_audio
    silent = parse_media_info(FFMPEG_OUT.split("  Stream #0:1")[0])
    assert silent.has_video and not silent.has_audio
    assert not parse_media_info("Invalid data found when processing input").has_video


def test_compose_args_order_normalization_and_silence_for_missing_audio():
    segs = [Segment(Path("intro.mp4"), 6, True), Segment(Path("main.mp4"), 100, True), Segment(Path("outro.mp4"), 5, False)]
    args = build_compose_args(segs, Path("out.mp4"), 1280, 720, 30)
    inputs = [args[i + 1] for i, a in enumerate(args) if a == "-i"]
    assert inputs[:2] == ["intro.mp4", "main.mp4"] and inputs[2] == "outro.mp4"  # abertura → fala → final
    graph = args[args.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=1" in graph and graph.index("[v0][a0][v1][a1][v2][a2]") < graph.index("concat")
    assert "scale=1280:720" in graph and "pad=1280:720" in graph and "aresample=48000" in graph
    assert "anullsrc=r=48000:cl=stereo" in args and args[args.index("-t") + 1] == "5.000"  # saída sem áudio ganha 5 s de silêncio
    assert args[-1] == "out.mp4"


# ---- upload ----
class FakeProbe:
    def __init__(self, info, level=-20.0):
        self.info, self.level = info, level

    async def mean_volume(self, path):
        return self.level

    async def probe(self, path):
        if isinstance(self.info, Exception):
            raise self.info
        return self.info


class MemoryAssets:
    def __init__(self):
        self.data = {}

    async def add(self, a):
        self.data[a.id] = a

    async def get(self, i):
        return self.data.get(i)

    async def list(self, kind):
        return [a for a in self.data.values() if kind is None or a.kind == kind]

    async def delete(self, i):
        self.data.pop(i, None)


async def one(data: bytes):
    yield data


GOOD = MediaInfo(6.0, 1920, 1080, 30, True, True)


async def test_upload_validates_kind_extension_content_and_cleans_up(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    upload = lambda info=GOOD, mb=1: UploadRenderAsset(assets, store, FakeProbe(info), mb * 1024 * 1024)  # noqa: E731

    asset = await upload()("intro", "Minha Vinheta.MP4", one(b"x" * 1000))
    assert (asset.kind, asset.filename, asset.size_bytes, asset.duration) == (AssetKind.INTRO, "Minha Vinheta.MP4", 1000, 6.0)
    assert store.asset_path(asset.stored_name).is_file()

    for bad in [("publicidade", "a.mp4"), ("intro", "a.exe"), ("intro", "semextensao")]:
        with pytest.raises(InvalidInput):
            await upload()(bad[0], bad[1], one(b"x"))
    with pytest.raises(InvalidInput, match="sem vídeo|não tem vídeo"):
        await upload(MediaInfo(5, 0, 0, 30, False, True))("outro", "a.mp4", one(b"x"))
    with pytest.raises(InvalidInput, match="Não consegui ler"):
        await upload(MediaError("corrompido"))("outro", "a.mp4", one(b"x"))
    with pytest.raises(MediaError, match="limite"):  # maior que o limite
        await upload(GOOD, 1)("outro", "a.mp4", one(b"x" * (2 * 1024 * 1024)))
    assert len(list((tmp_path / "assets").iterdir())) == 1  # nada sobrou dos uploads recusados


# ---- fluxo: ComfyUI termina -> montagem -> vídeo final ----
class FakeComposer:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def compose(self, main, intro, outro, dest, music=None, music_volume=0.08, intro_volume=1.0, outro_volume=1.0, normalize=True,
                      music_intro_volume=None, music_outro_volume=None):
        self.calls.append((main.read_bytes(), intro and intro.name, outro and outro.name))
        self.music = (music and music.name, music_volume)
        self.volumes = (intro_volume, outro_volume, normalize)
        self.music_stages = (music_intro_volume, music_volume, music_outro_volume)
        if self.fail:
            raise MediaError("ffmpeg falhou: erro")
        dest.write_bytes(b"FINAL")


class StreamRenderer(FakeRenderer):
    async def open_output(self, output):
        async def gen():
            yield b"MAIN"

        return OutputStream(gen(), 4)


async def _flow(tmp_path, composer, with_outro=True):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    probe = FakeProbe(GOOD)
    up = UploadRenderAsset(assets, store, probe, 10**7)
    intro = await up("intro", "abertura.mp4", one(b"i"))
    outro = await up("outro", "final.mp4", one(b"o")) if with_outro else None
    out = RenderOutput("final.mp4", "papotechcast")
    renderer = StreamRenderer([RenderProgress("running"), RenderProgress("done", out)])
    repo, runner = MemoryRenderRepo(), InlineRunner()
    finisher = RenderFinisher(repo, assets, renderer, store, composer)
    monitor = RenderMonitor(repo, renderer, poll_interval_s=0, finisher=finisher)
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner, monitor, assets)
    job = await start(uuid4(), None, intro.id, outro.id if outro else None)
    await runner.drain()
    return repo.data[job.id], store, repo, renderer, intro, outro


async def test_vignettes_are_composed_in_order_after_comfyui_finishes(tmp_path):
    composer = FakeComposer()
    job, store, repo, renderer, intro, outro = await _flow(tmp_path, composer)
    assert composer.calls == [(b"MAIN", intro.stored_name, outro.stored_name)]
    assert job.status is JobStatus.DONE and job.stage == "done" and job.final_path == str(store.result_path(job.id))
    assert not store.temp_path(job.id).exists()  # temporário apagado
    source = await OpenRenderVideo(repo, renderer)(job.id)
    assert source.path == store.result_path(job.id) and source.stream is None  # serve o arquivo montado


async def test_only_intro_is_enough(tmp_path):
    composer = FakeComposer()
    job, *_ = await _flow(tmp_path, composer, with_outro=False)
    assert job.status is JobStatus.DONE and composer.calls[0][2] is None


async def test_composition_failure_is_reported_clearly(tmp_path):
    job, store, *_ = await _flow(tmp_path, FakeComposer(fail=True))
    assert job.status is JobStatus.FAILED and "montagem com as vinhetas falhou" in job.error
    assert not store.temp_path(job.id).exists()


async def test_without_vignettes_nothing_is_composed_and_video_is_proxied(tmp_path):
    composer = FakeComposer()
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    out = RenderOutput("final.mp4")
    renderer = StreamRenderer([RenderProgress("done", out)])
    repo, runner = MemoryRenderRepo(), InlineRunner()
    monitor = RenderMonitor(repo, renderer, 0, finisher=RenderFinisher(repo, assets, renderer, store, composer))
    job = await StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner, monitor, assets)(uuid4())
    await runner.drain()
    assert composer.calls == [] and repo.data[job.id].status is JobStatus.DONE
    assert (await OpenRenderVideo(repo, renderer)(job.id)).stream is not None


async def test_unknown_or_wrong_kind_vignette_is_rejected(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    outro = await UploadRenderAsset(assets, store, FakeProbe(GOOD), 10**7)("outro", "f.mp4", one(b"o"))
    renderer = StreamRenderer([RenderProgress("running")])
    repo, runner = MemoryRenderRepo(), InlineRunner()
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner,
                        RenderMonitor(repo, renderer, 0), assets)
    with pytest.raises(InvalidInput, match="abertura|intro"):
        await start(uuid4(), None, outro.id, None)  # um 'outro' usado como abertura
    with pytest.raises(InvalidInput):
        await start(uuid4(), None, uuid4(), None)


# ---- ffmpeg de verdade ----
def _ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:  # sem ffmpeg no sistema: usa o binário estático do pacote de desenvolvimento
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg não instalado")
async def test_real_ffmpeg_composes_intro_main_outro_with_audio(tmp_path):
    def make(name, seconds, size, audio):
        path = tmp_path / name
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=30"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
        subprocess.run([*cmd, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-shortest", str(path)], check=True)
        return path

    intro, main, outro = make("intro.mp4", 2, "640x360", True), make("main.mp4", 3, "1280x720", True), make("outro.mp4", 1, "800x600", False)
    probe = FfmpegProbe(_ffmpeg())
    dest = tmp_path / "out" / "final.mp4"
    await FfmpegVideoComposer(probe, _ffmpeg()).compose(main, intro, outro, dest)
    info = await probe.probe(dest)
    assert (info.width, info.height) == (1280, 720)  # normalizado pelo vídeo principal
    assert info.has_audio and abs(info.duration - 6.0) < 0.5  # 2 + 3 + 1
    assert not list(dest.parent.glob("*.partial.mp4"))
    with pytest.raises(MediaError):
        await FfmpegVideoComposer(probe, _ffmpeg()).compose(tmp_path / "nao-existe.mp4", intro, None, tmp_path / "x.mp4")


# ---- áudio de fundo (trilha) ----
import json  # noqa: E402

import httpx  # noqa: E402

from studio.infrastructure.comfyui.renderer import DEFAULT_WORKFLOW, ComfyUiRenderer  # noqa: E402
from studio.infrastructure.comfyui.workflow import default_music_volume, fill_workflow  # noqa: E402
from studio.rendering.application.ports import RenderError, RenderSubmission  # noqa: E402

TEMPLATE = json.loads(DEFAULT_WORKFLOW.read_text(encoding="utf-8"))
AUDIO_ONLY = MediaInfo(180.0, 0, 0, 30, False, True)


def test_fill_workflow_sets_music_track_and_volume_only_when_chosen():
    plain = fill_workflow(TEMPLATE, RenderSubmission("R", "b.mp4", "L"))
    assert plain["2"]["inputs"]["trilha"] == TEMPLATE["2"]["inputs"]["trilha"]  # sem trilha: preserva o workflow
    assert plain["5"]["inputs"]["volume_trilha"] == TEMPLATE["5"]["inputs"]["volume_trilha"]

    filled = fill_workflow(TEMPLATE, RenderSubmission("R", "b.mp4", "L", "papotechcast/trilha-1a2b3c4d.mp3", 0.15))
    assert filled["2"]["inputs"]["trilha"] == "papotechcast/trilha-1a2b3c4d.mp3"
    assert filled["5"]["inputs"]["volume_trilha"] == 0.15
    changed = {(n, k) for n, node in filled.items() for k, v in node["inputs"].items() if TEMPLATE[n]["inputs"].get(k) != v}
    assert changed == {("1", "value"), ("8", "value"), ("2", "background"), ("2", "trilha"), ("5", "volume_trilha")}
    assert default_music_volume(TEMPLATE) == 0.08


async def test_comfy_upload_input_posts_multipart_to_input_folder(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        if req.method == "HEAD":  # o ComfyUI ainda não tem o arquivo
            return httpx.Response(404)
        seen["path"], seen["ctype"], seen["body"] = req.url.path, req.headers["content-type"], req.content
        return httpx.Response(200, json={"name": "trilha-1.mp3", "subfolder": "papotechcast", "type": "input"})

    song = tmp_path / "x.mp3"
    song.write_bytes(b"ID3audio")
    renderer = ComfyUiRenderer("http://comfy", transport=httpx.MockTransport(handler))
    assert await renderer.upload_input(song, "papotechcast", "trilha-1.mp3") == "papotechcast/trilha-1.mp3"
    assert seen["path"] == "/upload/image" and seen["ctype"].startswith("multipart/form-data")
    for part in (b'name="image"; filename="trilha-1.mp3"', b'name="type"', b"input", b'name="subfolder"', b'name="overwrite"', b"true", b"ID3audio"):
        assert part in seen["body"]
    failing = ComfyUiRenderer("http://comfy", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(RenderError, match="recusou o upload"):
        await failing.upload_input(song, "papotechcast", "t.mp3")


async def test_music_upload_accepts_audio_rejects_video_only_and_wrong_types(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    up = lambda info: UploadRenderAsset(assets, store, FakeProbe(info), 10**7)  # noqa: E731
    song = await up(AUDIO_ONLY)("music", "Trilha Calma.MP3", one(b"x"))
    assert song.kind is AssetKind.MUSIC and song.has_audio and song.duration == 180.0
    with pytest.raises(InvalidInput, match="não tem áudio"):
        await up(MediaInfo(5, 640, 360, 30, True, False))("music", "mudo.mp4", one(b"x"))
    with pytest.raises(InvalidInput, match="Formato não suportado"):
        await up(AUDIO_ONLY)("music", "doc.pdf", one(b"x"))
    with pytest.raises(InvalidInput, match="Formato não suportado"):
        await up(GOOD)("intro", "musica.mp3", one(b"x"))  # áudio não serve como vinheta de vídeo
    assert len(list((tmp_path / "assets").iterdir())) == 1


async def test_render_uploads_track_to_comfy_and_sends_it_with_volume(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    song = await UploadRenderAsset(assets, store, FakeProbe(AUDIO_ONLY), 10**7)("music", "calma.mp3", one(b"audio"))
    renderer = StreamRenderer([RenderProgress("running")])
    sent = []
    original = renderer.submit

    async def spy(submission):
        sent.append(submission)
        return await original(submission)

    renderer.submit = spy
    repo, runner = MemoryRenderRepo(), InlineRunner()
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner,
                        RenderMonitor(repo, renderer, 0), assets, store)
    job = await start(uuid4(), None, None, None, song.id, 0.2)
    assert renderer.uploads == [(f"{song.id}.mp3", "papotechcast", f"trilha-{song.id.hex[:8]}.mp3")]
    assert sent[0].music == f"papotechcast/trilha-{song.id.hex[:8]}.mp3" and sent[0].music_volume == 0.2
    assert job.music_asset_id == song.id and job.music_volume == 0.2

    default = await start(uuid4(), None, None, None, song.id, None)  # sem volume: usa o padrão do workflow
    assert default.music_volume == 0.08
    with pytest.raises(InvalidInput, match="volume"):
        await start(uuid4(), None, None, None, song.id, 1.5)
    with pytest.raises(InvalidInput):  # um vídeo de abertura não pode ser usado como trilha
        intro = await UploadRenderAsset(assets, store, FakeProbe(GOOD), 10**7)("intro", "i.mp4", one(b"x"))
        await start(uuid4(), None, None, None, intro.id, None)


async def test_render_without_music_keeps_workflow_default_track(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    renderer = StreamRenderer([RenderProgress("running")])
    sent = []
    original = renderer.submit

    async def spy(submission):
        sent.append(submission)
        return await original(submission)

    renderer.submit = spy
    repo, runner = MemoryRenderRepo(), InlineRunner()
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner,
                        RenderMonitor(repo, renderer, 0), assets, store)
    await start(uuid4())
    assert sent[0].music is None and sent[0].music_volume is None and not getattr(renderer, "uploads", [])


async def test_comfy_upload_is_skipped_when_same_file_is_already_there(tmp_path):
    calls = []
    big = tmp_path / "fundo.mp4"
    big.write_bytes(b"x" * 5000)

    def handler(req: httpx.Request):
        calls.append(req.method)
        if req.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(5000 if not same_size[0] else 5000)})
        return httpx.Response(200, json={"name": "fundo-1.mp4", "subfolder": "papotechcast", "type": "input"})

    same_size = [True]
    renderer = ComfyUiRenderer("http://comfy", transport=httpx.MockTransport(handler))
    assert await renderer.upload_input(big, "papotechcast", "fundo-1.mp4") == "papotechcast/fundo-1.mp4"
    assert calls == ["HEAD"]  # mesmo nome e tamanho: não reenviou 800 MB
    big.write_bytes(b"x" * 6000)  # arquivo diferente com o mesmo nome: reenvia
    calls.clear()
    await renderer.upload_input(big, "papotechcast", "fundo-1.mp4")
    assert calls == ["HEAD", "POST"]


async def test_uploaded_background_replaces_server_path_and_is_sent_to_comfy(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    up = UploadRenderAsset(assets, store, FakeProbe(MediaInfo(3600.0, 1920, 1080, 30, True, False)), 10**8)
    bg = await up("background", "Meu Fundo.mp4", one(b"video"))  # 1 h: aceito (vinhetas são limitadas a 10 min)
    assert bg.kind is AssetKind.BACKGROUND and bg.duration == 3600.0
    with pytest.raises(InvalidInput, match="até 6 horas"):
        await UploadRenderAsset(assets, store, FakeProbe(MediaInfo(7 * 3600, 1920, 1080, 30, True, True)), 10**8)("background", "x.mp4", one(b"v"))
    with pytest.raises(InvalidInput, match="não tem vídeo"):
        await UploadRenderAsset(assets, store, FakeProbe(AUDIO_ONLY), 10**8)("background", "x.mp4", one(b"v"))

    renderer = StreamRenderer([RenderProgress("running")])
    sent = []
    original = renderer.submit

    async def spy(submission):
        sent.append(submission)
        return await original(submission)

    renderer.submit = spy
    repo, runner = MemoryRenderRepo(), InlineRunner()
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner,
                        RenderMonitor(repo, renderer, 0), assets, store)
    job = await start(uuid4(), "papotechcast/Background2.mp4", None, None, None, None, bg.id)
    expected = f"papotechcast/fundo-{bg.id.hex[:8]}.mp4"
    assert renderer.uploads == [(f"{bg.id}.mp4", "papotechcast", f"fundo-{bg.id.hex[:8]}.mp4")]
    assert sent[0].background == expected and job.background == expected and job.background_asset_id == bg.id

    plain = await start(uuid4(), "papotechcast/Background2.mp4")  # sem upload: usa o caminho do servidor
    assert plain.background == "papotechcast/Background2.mp4" and plain.background_asset_id is None
    with pytest.raises(InvalidInput):  # uma trilha não serve como background
        song = await UploadRenderAsset(assets, store, FakeProbe(AUDIO_ONLY), 10**8)("music", "m.mp3", one(b"a"))
        await start(uuid4(), None, None, None, None, None, song.id)


# ---- trilha desde a abertura ----
def test_compose_args_with_music_mixes_over_the_whole_video_with_fade_out():
    segs = [Segment(Path("intro.mp4"), 6, True), Segment(Path("main.mp4"), 100, True), Segment(Path("outro.mp4"), 5, True)]
    args = build_compose_args(segs, Path("out.mp4"), 1280, 720, 30, music=Path("calma.mp3"), music_volume=0.12)
    graph = args[args.index("-filter_complex") + 1]
    assert args[args.index("-stream_loop") + 1] == "-1" and "calma.mp3" in args  # em loop
    assert "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][voice]" in graph  # voz e vinhetas concatenadas
    assert "volume=0.12" in graph and "afade=t=out:st=109.000:d=2.000" in graph  # fade-out nos últimos 2 s dos 111 s
    assert "[voice][bed]amix=inputs=2:duration=first:normalize=0[a]" in graph
    assert args[args.index("-t") + 1] == "111.000"  # corta o loop infinito no tamanho do vídeo
    no_music = build_compose_args(segs, Path("out.mp4"), 1280, 720, 30)
    assert "-stream_loop" not in no_music and "amix" not in no_music[no_music.index("-filter_complex") + 1]


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg não instalado")
async def test_real_ffmpeg_music_is_audible_from_the_silent_intro_and_fades_out(tmp_path):
    ff = _ffmpeg()

    def make(name, seconds, audio):
        path = tmp_path / name
        cmd = [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=640x360:rate=30"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
        subprocess.run([*cmd, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-shortest", str(path)], check=True)
        return path

    intro, main = make("intro.mp4", 3, False), make("main.mp4", 4, True)  # abertura MUDA
    music = tmp_path / "bed.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=2", str(music)], check=True)  # 2 s: precisa repetir

    def mean_volume(video: Path, start: float, length: float) -> float:
        r = subprocess.run([ff, "-hide_banner", "-ss", str(start), "-t", str(length), "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True)
        line = next(l for l in r.stderr.splitlines() if "mean_volume" in l)
        return float(line.split("mean_volume:")[1].split("dB")[0])

    probe = FfmpegProbe(ff)
    composer = FfmpegVideoComposer(probe, ff)
    plain, mixed = tmp_path / "plain.mp4", tmp_path / "mixed.mp4"
    await composer.compose(main, intro, None, plain)
    await composer.compose(main, intro, None, mixed, music, 0.5)

    assert mean_volume(plain, 0.2, 2.5) < -80  # sem trilha, a abertura muda é silêncio
    assert mean_volume(mixed, 0.2, 2.5) > -35  # com trilha, a música já toca durante a abertura
    assert mean_volume(mixed, 4.0, 2.0) > -50  # e continua sob a fala, mesmo o arquivo tendo só 2 s (loop)
    info = await probe.probe(mixed)
    assert abs(info.duration - 7.0) < 0.3  # a trilha não estica o vídeo


async def test_with_vignettes_music_is_mixed_in_final_composition_not_sent_to_comfy(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    up = lambda info: UploadRenderAsset(assets, store, FakeProbe(info), 10**7)  # noqa: E731
    intro = await up(GOOD)("intro", "i.mp4", one(b"i"))
    song = await up(AUDIO_ONLY)("music", "calma.mp3", one(b"a"))
    out = RenderOutput("final.mp4", "papotechcast")
    renderer = StreamRenderer([RenderProgress("done", out)])
    sent = []
    original = renderer.submit

    async def spy(submission):
        sent.append(submission)
        return await original(submission)

    renderer.submit = spy
    repo, runner, composer = MemoryRenderRepo(), InlineRunner(), FakeComposer()
    finisher = RenderFinisher(repo, assets, renderer, store, composer)
    monitor = RenderMonitor(repo, renderer, poll_interval_s=0, finisher=finisher)
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner, monitor, assets, store)
    job = await start(uuid4(), None, intro.id, None, song.id, 0.15)
    await runner.drain()
    assert sent[0].music is None and not getattr(renderer, "uploads", [])  # o ComfyUI não recebe a trilha
    assert composer.music == (song.stored_name, 0.15)  # a montagem final recebe a trilha e o volume
    assert repo.data[job.id].status is JobStatus.DONE


# ---- volumes por trecho, nivelamento, volume do background e remix ----
from studio.rendering.application.use_cases import RemixRender  # noqa: E402


def test_compose_args_apply_gain_and_loudness_only_to_vignettes():
    segs = [Segment(Path("i.mp4"), 6, True, 0.5, True), Segment(Path("m.mp4"), 90, True), Segment(Path("o.mp4"), 5, True, 1.5, False)]
    graph = build_compose_args(segs, Path("out.mp4"), 1280, 720, 30)
    graph = graph[graph.index("-filter_complex") + 1]
    intro, main, outro = (next(f for f in graph.split(";") if f.endswith(f"[a{n}]")) for n in range(3))
    assert "loudnorm=I=-16" in intro and "volume=0.5" in intro  # nivela e depois aplica o ganho do usuário
    assert "loudnorm" not in main and "volume=" not in main  # a fala já vem nivelada do ComfyUI e não muda
    assert "volume=1.5" in outro and "loudnorm" not in outro
    plain = build_compose_args([Segment(Path("i.mp4"), 6, True)], Path("o.mp4"), 1280, 720, 30)
    assert "volume=" not in plain[plain.index("-filter_complex") + 1]  # ganho 1 não gera filtro


def test_fill_workflow_sets_background_volume_and_refuses_when_workflow_lacks_it():
    filled = fill_workflow(TEMPLATE, RenderSubmission("R", "b.mp4", "L", background_volume=0.3))
    assert filled["5"]["inputs"]["volume_fundo"] == 0.3
    legacy = json.loads(json.dumps(TEMPLATE))
    del legacy["5"]["inputs"]["volume_fundo"]
    with pytest.raises(RenderError, match="volume_fundo"):
        fill_workflow(legacy, RenderSubmission("R", "b.mp4", "L", background_volume=0.3))
    assert "volume_fundo" not in fill_workflow(legacy, RenderSubmission("R", "b.mp4", "L", background_volume=0.0))["5"]["inputs"]


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg não instalado")
async def test_real_ffmpeg_vignette_volume_and_leveling(tmp_path):
    ff = _ffmpeg()

    def tone(name, amp):  # abertura com tom a volume conhecido
        path = tmp_path / name
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=30",
                        "-f", "lavfi", "-i", f"sine=frequency=440:duration=3,volume={amp}", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-c:a", "aac", "-shortest", str(path)], check=True)
        return path

    def mean_volume(video, start, length):
        r = subprocess.run([ff, "-hide_banner", "-ss", str(start), "-t", str(length), "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True)
        return float(next(l for l in r.stderr.splitlines() if "mean_volume" in l).split("mean_volume:")[1].split("dB")[0])

    main = tmp_path / "main.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=30", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=2", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(main)], check=True)
    loud, quiet = tone("loud.mp4", 0.8), tone("quiet.mp4", 0.05)
    composer = FfmpegVideoComposer(FfmpegProbe(ff), ff)

    async def intro_level(src, gain, normalize):
        out = tmp_path / f"o-{src.stem}-{gain}-{normalize}.mp4"
        await composer.compose(main, src, None, out, None, 0.08, gain, 1.0, normalize)
        return mean_volume(out, 0.3, 2.0)

    full, half = await intro_level(loud, 1.0, False), await intro_level(loud, 0.5, False)
    assert 4.5 < full - half < 7.5  # ganho 0,5 ≈ −6 dB
    assert await intro_level(loud, 0.0, False) < -70  # 0% = mudo
    gap_raw = abs(await intro_level(loud, 1.0, False) - await intro_level(quiet, 1.0, False))
    gap_leveled = abs(await intro_level(loud, 1.0, True) - await intro_level(quiet, 1.0, True))
    assert gap_raw > 15 and gap_leveled < 4  # o nivelamento aproxima uma vinheta baixa de uma alta


async def test_start_render_passes_volumes_and_validates_them(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    renderer = StreamRenderer([RenderProgress("running")])
    sent = []
    original = renderer.submit

    async def spy(submission):
        sent.append(submission)
        return await original(submission)

    renderer.submit = spy
    repo, runner = MemoryRenderRepo(), InlineRunner()
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner,
                        RenderMonitor(repo, renderer, 0), assets, store)
    job = await start(uuid4(), None, intro_volume=0.6, outro_volume=1.2, background_volume=0.25, normalize_vignettes=False)
    assert sent[0].background_volume == 0.25  # vai ao ComfyUI (volume_fundo)
    assert (job.intro_volume, job.outro_volume, job.background_volume, job.normalize_vignettes) == (0.6, 1.2, 0.25, False)
    for bad in ({"intro_volume": 2.0}, {"outro_volume": -0.1}, {"background_volume": 1.6}):
        with pytest.raises(InvalidInput, match="volume"):
            await start(uuid4(), None, **bad)

    class OldWorkflow(StreamRenderer):
        def supports_background_volume(self):
            return False

    old = OldWorkflow([RenderProgress("running")])
    start_old = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), old), old, runner, RenderMonitor(repo, old, 0), assets, store)
    with pytest.raises(InvalidInput, match="não tem o volume"):
        await start_old(uuid4(), None, background_volume=0.3)
    await start_old(uuid4(), None)  # sem pedir volume do background, funciona normalmente


async def _remix_setup(tmp_path, *, with_vignettes=True, music_baked=False):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    up = lambda info: UploadRenderAsset(assets, store, FakeProbe(info), 10**7)  # noqa: E731
    intro, outro = await up(GOOD)("intro", "i.mp4", one(b"i")), await up(GOOD)("outro", "o.mp4", one(b"o"))
    song = await up(AUDIO_ONLY)("music", "calma.mp3", one(b"a"))
    out = RenderOutput("final.mp4", "papotechcast")
    renderer = StreamRenderer([RenderProgress("done", out)])
    opened = []
    base_open = renderer.open_output

    async def counting(output):
        opened.append(output)
        return await base_open(output)

    renderer.open_output = counting
    repo, runner, composer = MemoryRenderRepo(), InlineRunner(), FakeComposer()
    finisher = RenderFinisher(repo, assets, renderer, store, composer)
    monitor = RenderMonitor(repo, renderer, 0, finisher=finisher)
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner, monitor, assets, store)
    kw = dict(intro_id=intro.id if with_vignettes else None, music_id=song.id if music_baked else None)
    job = await start(uuid4(), None, kw["intro_id"], None, kw["music_id"], 0.1 if kw["music_id"] else None)
    await runner.drain()
    remix = RemixRender(repo, assets, runner, finisher)
    return repo, runner, composer, remix, opened, job, (intro, outro, song)


async def test_remix_recomposes_with_new_volumes_without_running_comfyui_again(tmp_path):
    repo, runner, composer, remix, opened, job, (intro, outro, song) = await _remix_setup(tmp_path)
    assert repo.data[job.id].main_path and Path(repo.data[job.id].main_path).is_file()  # vídeo da fala guardado
    assert len(opened) == 1 and composer.calls[-1][1] == intro.stored_name

    new = await remix(job.id, intro.id, outro.id, song.id, 0.2, 0.5, 1.4, False)
    await runner.drain()
    saved = repo.data[new.id]
    assert saved.id != job.id and saved.status is JobStatus.DONE and saved.final_path
    assert len(opened) == 1  # NÃO baixou nem rodou o ComfyUI de novo
    assert composer.volumes == (0.5, 1.4, False) and composer.music == (song.stored_name, 0.2)
    assert composer.calls[-1] == (b"MAIN", intro.stored_name, outro.stored_name)
    assert repo.data[job.id].final_path != saved.final_path  # o vídeo anterior continua intacto


async def test_remix_rules_and_validation(tmp_path):
    repo, runner, composer, remix, opened, job, (intro, outro, song) = await _remix_setup(tmp_path)
    with pytest.raises(InvalidInput, match="ao menos uma vinheta"):
        await remix(job.id, None, None, None, None)
    with pytest.raises(InvalidInput, match="volume"):
        await remix(job.id, intro.id, None, None, None, 2.0, 1.0, True)
    with pytest.raises(InvalidInput, match="não encontrada"):
        await remix(job.id, outro.id, None, None, None)  # um 'final' usado como abertura
    from studio.shared.domain.errors import NotFound

    with pytest.raises(NotFound):
        await remix(uuid4(), intro.id, None, None, None)
    from studio.rendering.domain.render_job import RenderJob

    running = RenderJob.create(uuid4(), "b", "r", "e")
    await repo.add(running)
    with pytest.raises(InvalidInput, match="já ficou pronto"):
        await remix(running.id, intro.id, None, None, None)


async def test_remix_cannot_swap_music_that_is_baked_into_the_comfy_video(tmp_path):
    repo, runner, composer, remix, opened, job, (intro, outro, song) = await _remix_setup(tmp_path, with_vignettes=False, music_baked=True)
    assert repo.data[job.id].music_is_baked and repo.data[job.id].status is JobStatus.DONE
    new = await remix(job.id, intro.id, None, None, None)  # só adiciona uma abertura
    await runner.drain()
    assert repo.data[new.id].music_asset_id == song.id and composer.music[0] is None  # trilha segue no vídeo, não é mixada de novo
    assert len(opened) == 1  # baixou a fala uma única vez (primeiro remix)
    assert (await remix(job.id, intro.id, None, song.id, 0.3)).music_asset_id == song.id  # pedido de troca é ignorado, mantém a embutida


async def test_silent_audio_track_is_detected_at_upload(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    loud = await UploadRenderAsset(assets, store, FakeProbe(GOOD, -18.5), 10**7)("intro", "i.mp4", one(b"i"))
    muted = await UploadRenderAsset(assets, store, FakeProbe(GOOD, -91.0), 10**7)("intro", "mudo.mp4", one(b"i"))
    unknown = await UploadRenderAsset(assets, store, FakeProbe(GOOD, None), 10**7)("intro", "x.mp4", one(b"i"))
    noaudio = await UploadRenderAsset(assets, store, FakeProbe(MediaInfo(5, 640, 360, 30, True, False), -91.0), 10**7)("outro", "o.mp4", one(b"o"))
    assert (loud.audio_silent, muted.audio_silent, unknown.audio_silent, noaudio.audio_silent) == (False, True, False, False)
    assert muted.mean_volume_db == -91.0 and noaudio.mean_volume_db is None  # sem faixa de áudio: nem mede


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg não instalado")
async def test_real_ffmpeg_measures_silence_vs_sound(tmp_path):
    ff = _ffmpeg()
    sound, quiet = tmp_path / "som.wav", tmp_path / "mudo.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(sound)], check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", str(quiet)], check=True)
    probe = FfmpegProbe(ff)
    assert -30 < await probe.mean_volume(sound) < -5
    assert await probe.mean_volume(quiet) < -80


# ---- um único áudio de fundo com nível por etapa ----
from studio.infrastructure.media.ffmpeg import music_gain_expression  # noqa: E402


def test_music_gain_expression_constant_and_with_ramps():
    assert music_gain_expression([0.08, 0.08, 0.08], [6, 90, 5]) == "0.08"  # sem variação: número simples
    expr = music_gain_expression([0.5, 0.05, 0.3], [6, 90, 5])
    assert expr.startswith("0.5+(-0.45)*clip((t-5.700)/0.6,0,1)")  # abertura → fala, rampa centrada em 6 s
    assert "+(0.25)*clip((t-95.700)/0.6,0,1)" in expr  # fala → final, rampa centrada em 96 s
    assert "clip(" not in music_gain_expression([0.2, 0.2], [3, 4])  # níveis iguais não geram rampa
    short = music_gain_expression([0.1, 0.4], [0.2, 5])
    assert "/0.2," in short or "/0.05," in short  # rampa nunca maior que a etapa curta


def test_compose_args_use_time_varying_gain_only_when_levels_differ():
    segs = [Segment(Path("i.mp4"), 6, True), Segment(Path("m.mp4"), 90, True), Segment(Path("o.mp4"), 5, True)]
    varied = build_compose_args(segs, Path("o.mp4"), 1280, 720, 30, music=Path("m.mp3"), music_volume=0.05, music_levels=[0.5, 0.05, 0.3])
    graph = varied[varied.index("-filter_complex") + 1]
    assert "volume='0.5+(-0.45)*clip((t-5.700)/0.6,0,1)" in graph and ":eval=frame" in graph
    flat = build_compose_args(segs, Path("o.mp4"), 1280, 720, 30, music=Path("m.mp3"), music_volume=0.05)
    assert "volume=0.05," in flat[flat.index("-filter_complex") + 1] and "eval=frame" not in flat[flat.index("-filter_complex") + 1]


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg não instalado")
async def test_real_ffmpeg_music_level_changes_per_stage(tmp_path):
    ff = _ffmpeg()

    def clip(name, seconds):  # vídeo sem áudio nenhum: só a trilha será ouvida
        path = tmp_path / name
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x180:rate=30",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)
        return path

    intro, main, outro = clip("i.mp4", 4), clip("m.mp4", 6), clip("o.mp4", 4)
    music = tmp_path / "bed.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=3", str(music)], check=True)

    def level(video, start, length):
        r = subprocess.run([ff, "-hide_banner", "-ss", str(start), "-t", str(length), "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                           capture_output=True, text=True)
        return float(next(l for l in r.stderr.splitlines() if "mean_volume" in l).split("mean_volume:")[1].split("dB")[0])

    out = tmp_path / "out.mp4"
    # abertura 50%, fala 5%, final 25%
    await FfmpegVideoComposer(FfmpegProbe(ff), ff).compose(main, intro, outro, out, music, 0.05, 1.0, 1.0, False, 0.5, 0.25)
    in_intro, in_main, in_outro = level(out, 0.5, 2.5), level(out, 5.0, 4.0), level(out, 10.5, 1.5)
    assert 17 < in_intro - in_main < 23  # 0,5 / 0,05 = +20 dB
    assert 11 < in_outro - in_main < 17  # 0,25 / 0,05 ≈ +14 dB (já com o início do fade-out, margem maior)
    assert abs((await FfmpegProbe(ff).probe(out)).duration - 14.0) < 0.4


async def test_stage_levels_reach_final_composition_and_remix(tmp_path):
    store, assets = LocalMediaStore(tmp_path), MemoryAssets()
    up = lambda info: UploadRenderAsset(assets, store, FakeProbe(info), 10**7)  # noqa: E731
    intro, outro = await up(GOOD)("intro", "i.mp4", one(b"i")), await up(GOOD)("outro", "o.mp4", one(b"o"))
    song = await up(AUDIO_ONLY)("music", "calma.mp3", one(b"a"))
    renderer = StreamRenderer([RenderProgress("done", RenderOutput("final.mp4", "papotechcast"))])
    repo, runner, composer = MemoryRenderRepo(), InlineRunner(), FakeComposer()
    finisher = RenderFinisher(repo, assets, renderer, store, composer)
    monitor = RenderMonitor(repo, renderer, 0, finisher=finisher)
    start = StartRender(repo, PreviewRender(Source(script(cut(1, "Abertura do vídeo"))), renderer), renderer, runner, monitor, assets, store)

    job = await start(uuid4(), None, intro.id, outro.id, song.id, 0.05, music_intro_volume=0.5, music_outro_volume=0.25)
    await runner.drain()
    assert composer.music_stages == (0.5, 0.05, 0.25)  # (abertura, fala, final)
    with pytest.raises(InvalidInput, match="trilha na abertura"):
        await start(uuid4(), None, intro.id, outro.id, song.id, 0.05, music_intro_volume=1.5)

    only_intro = await start(uuid4(), None, intro.id, None, song.id, 0.05, music_intro_volume=0.4, music_outro_volume=0.9)
    assert (only_intro.music_intro_volume, only_intro.music_outro_volume) == (0.4, None)  # nível de etapa inexistente é descartado

    remix = RemixRender(repo, assets, runner, finisher)
    new = await remix(job.id, intro.id, outro.id, song.id, 0.1, 1.0, 1.0, True, 0.7, 0.2)
    await runner.drain()
    assert composer.music_stages == (0.7, 0.1, 0.2) and repo.data[new.id].music_intro_volume == 0.7
