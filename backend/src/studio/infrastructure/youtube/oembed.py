import logging

import httpx

log = logging.getLogger(__name__)


class YoutubeOEmbed:
    """Adaptador da porta VideoTitles: título público do vídeo pelo oEmbed do YouTube (sem chave de API)."""

    def __init__(self, timeout_s: float = 5.0, transport: httpx.AsyncBaseTransport | None = None):
        self._timeout, self._transport = timeout_s, transport

    async def title_of(self, video_id: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                response = await http.get(
                    "https://www.youtube.com/oembed",
                    params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                )
            if response.status_code != 200:  # privado, removido ou inexistente
                return None
            title = response.json().get("title")
            return title.strip()[:300] if isinstance(title, str) and title.strip() else None
        except (httpx.HTTPError, ValueError) as exc:
            log.info("título do vídeo %s indisponível: %s", video_id, exc)
            return None
