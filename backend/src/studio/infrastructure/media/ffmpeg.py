import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from studio.rendering.application.ports import MediaError, MediaInfo

_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\d+:\d+[^:]*: Video:.*?, (\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"(\d+(?:\.\d+)?) fps")


def parse_media_info(stderr: str) -> MediaInfo:
    """Lê duração, resolução, fps e presença de áudio da saída de `ffmpeg -i arquivo`."""
    duration = _DURATION.search(stderr)
    video = _VIDEO.search(stderr)
    fps = _FPS.search(stderr)
    h, m, s = (float(x) for x in duration.groups()) if duration else (0, 0, 0)
    return MediaInfo(
        duration=round(h * 3600 + m * 60 + s, 3),
        width=int(video.group(1)) if video else 0,
        height=int(video.group(2)) if video else 0,
        fps=float(fps.group(1)) if fps else 30.0,
        has_video=video is not None,
        has_audio=bool(re.search(r"Stream #\d+:\d+[^:]*: Audio:", stderr)),
    )


async def _run(args: list[str], timeout: float) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except OSError as exc:
        raise MediaError(f"ffmpeg indisponível: {exc}") from exc
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError("o ffmpeg demorou demais") from None
    return proc.returncode or 0, err.decode(errors="replace")


class FfmpegProbe:
    def __init__(self, ffmpeg: str = "ffmpeg"):
        self._ffmpeg = ffmpeg

    async def mean_volume(self, path: Path) -> float | None:
        try:
            _, stderr = await _run([self._ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], 300)
        except MediaError:
            return None
        found = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", stderr)
        return float(found.group(1)) if found else None

    async def probe(self, path: Path) -> MediaInfo:
        _, stderr = await _run([self._ffmpeg, "-hide_banner", "-i", str(path)], 60)  # sem saída => retorna 1, é normal
        info = parse_media_info(stderr)
        if not info.has_video and "Invalid data" in stderr:
            raise MediaError("arquivo de vídeo inválido ou corrompido")
        return info


@dataclass(frozen=True)
class Segment:
    path: Path
    duration: float
    has_audio: bool
    gain: float = 1.0  # ajuste de volume do usuário (1 = como está)
    normalize: bool = False  # nivela o loudness (-16 LUFS, igual à fala) antes do ganho


FADE_OUT_SECONDS = 2.0
MUSIC_RAMP_SECONDS = 0.6  # transição do nível da trilha entre etapas


def music_gain_expression(levels: list[float], durations: list[float], ramp: float = MUSIC_RAMP_SECONDS) -> str:
    """Ganho da trilha ao longo do tempo: nível constante em cada etapa e rampa linear nas fronteiras.

    g(t) = L0 + Σ (L[i+1] − L[i]) · clip((t − (B[i] − r/2)) / r, 0, 1),  B[i] = fim da etapa i.
    Devolve um número simples quando todas as etapas têm o mesmo nível.
    """
    if len(set(levels)) == 1:
        return f"{levels[0]:g}"
    shortest = min(durations[:-1]) if len(durations) > 1 else ramp
    r = max(min(ramp, shortest), 0.05)
    expr, boundary = f"{levels[0]:g}", 0.0
    for i in range(len(levels) - 1):
        boundary += durations[i]
        delta = levels[i + 1] - levels[i]
        if delta:
            expr += f"+({delta:g})*clip((t-{boundary - r / 2:.3f})/{r:g},0,1)"
    return expr


def build_compose_args(
    segments: list[Segment], dest: Path, width: int, height: int, fps: float, ffmpeg: str = "ffmpeg",
    music: Path | None = None, music_volume: float = 0.08, music_levels: list[float] | None = None,
) -> list[str]:  # fmt: skip
    """Concatena os segmentos num MP4 único, normalizando resolução, fps e áudio (estéreo 48 kHz).

    Segmentos sem áudio recebem silêncio da mesma duração para não dessincronizar a concatenação.
    """
    inputs: list[str] = []
    filters: list[str] = []
    index = 0
    for n, seg in enumerate(segments):
        inputs += ["-i", str(seg.path)]
        video_index = index
        index += 1
        filters.append(
            f"[{video_index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps:g},format=yuv420p[v{n}]"
        )
        if seg.has_audio:
            chain = f"[{video_index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            if seg.normalize:
                chain += ",loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"
            if seg.gain != 1.0:
                chain += f",volume={seg.gain:g}"
            filters.append(f"{chain}[a{n}]")
        else:
            inputs += ["-f", "lavfi", "-t", f"{seg.duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            filters.append(f"[{index}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a{n}]")
            index += 1
    joined = "".join(f"[v{n}][a{n}]" for n in range(len(segments)))
    total = sum(seg.duration for seg in segments)
    tail: list[str] = []
    if music is None:
        filters.append(f"{joined}concat=n={len(segments)}:v=1:a=1[v][a]")
    else:  # a trilha cobre o vídeo todo (abertura + fala + final) e some em fade-out no fim
        filters.append(f"{joined}concat=n={len(segments)}:v=1:a=1[v][voice]")
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        fade_start = max(total - FADE_OUT_SECONDS, 0)
        levels = music_levels or [music_volume] * len(segments)  # um nível por etapa (abertura, fala, final)
        gain = music_gain_expression(levels, [seg.duration for seg in segments])
        volume = f"volume={gain}" if len(set(levels)) == 1 else f"volume='{gain}':eval=frame"
        filters.append(
            f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,{volume},"
            f"afade=t=out:st={fade_start:.3f}:d={min(FADE_OUT_SECONDS, total):.3f}[bed]"
        )
        filters.append("[voice][bed]amix=inputs=2:duration=first:normalize=0[a]")
        tail = ["-t", f"{total:.3f}"]  # a trilha em loop é infinita: corta no tamanho do vídeo
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[a]", *tail, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest),
    ]  # fmt: skip


class FfmpegVideoComposer:
    def __init__(self, probe: FfmpegProbe, ffmpeg: str = "ffmpeg", timeout_s: float = 3600):
        self._probe, self._ffmpeg, self._timeout = probe, ffmpeg, timeout_s

    async def compose(
        self, main: Path, intro: Path | None, outro: Path | None, dest: Path,
        music: Path | None = None, music_volume: float = 0.08,
        intro_volume: float = 1.0, outro_volume: float = 1.0, normalize: bool = True,
        music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> None:  # fmt: skip
        main_info = await self._probe.probe(main)
        if not main_info.has_video:
            raise MediaError("o vídeo da narração não tem imagem")
        segments: list[Segment] = []
        levels: list[float] = []
        for path, gain, leveled, level in ((intro, intro_volume, normalize, music_intro_volume), (main, 1.0, False, music_volume), (outro, outro_volume, normalize, music_outro_volume)):
            if path is None:
                continue
            info = main_info if path == main else await self._probe.probe(path)
            segments.append(Segment(path, info.duration, info.has_audio, gain, leveled))
            levels.append(music_volume if level is None else level)
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(".partial.mp4")
        args = build_compose_args(segments, partial, main_info.width, main_info.height, main_info.fps or 30, self._ffmpeg,
                                  music, music_volume, levels)
        code, stderr = await _run(args, self._timeout)
        if code != 0:
            partial.unlink(missing_ok=True)
            raise MediaError(f"ffmpeg falhou: {stderr.strip()[-400:]}")
        partial.replace(dest)  # só aparece pronto quando termina
