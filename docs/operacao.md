# Operação

## Variáveis de ambiente (backend)

| Variável | Padrão | Para quê |
|---|---|---|
| `STUDIO_DATABASE_URL` | — (obrigatória) | `postgresql://usuario:senha@host:5432/banco` |
| `STUDIO_RUN_MIGRATIONS` | `true` | Aplica as migrações ao subir |
| `STUDIO_HERMES_SSH` | vazio | `usuario@servidor` para chamar o Hermes por SSH; vazio = docker local |
| `STUDIO_HERMES_SSH_KEY` | vazio | Chave SSH (use o `known_hosts` da mesma pasta) |
| `STUDIO_HERMES_CONTAINER` | `hermes` | Nome do contêiner do Hermes |
| `STUDIO_AGENT_TIMEOUT_S` | `600` | Tempo máximo por chamada a um bot |
| `STUDIO_MAX_CONCURRENT_AGENTS` | `3` | Chamadas simultâneas aos bots |
| `STUDIO_COMFY_URL` | `http://rises:8188` | ComfyUI |
| `STUDIO_COMFY_WORKFLOW_PATH` | embutido | Workflow API alternativo |
| `STUDIO_COMFY_POLL_INTERVAL_S` | `4` | Intervalo de consulta ao `/history` |
| `STUDIO_MEDIA_DIR` | `./data/media` | Uploads e vídeos montados |
| `STUDIO_MAX_UPLOAD_MB` | `2048` | Limite de upload |
| `STUDIO_FFMPEG` | `ffmpeg` | Binário do ffmpeg |
| `STUDIO_API_KEY` | vazio | Se definida, exige `X-API-Key` |
| `STUDIO_CORS_ORIGINS` | vazio | Origens extras (lista separada por vírgula) |

Modelos prontos: `backend/.env.example` e `.env.example` (deploy). **Nunca versione o `.env`** (já está no `.gitignore`).

## Rodar em desenvolvimento

O PostgreSQL só existe na rede Docker do servidor; use um túnel SSH.

```bash
# 1) túnel até o banco (ajuste o IP do contêiner kontrul-postgres-1)
ssh -f -N -L 15433:<ip-do-postgres>:5432 usuario@servidor

# 2) backend
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env     # STUDIO_DATABASE_URL=postgresql://sofia:<senha>@127.0.0.1:15433/sofia
                         # STUDIO_HERMES_SSH=usuario@servidor
set -a; . ./.env; set +a
.venv/bin/uvicorn studio.bootstrap:create_app --factory --port 8100

# 3) frontend (proxy /api -> :8100)
cd ../frontend && npm install && npm run dev      # http://localhost:5173
```
Se o túnel cair, o backend perde o banco e para de responder: recrie o túnel e reinicie.

## Testes

```bash
cd backend  && .venv/bin/pytest          # 100+ testes; usa ffmpeg real (do sistema ou do imageio-ffmpeg)
cd frontend && npm test && npx tsc --noEmit
```
Cobrem domínio, casos de uso (com fakes), adaptadores (Hermes, ComfyUI simulado, ffmpeg real) e a interface.

## Deploy (Docker Compose)

```bash
cp .env.example .env    # STUDIO_DB_PASSWORD, STUDIO_API_KEY (recomendado), STUDIO_COMFY_URL, STUDIO_WEB_BIND/PORT
docker compose up -d --build
```
- `studio-api`: backend, imagem com `ffmpeg` e cliente SSH; usuário `1000:1000`; monta a chave SSH do Hermes (somente leitura) e o volume `studio-media`.
- `studio-web`: nginx com o frontend e proxy de `/api` (injeta `X-API-Key`, aceita uploads de até 2 GB). Porta padrão `127.0.0.1:8795`.
- Ambos entram na rede `kontrul_core` para alcançar o PostgreSQL pelo nome `postgres`.

## Limitações conhecidas

- **YouTube bloqueia o IP do servidor** para transcrições (pausa de ~15 min): a Lumière devolve cenas sem horário ou falha; use **Rebuscar B-roll**.
- **Alinhamento por frase** depende do WhisperX: trechos com número/símbolo ou repetidos são bloqueados antes do envio.
- **Custo e tempo:** cada envio ao ComfyUI usa GPU e créditos da ElevenLabs (a narração igual vem do cache).
- **Trilha sem vinhetas** fica embutida no vídeo do ComfyUI e não pode ser trocada no remix; o **volume do áudio do background** só muda com novo envio.
- **Armazenamento:** uploads e o vídeo da fala de cada envio ficam em disco até serem apagados (hoje só as vinhetas/mídias têm botão de apagar).
- **Segurança:** o Hermes executa com aprovação automática; sem `STUDIO_API_KEY` a API é aberta para quem alcançar a porta.

## Solução de problemas

| Sintoma | Causa provável e o que fazer |
|---|---|
| Tela "processando" para sempre | Recarregue (Ctrl+F5); confira `GET /api/...` e o log do backend; reinício marca trabalhos interrompidos como falha |
| Envio bloqueado: "sem trecho" | Selecione o texto no parágrafo e use o ✎ do corte |
| Falha no nó 5: frase não encontrada | Trecho com número/variação; troque o trecho. Confirme o alinhador tolerante no servidor |
| "Perdi a conexão com o ComfyUI" | ComfyUI reiniciando ou fora do ar; reenvie |
| Falha ao montar com as vinhetas | Veja a mensagem do ffmpeg; o vídeo da fala continua no ComfyUI; ajuste e use **Remixar** |
| Backend não conecta ao banco | Túnel SSH caiu ou senha errada |
| `git`: "dubious ownership" | Pasta em disco NTFS pertencente a outro usuário: `git -c safe.directory=$PWD …` |
