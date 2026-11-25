import asyncio
import json
import os
from pathlib import Path

import folder_paths
from comfy.utils import ProgressBar
from aiohttp import web
from server import PromptServer
from comfy_api.latest import ComfyExtension, io
from . import pipeline, youtube_brolls, resource_management, elevenlabs_tts

WEB_DIRECTORY = './web'
Assets = io.Custom('PAPO_ASSETS')
Narration = io.Custom('PAPO_NARRATION')
PROFILE_FILE = Path.home() / '.config/papotechcast/profiles.json'
PROFILES = json.loads(PROFILE_FILE.read_text()) if PROFILE_FILE.is_file() else {}
VOICE_OPTIONS = ['Descrição livre / referência enviada'] + list(PROFILES)


class PapoAssets(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoAssets', display_name='PapoTechCast • Arquivos', category='PapoTechCast',
                         inputs=[io.String.Input('background', default=''),
                                 io.String.Input('brolls', default='', multiline=True),
                                 io.String.Input('trilha', default=''),
                                 io.String.Input('referencia_voz', default=''),
                                 io.String.Input('brolls_timeline', optional=True, force_input=True, tooltip='Lista: caminho | MM:SS ou frase:trecho único do roteiro | duração opcional. Frases usam WhisperX local no Run. Tem prioridade sobre brolls quando preenchida.')], outputs=[Assets.Output('arquivos')])

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        root = Path(folder_paths.get_input_directory()).resolve()
        values = []
        paths = [(kwargs.get(name) or '') for name in ('background', 'trilha', 'referencia_voz')]
        schedule = kwargs.get('brolls_timeline') or ''
        raw = schedule if schedule.strip() else (kwargs.get('brolls') or '')
        local_lines = '\n'.join(line for line in raw.splitlines() if not line.strip().startswith('https://'))
        paths.extend(entry['path'] for entry in pipeline.broll_entries(local_lines))
        for value in paths:
            if not value.strip():
                continue
            path = (root / value.strip()).resolve()
            if path.is_relative_to(root) and path.is_file():
                stat = path.stat()
                values.append((str(path), stat.st_mtime_ns, stat.st_size))
        return json.dumps(values)

    @classmethod
    def execute(cls, background, brolls, trilha, referencia_voz, brolls_timeline=""):
        progress = ProgressBar(1)
        return io.NodeOutput(youtube_brolls.prepare_registered_assets(background, brolls, trilha, referencia_voz, folder_paths.get_input_directory(), brolls_timeline, progress.update_absolute))


class PapoYouTubeBrolls(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoYouTubeBrolls', display_name='PapoTechCast • Baixar B-rolls YouTube', category='PapoTechCast',
                         inputs=[io.String.Input('lista_youtube', default='', multiline=True, tooltip='Uma linha por trecho: URL | início na fonte | fim na fonte | entrada no vídeo final. Exemplo: https://youtu.be/VIDEO_ID | 00:45 | 00:52 | 01:10'),
                                 io.Combo.Input('resolucao', options=['1080p', '720p']),
                                 io.String.Input('brolls_locais', optional=True, force_input=True)],
                         outputs=[io.String.Output('lista_brolls')])

    @classmethod
    def execute(cls, lista_youtube, resolucao, brolls_locais=''):
        height = {'1080p': 1080, '720p': 720}[resolucao]
        progress = ProgressBar(1)
        value = youtube_brolls.download_list(lista_youtube, brolls_locais, height,
                                             folder_paths.get_input_directory(), progress.update_absolute)
        return io.NodeOutput(value)


class PapoNarration(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoNarration', display_name='PapoTechCast • Narração local / ElevenLabs', category='PapoTechCast',
                         inputs=[io.String.Input('roteiro', force_input=True), Assets.Input('arquivos'),
                                 io.Combo.Input('voz_salva', options=VOICE_OPTIONS),
                                 io.String.Input('descricao_voz', multiline=True, tooltip='Características aceitas pela API, em inglês e separadas por vírgula: male, female, middle-aged, young adult, low pitch, moderate pitch, high pitch, whisper.', default='male, middle-aged, moderate pitch'),
                                 io.String.Input('transcricao_referencia', default='', multiline=True),
                                 io.String.Input('idioma', default='Portuguese'),
                                 io.Int.Input('seed', default=42, min=0, max=2147483647),
                                 io.Combo.Input('provedor', options=['VoiceStudio', 'ElevenLabs'], optional=True),
                                 io.String.Input('voz_elevenlabs', default='', optional=True, tooltip='Escolha pelo botão Vozes ElevenLabs. Vazio usa a voz padrão configurada no servidor.'),
                                 io.Combo.Input('modelo_elevenlabs', options=['eleven_multilingual_v2','eleven_flash_v2_5'], optional=True),
                                 io.Float.Input('estabilidade_elevenlabs', default=0.3, min=0, max=1, step=0.01, optional=True),
                                 io.Float.Input('similaridade_elevenlabs', default=0.73, min=0, max=1, step=0.01, optional=True),
                                 io.Float.Input('velocidade_elevenlabs', default=1.08, min=0.7, max=1.2, step=0.01, optional=True),
                                 io.Float.Input('estilo_elevenlabs', default=0.66, min=0, max=1, step=0.01, optional=True),
                                 io.String.Input('idioma_elevenlabs', default='pt', optional=True, tooltip='Multilingual v2 detecta o idioma pelo texto; outros modelos recebem este código.')],
                         outputs=[Narration.Output('narracao')])

    @classmethod
    def execute(cls, roteiro, arquivos, voz_salva, descricao_voz, transcricao_referencia, idioma, seed,
                provedor='VoiceStudio', voz_elevenlabs='', modelo_elevenlabs='eleven_multilingual_v2',
                estabilidade_elevenlabs=0.3, similaridade_elevenlabs=0.73, velocidade_elevenlabs=1.08,
                estilo_elevenlabs=0.66, idioma_elevenlabs="pt"):
        if provedor == 'ElevenLabs':
            progress = ProgressBar(1)
            return io.NodeOutput(elevenlabs_tts.narrate(roteiro, voz_elevenlabs, modelo_elevenlabs, seed,
                estabilidade_elevenlabs, similaridade_elevenlabs, folder_paths.get_output_directory(), progress.update_absolute,
                speed=velocidade_elevenlabs, style=estilo_elevenlabs, language=idioma_elevenlabs))
        if provedor != 'VoiceStudio':
            raise ValueError('Selecione VoiceStudio ou ElevenLabs.')
        return io.NodeOutput(pipeline.narrate(roteiro, arquivos, PROFILES.get(voz_salva, ''), descricao_voz, transcricao_referencia, idioma, seed, folder_paths.get_output_directory()))


class PapoCaptions(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoCaptions', display_name='PapoTechCast • Legendas automáticas', category='PapoTechCast',
                         inputs=[Narration.Input('narracao'), io.Boolean.Input('ativar', default=True, tooltip='Gera legendas somente para vídeos de até 30 segundos. Vídeos mais longos seguem sem legendas; alinhamento de B-rolls é independente.')],
                         outputs=[io.String.Output('legendas_srt')])

    @classmethod
    def execute(cls, narracao, ativar):
        return io.NodeOutput(pipeline.captions(narracao, ativar))


class PapoRender(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoRender', display_name='PapoTechCast • Montar e renderizar', category='PapoTechCast',
                         inputs=[Assets.Input('arquivos'), Narration.Input('narracao'), io.String.Input('legendas_srt', force_input=True),
                                 io.Combo.Input('formato', options=['YouTube 1080p', 'YouTube 720p', 'Shorts 1080x1920']),
                                 io.Float.Input('intervalo_broll', default=10, min=0.1, max=3600, step=0.5),
                                 io.Float.Input('duracao_broll', default=4, min=0.1, max=3600, step=0.5),
                                 io.Float.Input('volume_trilha', default=0.08, min=0, max=1, step=0.01),
                                 io.Float.Input('volume_fundo', default=0.0, min=0, max=1.5, step=0.01, optional=True, tooltip='Áudio do vídeo de background em loop contínuo sob a narração. Zero desativa.')],
                         outputs=[io.String.Output('video_mp4')])

    @classmethod
    def execute(cls, arquivos, narracao, legendas_srt, formato, intervalo_broll, duracao_broll, volume_trilha, volume_fundo=0.0):
        video = pipeline.render(arquivos, narracao, legendas_srt, formato, intervalo_broll, duracao_broll, volume_trilha, volume_fundo=volume_fundo)
        return io.NodeOutput(video)


class PapoYouTube(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='PapoYouTube', display_name='PapoTechCast • Saída e YouTube', category='PapoTechCast', is_output_node=True,
                         inputs=[io.String.Input('video_mp4', force_input=True),
                                 io.String.Input('titulo', default='PapoTechCast — novo episódio'),
                                 io.String.Input('descricao', multiline=True, default='Episódio do PapoTechCast.'),
                                 io.String.Input('tags', default='tecnologia,podcast,papotechcast'),
                                 io.Combo.Input('privacidade', options=['private', 'unlisted', 'public']),
                                 io.Boolean.Input('conteudo_infantil', default=False),
                                 io.Boolean.Input('midia_sintetica', default=True),
                                 io.Combo.Input('acao', options=['Preparar pacote (sem envio)', 'Enviar ao YouTube'])],
                         outputs=[io.String.Output('resultado')])

    @classmethod
    def execute(cls, video_mp4, titulo, descricao, tags, privacidade, conteudo_infantil, midia_sintetica, acao):
        video = Path(video_mp4).resolve()
        root = Path(folder_paths.get_output_directory()).resolve()
        if not video.is_relative_to(root) or not video.is_file():
            raise ValueError('O vídeo deve ser um arquivo gerado na pasta output do ComfyUI.')
        result = pipeline.youtube_package(str(video), titulo, descricao, tags, privacidade, conteudo_infantil, midia_sintetica, acao)
        relative = video.relative_to(root)
        preview = {'filename': video.name, 'subfolder': str(relative.parent), 'type': 'output'}
        return io.NodeOutput(json.dumps(result, ensure_ascii=False), ui={'text': [json.dumps(result, ensure_ascii=False, indent=2)], 'papo_video': [preview]})


class PapoExtension(ComfyExtension):
    async def get_node_list(self):
        return [PapoAssets, PapoYouTubeBrolls, PapoNarration, PapoCaptions, PapoRender, PapoYouTube]


async def comfy_entrypoint():
    return PapoExtension()


@PromptServer.instance.routes.post('/papotechcast/resources/delete-preview')
async def preview_resource_deletion(request):
    try:
        body = await request.json()
        files = resource_management.deletion_preview(body.get('resource', ''), folder_paths.get_input_directory())
        return web.json_response({'files': files})
    except (ValueError, TypeError, AttributeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)


@PromptServer.instance.routes.post('/papotechcast/resources/delete')
async def delete_video_resource(request):
    try:
        body = await request.json()
        if body.get('confirm') is not True:
            raise ValueError('Confirme a exclusão dos arquivos selecionados.')
        running, pending = PromptServer.instance.prompt_queue.get_current_queue()
        if running or pending:
            return web.json_response({'error': 'Há uma execução ativa ou na fila. Aguarde a conclusão antes de excluir arquivos.'}, status=409)
        deleted = resource_management.delete_resource(body.get('resource', ''), body.get('expected'), folder_paths.get_input_directory())
        return web.json_response({'deleted': deleted})
    except (ValueError, TypeError, AttributeError) as exc:
        return web.json_response({'error': str(exc)}, status=400)
    except OSError:
        return web.json_response({'error': 'Não foi possível excluir o arquivo. Confira as permissões e tente novamente.'}, status=500)


@PromptServer.instance.routes.get('/papotechcast/elevenlabs/status')
async def elevenlabs_status(request):
    settings = elevenlabs_tts.config()
    return web.json_response({'configured': bool(settings.get('api_key')), 'default_voice': settings.get('voice_name','')})


@PromptServer.instance.routes.get('/papotechcast/elevenlabs/voices')
async def elevenlabs_voices(request):
    try:
        voices = await asyncio.to_thread(elevenlabs_tts.list_voices)
        return web.json_response({'voices':voices})
    except (ValueError, RuntimeError) as exc:
        return web.json_response({'error':str(exc)}, status=400)
