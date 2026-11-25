import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from studio.rendering.application.ports import MediaError


class LocalMediaStore:
    """Vinhetas enviadas e vídeos montados no disco local (STUDIO_MEDIA_DIR)."""

    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()
        for sub in ("assets", "renders", "tmp"):
            (self._root / sub).mkdir(parents=True, exist_ok=True)

    def asset_path(self, stored_name: str) -> Path:
        path = (self._root / "assets" / Path(stored_name).name).resolve()  # .name evita sair da pasta
        return path

    def result_path(self, job_id: UUID) -> Path:
        return self._root / "renders" / f"{job_id}.mp4"

    def main_path(self, job_id: UUID) -> Path:
        return self._root / "renders" / f"{job_id}-fala.mp4"

    def temp_path(self, job_id: UUID) -> Path:
        return self._root / "tmp" / f"{job_id}.mp4"

    async def save_upload(self, name: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        return await self._write(self.asset_path(name), chunks, max_bytes)

    async def write_stream(self, path: Path, chunks: AsyncIterator[bytes]) -> None:
        await self._write(path, chunks, None)

    async def _write(self, path: Path, chunks: AsyncIterator[bytes], max_bytes: int | None) -> int:
        size = 0
        try:
            with open(path, "wb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise MediaError(f"arquivo maior que o limite de {max_bytes // (1024 * 1024)} MB")
                    await asyncio.to_thread(out.write, chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return size

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)
