from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from studio.shared.domain.clock import utcnow
from studio.shared.domain.status import JobStatus


@dataclass(frozen=True)
class RenderOutput:
    """Localização do MP4 na saída do ComfyUI (parâmetros do GET /view)."""

    filename: str
    subfolder: str = ""
    type: str = "output"


@dataclass
class RenderJob:
    """Agregado: um envio do roteiro e da lista de edição ao ComfyUI, até o MP4 final."""

    id: UUID
    script_id: UUID
    status: JobStatus
    background: str
    roteiro: str
    edit_list: str
    created_at: datetime
    prompt_id: str | None = None
    queued: bool = True  # ainda na fila do ComfyUI (False = executando)
    output: RenderOutput | None = None
    error: str | None = None
    finished_at: datetime | None = None
    intro_asset_id: UUID | None = None
    outro_asset_id: UUID | None = None
    stage: str = "comfyui"  # comfyui -> composing (monta abertura/final) -> done
    final_path: str | None = None  # vídeo montado, guardado pelo app
    music_asset_id: UUID | None = None
    music_volume: float | None = None
    background_asset_id: UUID | None = None
    intro_volume: float = 1.0
    outro_volume: float = 1.0
    background_volume: float = 0.0  # áudio do vídeo de background, mixado dentro do ComfyUI (volume_fundo)
    normalize_vignettes: bool = True
    music_intro_volume: float | None = None  # nível do áudio de fundo durante a abertura (None = igual ao da fala)
    music_outro_volume: float | None = None  # ... e durante a vinheta final
    music_in_video: bool = False  # a trilha foi mixada DENTRO do vídeo do ComfyUI (envio sem vinhetas)
    main_path: str | None = None  # vídeo da fala (saída do ComfyUI) guardado para remixar sem refazer o render

    @classmethod
    def create(
        cls, script_id: UUID, background: str, roteiro: str, edit_list: str,
        intro_asset_id: UUID | None = None, outro_asset_id: UUID | None = None,
        music_asset_id: UUID | None = None, music_volume: float | None = None,
        background_asset_id: UUID | None = None, intro_volume: float = 1.0, outro_volume: float = 1.0,
        background_volume: float = 0.0, normalize_vignettes: bool = True, music_in_video: bool = False,
        music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> "RenderJob":  # fmt: skip
        return cls(
            uuid4(), script_id, JobStatus.PENDING, background, roteiro, edit_list, utcnow(),
            intro_asset_id=intro_asset_id, outro_asset_id=outro_asset_id,
            music_asset_id=music_asset_id, music_volume=music_volume, background_asset_id=background_asset_id,
            intro_volume=intro_volume, outro_volume=outro_volume, background_volume=background_volume,
            normalize_vignettes=normalize_vignettes, music_in_video=music_in_video,
            music_intro_volume=music_intro_volume, music_outro_volume=music_outro_volume,
        )  # fmt: skip

    @property
    def has_vignettes(self) -> bool:
        return self.intro_asset_id is not None or self.outro_asset_id is not None

    @property
    def music_is_baked(self) -> bool:
        """Sem vinhetas a trilha foi mixada dentro do vídeo do ComfyUI; não dá para trocá-la ao remixar."""
        return self.music_in_video

    @property
    def can_remix(self) -> bool:
        return self.status is JobStatus.DONE and self.output is not None

    def remix(
        self, intro: UUID | None, outro: UUID | None, music: UUID | None, music_volume: float | None,
        intro_volume: float, outro_volume: float, normalize: bool,
        music_intro_volume: float | None = None, music_outro_volume: float | None = None,
    ) -> "RenderJob":  # fmt: skip
        """Novo envio que reaproveita o vídeo da fala deste e só refaz a montagem final."""
        keep_music = self.music_is_baked
        return RenderJob(
            uuid4(), self.script_id, JobStatus.RUNNING, self.background, self.roteiro, self.edit_list, utcnow(),
            prompt_id=self.prompt_id, queued=False, output=self.output, stage="composing", main_path=self.main_path,
            intro_asset_id=intro, outro_asset_id=outro,
            music_asset_id=self.music_asset_id if keep_music else music,
            music_volume=self.music_volume if keep_music else (music_volume if music else None),
            background_asset_id=self.background_asset_id, background_volume=self.background_volume,
            intro_volume=intro_volume, outro_volume=outro_volume, normalize_vignettes=normalize,
            music_in_video=keep_music,
            music_intro_volume=None if keep_music else (music_intro_volume if music else None),
            music_outro_volume=None if keep_music else (music_outro_volume if music else None),
        )  # fmt: skip

    def begin_composing(self, output: RenderOutput) -> None:
        """O ComfyUI terminou; falta montar abertura + vídeo + final."""
        self.output, self.stage, self.queued = output, "composing", False

    def submitted(self, prompt_id: str) -> None:
        self.prompt_id, self.status = prompt_id, JobStatus.RUNNING

    def set_queued(self, queued: bool) -> None:
        self.queued = queued

    def complete(self, output: RenderOutput) -> None:
        self.status, self.output, self.error, self.queued = JobStatus.DONE, output, None, False
        self.stage = "done"
        self.finished_at = utcnow()

    def fail(self, error: str) -> None:
        self.status, self.error, self.queued = JobStatus.FAILED, error, False
        self.finished_at = utcnow()
