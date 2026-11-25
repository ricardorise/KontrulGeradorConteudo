import json
import re
from typing import Any

from studio.shared.application.ports import AgentOutputError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(raw: str, required_key: str) -> dict[str, Any]:
    """Acha o primeiro objeto JSON da saída do bot que contenha `required_key`.

    Os bots às vezes comentam antes/depois ou envolvem em ```json```; toleramos isso.
    """
    candidates = [raw, *_FENCE.findall(raw)]
    decoder = json.JSONDecoder()
    for text in candidates:
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and required_key in value:
                return value
    raise AgentOutputError(f"Resposta do bot sem JSON válido com a chave '{required_key}'.")
