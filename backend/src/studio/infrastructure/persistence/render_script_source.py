from uuid import UUID

from studio.rendering.domain.script_view import CutForRender, ScriptForRender
from studio.scripting.domain.repository import ScriptRepository
from studio.shared.domain.status import JobStatus


class ScriptingScriptSourceReader:
    """Adaptador: o contexto de renderização lê o roteiro e os cortes do contexto de roteiro."""

    def __init__(self, scripts: ScriptRepository):
        self._scripts = scripts

    async def get(self, script_id: UUID) -> ScriptForRender | None:
        script = await self._scripts.get(script_id)
        if script is None or script.status is not JobStatus.DONE:
            return None
        position = {p.id: p.position + 1 for p in script.paragraphs}
        cuts = [
            CutForRender(
                paragraph=position[c.paragraph_id], video_id=c.video_id, start=c.start_seconds, end=c.end_seconds,
                excerpt=c.excerpt.text if c.excerpt else None, excerpt_start=c.excerpt.start if c.excerpt else None,
            )  # fmt: skip
            for c in script.cuts
        ]
        return ScriptForRender(script.title, [p.text for p in script.paragraphs], cuts)
