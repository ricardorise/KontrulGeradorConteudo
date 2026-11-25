# Integrações

## Hermes (bots)

Os agentes rodam no contêiner `hermes` do servidor. O app chama cada um por **perfil**, sem estado:

```
ssh <usuario@servidor> docker exec -i hermes sh -c 'exec hermes -p <bot> -z "$(cat)"'
```
O prompt vai por **stdin** (sem problema de aspas ou tamanho) e a resposta final volta por stdout. O mesmo caminho é usado pelo `kontrul-api`.

| Bot (perfil) | Papel no app |
|---|---|
| `tonton` | Busca de notícias e Radar de tendências (e cruza fontes) |
| `youtoba` | Pesquisa de vídeos com tração no YouTube para o Radar (não tem aba de chat) |
| `julesverne` | Redação do roteiro |
| `lumiere` | B-roll no YouTube |
| `baru` | Supervisor editorial (chat) |

- Concorrência limitada por `STUDIO_MAX_CONCURRENT_AGENTS` (3) e tempo máximo por `STUDIO_AGENT_TIMEOUT_S` (600 s).
- `hermes -z` aprova ferramentas automaticamente: proteja a API com `STUDIO_API_KEY`/rede confiável.
- Saídas são **JSON** pedido no prompt e validado; o parser tolera texto em volta.

## ComfyUI

URL em `STUDIO_COMFY_URL` (padrão `http://rises:8188`). Workflow **"videos do papotechcast"** no formato API em `backend/src/studio/infrastructure/comfyui/workflows/papotechcast_api.json` (ou o seu export, via `STUDIO_COMFY_WORKFLOW_PATH`).

### O que o app preenche
Os nós são localizados pela **classe e ligação**, não por id:

| Nó | Campo | Valor |
|---|---|---|
| Primitive (ligado a `PapoNarration.roteiro`) | `value` | Parágrafos do roteiro, separados por linha em branco |
| Primitive (ligado a `PapoYouTubeBrolls.brolls_locais`) | `value` | Lista de edição |
| `PapoAssets` | `background` | Caminho relativo à pasta `input` do ComfyUI |
| `PapoAssets` | `trilha` | Caminho da trilha (só quando não há vinhetas) |
| `PapoRender` | `volume_trilha`, `volume_fundo` | Níveis (0–1; 0–1,5) |

Voz (ElevenLabs, seed), formato 720p, legendas e `PapoYouTube.acao = "Preparar pacote (sem envio)"` **não são alterados**.

### Endpoints usados
`POST /prompt` · `GET /history/{id}` · `GET /queue` · `GET /object_info/…` · `POST /upload/image` (`type=input`, `subfolder=papotechcast`) · `HEAD`/`GET /view`.

- Uploads vão para `input/papotechcast/` como `fundo-<id>.ext` e `trilha-<id>.ext`. Antes de subir, um `HEAD /view` compara nome e tamanho para **não reenviar** arquivos grandes.
- O MP4 final é achado na saída do workflow (objeto `{filename, subfolder}` ou caminho em texto) e baixado por `GET /view`.

### Regenerar o workflow no formato API
Quando o workflow visual muda (nova entrada, nó novo):
```bash
cd backend
python scripts/convert_workflow.py "videos do papotechcast.json" > src/studio/infrastructure/comfyui/workflows/papotechcast_api.json
```
O conversor consulta `/object_info` do servidor para mapear os widgets e falha se faltar algum campo obrigatório.

### Alinhamento por frase (WhisperX)
O nó `PapoRender` posiciona cada B-roll buscando a **frase** na transcrição do áudio. A comparação exata falha quando a transcrição troca palavras ou escreve números como dígitos. Em `comfyui_patches/papotechcast/` estão a versão **tolerante** do alinhador (normaliza números, similaridade de sequência, desempate por posição, confiança mínima), seus testes e o prompt entregue ao agente do ComfyUI. A versão efetivamente instalada no servidor deve ser conferida lá.

Por isso o app **bloqueia** trechos com número ou símbolo e exige frase única no roteiro.

## ffmpeg (montagem final)

Feita **no app**, depois que o ComfyUI termina:
1. Baixa o MP4 da fala e guarda em disco (permite o *Remixar*).
2. Concatena **abertura → fala → final**, normalizando resolução, fps e áudio (estéreo 48 kHz) pelo vídeo da fala; vinhetas sem áudio recebem silêncio.
3. Opcional: nivela o loudness das vinhetas (-16 LUFS) e aplica o ganho; mixa **uma trilha** em loop sobre o vídeo todo, com nível por etapa (rampa de 0,6 s) e fade-out de 2 s.

Sem `ffmpeg` no PATH, use `STUDIO_FFMPEG`. O pacote de desenvolvimento `imageio-ffmpeg` traz um binário estático para testes.

## YouTube
O app só usa links e o player oficial incorporado (IFrame API, domínio `youtube-nocookie.com`). Nenhum vídeo do YouTube é baixado pelo app — o download e o recorte acontecem **dentro do workflow do ComfyUI**, durante a execução.
