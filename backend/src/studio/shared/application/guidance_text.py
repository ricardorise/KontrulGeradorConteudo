def render_guidance(guidelines: list[str], instructions: str | None) -> str:
    """Bloco de prompt com as orientações permanentes e o pedido específico desta execução."""
    parts: list[str] = []
    if guidelines:
        rules = "\n".join(f"- {g}" for g in guidelines)
        parts.append(f"Orientações permanentes do editor (siga-as):\n{rules}")
    if instructions and instructions.strip():
        parts.append(f"Pedido específico do editor para esta tarefa (tem prioridade):\n{instructions.strip()}")
    return ("\n\n" + "\n\n".join(parts)) if parts else ""
