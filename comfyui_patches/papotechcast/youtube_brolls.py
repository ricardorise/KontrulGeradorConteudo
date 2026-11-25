import hashlib
import json
import logging
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .pipeline import time_seconds, probe, command, broll_entries, input_file


def youtube_url(value):
    parsed = urlparse(value.strip())
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Informe um link HTTPS de vídeo do YouTube.')
    host = parsed.hostname
    parts = parsed.path.strip('/').split('/')
    if host == 'youtu.be':
        video_id = parts[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
            video_id = parts[1]
        else:
            video_id = ''
    else:
        video_id = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('Use o link de um vídeo, não de um canal ou playlist.')
    return 'https://www.youtube.com/watch?v=' + video_id


def parse_list(text):
    entries = []
    for line, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        parts = [part.strip() for part in raw.split('|')]
        if len(parts) != 4:
            raise ValueError(f'YouTube linha {line}: use URL | início na fonte | fim na fonte | entrada no vídeo final.')
        try:
            url = youtube_url(parts[0])
            start, end, at = [time_seconds(value) for value in parts[1:]]
            if end <= start:
                raise ValueError('O fim do trecho deve ser maior que o início.')
        except ValueError as exc:
            raise ValueError(f'YouTube linha {line}: {exc}') from exc
        entries.append({'url': url, 'start': start, 'end': end, 'at': at})
    return entries


def video_duration(path):
    """Read measured duration; never substitute the requested cut length."""
    info = probe(path)
    videos = [stream for stream in info.get('streams', []) if stream.get('codec_type') == 'video']
    if not videos:
        raise ValueError('O recorte baixado não contém vídeo válido. Confira o intervalo e tente novamente.')
    candidates = [stream.get('duration') for stream in videos] + [info.get('format', {}).get('duration')]
    for value in candidates:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            return duration
    raise ValueError('Não foi possível medir a duração real do recorte após a conversão. O download pode estar vazio ou incompleto.')


def download_clip(entry, height, root):
    if height not in (720, 1080):
        raise ValueError('Resolução de download inválida.')
    root = Path(root).resolve()
    key = hashlib.sha256(json.dumps({'url': entry['url'], 'start': entry['start'], 'end': entry['end'], 'height': height}, sort_keys=True).encode()).hexdigest()[:24]
    directory = (root / 'papotechcast' / 'youtube' / key).resolve()
    if not directory.is_relative_to(root):
        raise ValueError('A pasta de download deve permanecer dentro de input.')
    directory.mkdir(parents=True, exist_ok=True)
    clip = directory / 'broll.mp4'
    source = directory / 'fonte.json'
    length = entry['end'] - entry['start']
    if not math.isfinite(length) or length <= 0:
        raise ValueError('O fim do recorte deve ser maior que o início.')
    if clip.exists() and source.exists():
        try:
            cached_duration = video_duration(clip)
            if cached_duration < length - 0.25:
                raise ValueError('Recorte no cache está incompleto.')
            return clip.relative_to(root).as_posix(), cached_duration
        except (RuntimeError, ValueError):
            logging.getLogger('papotechcast').warning('Cache de B-roll inválido; refazendo somente o recorte: %s', clip.name)
    with tempfile.TemporaryDirectory(prefix='download-', dir=directory) as temporary:
        temporary = Path(temporary)
        args = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist', '--no-progress',
                '--no-js-runtimes', '--js-runtimes', 'node', '--socket-timeout', '30', '--retries', '2',
                '--fragment-retries', '2', '--match-filters', '!is_live',
                '-f', f'bv[ext=mp4][height<={height}]/bv[height<={height}]/b[height<={height}]',
                '--download-sections', f"*{entry['start']}-{entry['end']}", '--force-keyframes-at-cuts',
                '--print', 'after_move:filepath', '-o', str(temporary / 'trecho.%(ext)s'), entry['url']]
        for attempt in range(2):
            current_args = list(args)
            target_dir = temporary
            offset = 0.0
            if attempt:
                # Some YouTube formats yield an empty section despite a successful exit.
                # Download once without remote slicing, then cut locally; keep source temporary.
                target_dir = temporary / 'full'
                target_dir.mkdir()
                index = current_args.index('--download-sections')
                del current_args[index:index + 2]
                current_args.remove('--force-keyframes-at-cuts')
                current_args[current_args.index('-o') + 1] = str(target_dir / 'source.%(ext)s')
                offset = entry['start']
            result = subprocess.run(current_args, capture_output=True, text=True, timeout=1800)
            if result.returncode:
                logging.getLogger('papotechcast').warning('Download YouTube falhou: %s', result.stderr[-1800:])
                raise RuntimeError('Não foi possível baixar o trecho do YouTube. O vídeo pode estar indisponível ou exigir acesso adicional. Consulte os logs do ComfyUI para o diagnóstico.')
            files = [path for path in target_dir.iterdir() if path.suffix in ('.mp4', '.webm', '.mkv', '.mov') and path.name != 'final.mp4']
            if len(files) != 1:
                raise RuntimeError('O download não produziu um único arquivo de vídeo.')
            try:
                info = probe(files[0])
                has_video = any(stream.get('codec_type') == 'video' for stream in info.get('streams', []))
            except RuntimeError:
                has_video = False
            if not has_video:
                if not attempt:
                    logging.getLogger('papotechcast').warning('Recorte remoto sem imagens; tentando download temporário da fonte e corte local.')
                    continue
                raise ValueError('O download veio sem imagens de vídeo, mesmo após nova tentativa. Confira a URL e o intervalo do B-roll.')
            # Fragmented media may have no duration metadata. Finalize the MP4 before measuring.
            normalized = temporary / 'final.mp4'
            command(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(files[0]),
                     '-ss', str(offset), '-t', str(length), '-map', '0:v:0', '-an', '-c:v', 'libx264',
                     '-preset', 'veryfast', '-crf', '20', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1',
                     '-pix_fmt', 'yuv420p', '-threads', '4', '-movflags', '+faststart', str(normalized)])
            try:
                actual = video_duration(normalized)
                if actual < length - 0.25:
                    raise ValueError(f'Trecho solicitado tem {length:g}s, mas o download forneceu apenas {actual:g}s. Confira o intervalo ou tente novamente.')
            except (ValueError, RuntimeError):
                if not attempt:
                    logging.getLogger('papotechcast').warning('Recorte incompleto; tentando corte local a partir da fonte temporária.')
                    continue
                raise
            normalized.replace(clip)
            break
    source.write_text(json.dumps(dict(entry, height=height, duration=actual), ensure_ascii=False, indent=2), encoding='utf-8')
    return clip.relative_to(root).as_posix(), actual


def download_list(text, local, height, root, progress=None):
    entries = parse_list(text)
    lines = [local.strip()] if local and local.strip() else []
    for i, entry in enumerate(entries, 1):
        path, duration = download_clip(entry, height, root)
        lines.append(f"{path} | {entry['at']:g} | {min(duration, entry['end'] - entry['start']):g}")
        logging.getLogger('papotechcast').info('YouTube B-roll %s/%s concluído', i, len(entries))
        if progress:
            progress(i, len(entries))
    return '\n'.join(lines)


def source_reference(value):
    """Parse a registered URL and cut without performing network or disk I/O."""
    parts = [part.strip() for part in value.split('|')]
    url = youtube_url(parts[0])
    if len(parts) == 3:
        start, end = time_seconds(parts[1]), time_seconds(parts[2])
    elif len(parts) == 1:
        fragment = parse_qs(urlparse(parts[0]).fragment).get('t', [''])[0].split(',')
        if len(fragment) != 2:
            raise ValueError('Cadastre o intervalo do YouTube: URL#t=início,fim, ou URL | início | fim.')
        start, end = [time_seconds(part) for part in fragment]
    else:
        raise ValueError('Na lista de recursos use URL | início na fonte | fim na fonte.')
    if end <= start:
        raise ValueError('O fim do trecho deve ser maior que o início.')
    reference = f'{url}#t={start:g},{end:g}'
    return reference, {'url': url, 'start': start, 'end': end}


def prepare_registered_assets(background, brolls, music, reference, root, schedule='', progress=None):
    catalog = [line.strip() for line in brolls.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    registered = {}
    aliases = {}
    local = []
    for line in catalog:
        if line.startswith('https://'):
            key, entry = source_reference(line)
            registered[key] = entry
            if key not in aliases.setdefault(entry['url'], []):
                aliases[entry['url']].append(key)
        else:
            local.append(line)
    if schedule.strip():
        entries = broll_entries(schedule)
    else:
        entries = broll_entries('\n'.join(local)) + [{'path': key, 'at': None, 'duration': None} for key in registered]
    resolved = []
    for index, item in enumerate(entries, 1):
        value = item['path']
        length = item['duration']
        if value.startswith('https://'):
            if urlparse(value).fragment:
                key, source = source_reference(value)
            else:
                candidates = aliases.get(youtube_url(value), [])
                if len(candidates) != 1:
                    raise ValueError('Copie a URL com #t=início,fim da lista de recursos para identificar o recorte.')
                source = registered[candidates[0]]
            path, downloaded_duration = download_clip(source, 1080, root)
            if length is None:
                length = min(downloaded_duration, source['end'] - source['start'])
        else:
            path = value
            if not (Path(root) / path).is_file():
                matches = [entry['path'] for entry in broll_entries('\n'.join(local)) if Path(entry['path']).name == value]
                if len(matches) == 1:
                    path = matches[0]
        resolved.append(dict(item, duration=length, source=input_file(path, root, 'video')))
        if progress:
            progress(index, len(entries))
    return {'background': input_file(background, root, 'video'), 'brolls': resolved,
            'music': input_file(music, root, 'audio') if music.strip() else '',
            'reference': input_file(reference, root, 'audio') if reference.strip() else ''}
