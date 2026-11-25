def render(assets, narration, srt, format_name, interval, broll_duration, music_volume):
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
    if assets['music']:
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
