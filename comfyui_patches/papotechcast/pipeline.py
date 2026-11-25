import json
import logging
import math
import os
import re
import subprocess
import textwrap
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests


def command(args, timeout=7200):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name}: {result.stderr[-2500:]}')
    return result.stdout


def probe(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))


def input_file(value, root, kind):
    root = Path(root).resolve()
    path = (root / value.strip()).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f'{kind}: envie o arquivo pelo botão de upload ou informe um caminho relativo à pasta input.')
    info = probe(path)
    if not any(s['codec_type'] == kind for s in info['streams']):
        raise ValueError(f'O arquivo {path.name} não contém {kind}.')
    return str(path)


def time_seconds(value):
    value = value.strip().replace(',', '.')
    if not re.fullmatch(r'\d+(?::\d{1,2}){0,2}(?:\.\d+)?', value):
        raise ValueError('Use segundos, MM:SS ou HH:MM:SS, com fração opcional.')
    parts = value.split(':')
    if any(float(part) >= 60 for part in parts[1:]):
        raise ValueError('Minutos e segundos após os dois-pontos devem ser menores que 60.')
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    if not math.isfinite(seconds):
        raise ValueError('O tempo deve ser finito.')
    return seconds


def broll_entries(text):
    entries = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        parts = [part.strip() for part in raw.split('|')]
        if len(parts) == 1:
            entries.append({'path': parts[0], 'at': None, 'duration': None})
            continue
        if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
            raise ValueError(f'B-roll linha {number}: use caminho | entrada | duração opcional.')
        # Both path-first and time-first forms are accepted.
        if re.fullmatch(r'\d+(?::\d{1,2}){0,2}(?:[.,]\d+)?', parts[0]):
            when, path = parts[:2]
        else:
            path, when = parts[:2]
        # Textual anchors may be entered directly, without a mandatory prefix.
        explicit_phrase = when.lower().startswith('frase:')
        is_phrase = explicit_phrase or (when.lower() not in ('nan', 'inf', 'infinity') and any(c.isalpha() for c in when) and not re.match(r'^\d+[\d:.,]*', when))
        try:
            at = None if is_phrase else time_seconds(when)
            length = time_seconds(parts[2]) if len(parts) == 3 and parts[2] else None
            if length is not None and length <= 0:
                raise ValueError('A duração deve ser maior que zero.')
        except ValueError as exc:
            raise ValueError(f'B-roll linha {number}: {exc}') from exc
        entry = {'path': path, 'at': at, 'duration': length}
        if is_phrase:
            entry['phrase'] = when[6:].strip() if explicit_phrase else when.strip()
            if not entry['phrase']:
                raise ValueError('Preencha a frase de referência.')
        entries.append(entry)
    if any(e['at'] is None and not e.get('phrase') for e in entries) and any(e['at'] is not None or e.get('phrase') for e in entries):
        raise ValueError('Informe o momento de entrada de todos os B-rolls da lista temporizada.')
    return entries


def prepare_assets(background, brolls, music, reference, root, brolls_timeline=''):
    entries = broll_entries(brolls_timeline if brolls_timeline.strip() else brolls)
    return {
        'background': input_file(background, root, 'video'),
        'brolls': [dict(entry, source=input_file(entry['path'], root, 'video')) for entry in entries],
        'music': input_file(music, root, 'audio') if music.strip() else '',
        'reference': input_file(reference, root, 'audio') if reference.strip() else '',
    }


def voice_request(route, data=None, files=None):
    key = os.environ.get('PAPOTECH_VOICE_KEY', '')
    if not key:
        raise RuntimeError('Chave do VoiceStudio ausente na configuração do serviço ComfyUI.')
    headers = {'Authorization': f'Bearer {key}'}
    try:
        response = requests.post('http://127.0.0.1:3900' + route, headers=headers,
                                 data=data, files=files, timeout=(15, 3600))
    except requests.RequestException as exc:
        raise RuntimeError('Não foi possível concluir a chamada ao VoiceStudio local.') from exc
    if not response.ok:
        raise RuntimeError(f'VoiceStudio {route}: HTTP {response.status_code}: {response.text[:1500]}')
    return response


def narrate(script, assets, profile, description, reference_text, language, seed, output_root):
    if not script.strip():
        raise ValueError('Preencha o roteiro antes de executar.')
    run = Path(output_root) / 'papotechcast' / uuid.uuid4().hex[:12]
    run.mkdir(parents=True)
    (run / 'roteiro.txt').write_text(script, encoding='utf-8')
    data = dict(text=script, language=language, instruct=description, seed=str(seed),
                num_step='32', effect_preset='broadcast', stream='false', max_chunk_chars='800')
    if profile.strip() and not assets['reference']:
        data['profile_id'] = profile.strip()
    reference = assets['reference']
    if reference:
        with open(reference, 'rb') as f:
            if not reference_text.strip():
                transcript = voice_request('/transcribe', data={'mode': 'fast'},
                                           files={'audio': (Path(reference).name, f, 'audio/wav')}).json()
                reference_text = transcript.get('text', '').strip()
            if not reference_text:
                raise RuntimeError('O áudio de referência não produziu transcrição; preencha a transcrição da referência.')
        data['ref_text'] = reference_text
        with open(reference, 'rb') as f:
            response = voice_request('/generate', data=data, files={'ref_audio': (Path(reference).name, f, 'audio/wav')})
    else:
        response = voice_request('/generate', data=data)
    if int(response.headers.get('X-OmniVoice-Dropped-Chunks', '0')):
        raise RuntimeError('VoiceStudio omitiu trechos do roteiro. Revise o roteiro e tente novamente.')
    audio = run / 'narracao.wav'
    audio.write_bytes(response.content)
    duration = float(probe(audio)['format']['duration'])
    if duration <= 0:
        raise RuntimeError('VoiceStudio retornou áudio vazio.')
    return {'audio': str(audio), 'run': str(run), 'duration': duration}


def timestamp(seconds):
    millis = max(0, round(seconds * 1000))
    h, millis = divmod(millis, 3600000)
    m, millis = divmod(millis, 60000)
    s, millis = divmod(millis, 1000)
    return f'{h:02}:{m:02}:{s:02},{millis:03}'


def subtitle_cues(result, duration):
    cues = []
    for segment in result.get('segments', []):
        text = re.sub(r'\s+', ' ', str(segment.get('text', ''))).strip()
        start = max(0.0, float(segment.get('start', 0)))
        end = min(duration, float(segment.get('end', duration)))
        if not text or end <= start:
            continue
        # Long ASR segments are divided into readable cues using their words' timing
        # where available, otherwise a proportional split within that segment.
        words = segment.get('words') or []
        timed = [w for w in words if 'start' in w and 'end' in w and w.get('word', '').strip()]
        if len(timed) == len(words) and timed:
            batch = []
            for word in timed:
                batch.append(word)
                if len(' '.join(w['word'].strip() for w in batch)) >= 60 or float(word['end']) - float(batch[0]['start']) >= 4:
                    cues.append((max(start, float(batch[0]['start'])), min(end, float(word['end'])), ' '.join(w['word'].strip() for w in batch)))
                    batch = []
            if batch:
                cues.append((max(start, float(batch[0]['start'])), end, ' '.join(w['word'].strip() for w in batch)))
        else:
            parts = textwrap.wrap(text, width=72, break_long_words=False, break_on_hyphens=False)
            total = sum(len(p) for p in parts)
            pos = start
            for part in parts:
                finish = pos + (end - start) * len(part) / total
                cues.append((pos, finish, part))
                pos = finish
    if not cues:
        raise RuntimeError('O transcritor não retornou segmentos temporizados para as legendas.')
    return cues


def captions(narration, enabled):
    if not enabled:
        return ''
    run = Path(narration['run'])
    duration = float(probe(narration['audio'])['format']['duration'])
    if duration > 30:
        logging.getLogger('papotechcast').info('Legendas ignoradas: áudio de %.2fs excede o limite de 30s para vídeos curtos.', duration)
        return ''
    with open(narration['audio'], 'rb') as f:
        result = voice_request('/transcribe', data={'mode': 'fast', 'refine': 'false'},
                               files={'audio': ('narracao.wav', f, 'audio/wav')}).json()
    (run / 'transcricao.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    cues = subtitle_cues(result, duration)
    text = '\n\n'.join(f'{i}\n{timestamp(start)} --> {timestamp(end)}\n' + '\n'.join(textwrap.wrap(text.replace('-->', '→'), 38, break_long_words=False))
                       for i, (start, end, text) in enumerate(cues, 1))
    path = run / 'legendas.srt'
    path.write_text(text + '\n', encoding='utf-8')
    return str(path)


def timeline(assets, duration, interval, broll_duration):
    if not math.isfinite(interval) or not math.isfinite(broll_duration) or interval <= 0 or broll_duration <= 0:
        raise ValueError('Intervalo e duração dos B-rolls devem ser positivos e finitos.')
    entries = [dict(source=entry, at=None, duration=None) if isinstance(entry, str) else entry for entry in assets['brolls']]
    scheduled = bool(entries) and entries[0]['at'] is not None
    if scheduled:
        entries = sorted(entries, key=lambda entry: entry['at'])
    events = []
    cursor = 0.0
    for index, entry in enumerate(entries):
        start = entry['at'] if scheduled else min(duration, cursor + interval)
        if scheduled and start >= duration:
            raise ValueError(f"B-roll {Path(entry['source']).name}: entrada em {start:g}s após o fim da narração ({duration:g}s).")
        if scheduled and start < cursor - 1e-8:
            raise ValueError(f"B-roll {Path(entry['source']).name}: entrada em {start:g}s sobrepõe o B-roll anterior, que termina em {cursor:g}s. Ajuste a duração.")
        if start > cursor:
            events.append({'source': assets['background'], 'start': cursor, 'duration': start - cursor, 'kind': 'background'})
        if start >= duration:
            cursor = start
            break
        end = min(duration, start + (entry['duration'] if entry['duration'] is not None else broll_duration))
        event = {'source': entry['source'], 'start': start, 'duration': end - start, 'kind': 'broll'}
        if scheduled and entry.get('phrase') and index + 1 < len(entries):
            next_start = entries[index + 1]['at']
            if next_start < end - 1e-8:
                if next_start <= start + 1e-8:
                    raise ValueError(f"B-rolls com entrada simultânea em {start:g}s. Escolha frases de referência distintas ou ajuste os horários.")
                event.update(duration=next_start - start, requested_duration=end - start,
                             trim_reason='next_broll_start', next_broll_at=next_start)
                logging.getLogger('papotechcast').info(
                    'B-roll por frase reduzido de %.3fs para %.3fs para respeitar a próxima entrada em %.3fs: %s',
                    end - start, next_start - start, next_start, entry['phrase'])
                end = next_start
        events.append(event)
        cursor = end
    if cursor < duration:
        events.append({'source': assets['background'], 'start': cursor, 'duration': duration - cursor, 'kind': 'background'})
    return events


def render(assets, narration, srt, format_name, interval, broll_duration, music_volume, volume_fundo=0.0):
    try:
        valid_volume = math.isfinite(volume_fundo) and 0 <= volume_fundo <= 1.5
    except TypeError:
        valid_volume = False
    if not valid_volume:
        raise ValueError('volume_fundo deve ser finito e estar entre 0 e 1,5.')
    mix_background = False
    if volume_fundo > 0:
        mix_background = any(stream.get('codec_type') == 'audio' for stream in probe(assets['background']).get('streams', []))
        if not mix_background:
            logging.getLogger('papotechcast').warning('volume_fundo ignorado: o vídeo de background não possui faixa de áudio.')
    dimensions = {'YouTube 1080p': (1920, 1080), 'YouTube 720p': (1280, 720), 'Shorts 1080x1920': (1080, 1920)}
    if format_name not in dimensions:
        raise ValueError('Formato de vídeo inválido.')
    width, height = dimensions[format_name]
    run = Path(narration['run'])
    if any(isinstance(e, dict) and e.get('phrase') for e in assets['brolls']):
        from .phrase_alignment import resolve
        assets = resolve(assets, narration)
    # Clip each insertion to the actual source; return to background afterwards.
    entries = []
    for entry in assets['brolls']:
        entry = dict(entry) if not isinstance(entry, str) else dict(source=entry, at=None, duration=None)
        source_duration = float(probe(entry['source'])['format']['duration'])
        requested = entry['duration'] if entry['duration'] is not None else (source_duration if entry.get('phrase') else broll_duration)
        entry['duration'] = min(requested, source_duration)
        entries.append(entry)
    assets = dict(assets, brolls=entries)
    events = timeline(assets, narration['duration'], interval, broll_duration)
    (run / 'timeline.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
    clips = []
    total_frames = math.ceil(narration['duration'] * 30)
    done_frames = 0
    for i, event in enumerate(events):
        end_frame = total_frames if i == len(events) - 1 else round((event['start'] + event['duration']) * 30)
        frames = end_frame - done_frames
        if frames <= 0:
            continue
        part = run / f'cena_{i:04}.mp4'
        vf = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,format=yuv420p'
        # Continue the background's clock when returning from a B-roll.
        offset = event['start'] % float(probe(event['source'])['format']['duration']) if event['kind'] == 'background' else 0
        command(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *(['-stream_loop', '-1'] if event['kind'] == 'background' else []), '-ss', str(offset),
                 '-i', event['source'], '-vf', vf, '-frames:v', str(frames), '-an', '-c:v', 'libx264',
                 '-preset', 'veryfast', '-crf', '20', '-threads', '4', str(part)])
        clips.append(part)
        done_frames = end_frame
    concat = run / 'cenas.txt'
    concat.write_text(''.join(f"file '{p.name}'\n" for p in clips), encoding='utf-8')
    base = run / 'montagem.mp4'
    command(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat), '-c', 'copy', str(base)])
    output = run / 'video_final.mp4'
    args = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(base), '-i', narration['audio']]
    if mix_background:
        filters = ['[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,asetpts=PTS-STARTPTS[voice]']
        inputs = ['[voice]']
        next_input = 2
        if assets['music']:
            args += ['-stream_loop', '-1', '-i', assets['music']]
            filters.append(f'[{next_input}:a]volume={music_volume}[music]')
            inputs.append('[music]')
            next_input += 1
        # Independent input: sound starts at zero and continues under every B-roll.
        args += ['-stream_loop', '-1', '-i', assets['background']]
        filters.append(f'[{next_input}:a:0]asetpts=PTS-STARTPTS,volume={volume_fundo},atrim=duration={narration["duration"]}[background]')
        inputs.append('[background]')
        filters.append(''.join(inputs) + f'amix=inputs={len(inputs)}:duration=first:normalize=0[a]')
        args += ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[a]']
    elif assets['music']:
        args += ['-stream_loop', '-1', '-i', assets['music'], '-filter_complex',
                 f'[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice];[2:a]volume={music_volume}[music];[voice][music]amix=inputs=2:duration=first:normalize=0[a]', '-map', '0:v:0', '-map', '[a]']
    else:
        args += ['-map', '0:v:0', '-map', '1:a:0', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11']
    if srt:
        # Caption paths are generated internally; none come from free text.
        args += ['-vf', f"subtitles=filename='{srt}':force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,MarginV=35'",
                 '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-threads', '4']
    else:
        args += ['-c:v', 'copy']
    args += ['-c:a', 'aac', '-b:a', '192k', '-t', str(narration['duration']), '-movflags', '+faststart', str(output)]
    command(args)
    info = probe(output)
    if not any(s['codec_type'] == 'video' for s in info['streams']) or not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise RuntimeError('O arquivo final não contém vídeo e áudio.')
    # Remove only intermediate files owned by this successful render.
    for path in clips + [base, concat]:
        path.unlink()
    return str(output)


def youtube_package(video, title, description, tags, privacy, made_for_kids, synthetic_media, action):
    if privacy not in ('private', 'unlisted', 'public'):
        raise ValueError('Privacidade inválida.')
    if not title.strip() or len(title) > 100:
        raise ValueError('O título do YouTube deve ter entre 1 e 100 caracteres.')
    if len(description) > 5000:
        raise ValueError('A descrição do YouTube deve ter até 5000 caracteres.')
    path = Path(video)
    metadata = {'snippet': {'title': title, 'description': description, 'tags': [t.strip() for t in tags.split(',') if t.strip()], 'categoryId': '28'},
                'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': made_for_kids, 'containsSyntheticMedia': synthetic_media}}
    metadata_file = path.parent / 'youtube-metadata.json'
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    if action == 'Preparar pacote (sem envio)':
        return {'status': 'Pacote pronto; nenhum envio realizado.', 'video': video, 'metadata': str(metadata_file)}
    if action != 'Enviar ao YouTube':
        raise ValueError('Ação de publicação inválida.')
    receipt = path.parent / 'youtube-upload.json'
    if receipt.exists():
        return json.loads(receipt.read_text(encoding='utf-8'))
    credentials = Path(os.environ.get('PAPOTECH_YOUTUBE_CREDENTIALS', str(Path.home() / '.config/papotechcast/youtube-oauth.json')))
    if not credentials.is_file():
        raise RuntimeError('Vídeo e metadados prontos. Falta conectar o canal YouTube via OAuth; use Preparar pacote até concluir a conexão.')
    oauth = json.loads(credentials.read_text(encoding='utf-8'))
    response = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': oauth['client_id'], 'client_secret': oauth['client_secret'],
        'refresh_token': oauth['refresh_token'], 'grant_type': 'refresh_token'}, timeout=30)
    if not response.ok:
        raise RuntimeError('YouTube: não foi possível renovar a autorização do canal.')
    token = response.json()['access_token']
    size = path.stat().st_size
    headers = {'Authorization': 'Bearer ' + token, 'X-Upload-Content-Length': str(size), 'X-Upload-Content-Type': 'video/mp4'}
    session_file = path.parent / '.youtube-session.json'
    if session_file.exists():
        session = json.loads(session_file.read_text())
        if session['metadata'] != metadata:
            raise RuntimeError('Há um envio pendente com outros metadados. Conclua ou revise esse envio antes de alterar os dados.')
        upload_url = session['url']
    else:
        response = requests.post('https://www.googleapis.com/upload/youtube/v3/videos', params={'uploadType': 'resumable', 'part': 'snippet,status'},
                                 headers=headers, json=metadata, timeout=60)
        if not response.ok:
            raise RuntimeError(f'YouTube: não foi possível iniciar o envio (HTTP {response.status_code}).')
        upload_url = response.headers['Location']
        session_file.write_text(json.dumps({'url': upload_url, 'metadata': metadata}))
        session_file.chmod(0o600)
    if urlparse(upload_url).scheme != 'https' or urlparse(upload_url).hostname != 'www.googleapis.com':
        raise ValueError('Endereço de sessão de upload inválido.')
    response = requests.put(upload_url, headers={'Authorization': 'Bearer ' + token, 'Content-Range': f'bytes */{size}', 'Content-Length': '0'}, timeout=60)
    if response.status_code == 308:
        position = int(response.headers['Range'].split('-')[-1]) + 1 if 'Range' in response.headers else 0
        with path.open('rb') as f:
            f.seek(position)
            while position < size:
                content = f.read(8 * 1024 * 1024)
                end = position + len(content) - 1
                response = requests.put(upload_url, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'video/mp4', 'Content-Range': f'bytes {position}-{end}/{size}'}, data=content, timeout=300)
                if response.status_code not in (200, 201, 308):
                    raise RuntimeError(f'YouTube: envio interrompido (HTTP {response.status_code}); execute novamente para retomar.')
                position = end + 1
    if response.status_code not in (200, 201):
        raise RuntimeError(f'YouTube: sessão de envio indisponível (HTTP {response.status_code}).')
    result = response.json()
    report = {'status': 'Enviado ao YouTube', 'url': 'https://www.youtube.com/watch?v=' + result['id'], 'privacy': privacy}
    receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
