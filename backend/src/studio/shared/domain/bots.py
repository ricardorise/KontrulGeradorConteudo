from enum import StrEnum


class Bot(StrEnum):
    """Perfis do Hermes usados pelo estúdio."""

    YOUTOBA = "youtoba"  # pesquisa de tração no YouTube; não é aba de chat
    TONTON = "tonton"  # busca de notícias
    JULESVERNE = "julesverne"  # redação de roteiro
    BARU = "baru"  # supervisor editorial
    LUMIERE = "lumiere"  # B-roll no YouTube e chat
    SNIPER = "sniper"  # publicador (tem a ferramenta youtube_publish); não é aba de chat


CHAT_BOTS: tuple[Bot, ...] = (Bot.TONTON, Bot.JULESVERNE, Bot.LUMIERE, Bot.BARU)
