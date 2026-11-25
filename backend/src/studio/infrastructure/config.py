import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool = False) -> bool:
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    hermes_ssh_target: str | None  # ex.: rises@10.241.168.46; vazio = docker local
    hermes_ssh_key: str | None
    hermes_container: str
    agent_timeout_s: float
    max_concurrent_agents: int
    api_key: str | None  # se definido, exige X-API-Key nas rotas /api
    cors_origins: tuple[str, ...]
    run_migrations: bool
    comfy_url: str
    comfy_workflow_path: str | None
    comfy_poll_interval_s: float
    media_dir: str
    max_upload_mb: int
    ffmpeg: str

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            database_url=env["STUDIO_DATABASE_URL"],
            hermes_ssh_target=env.get("STUDIO_HERMES_SSH") or None,
            hermes_ssh_key=env.get("STUDIO_HERMES_SSH_KEY") or None,
            hermes_container=env.get("STUDIO_HERMES_CONTAINER", "hermes"),
            agent_timeout_s=float(env.get("STUDIO_AGENT_TIMEOUT_S", "600")),
            max_concurrent_agents=int(env.get("STUDIO_MAX_CONCURRENT_AGENTS", "3")),
            api_key=env.get("STUDIO_API_KEY") or None,
            cors_origins=tuple(o for o in env.get("STUDIO_CORS_ORIGINS", "").split(",") if o),
            run_migrations=_bool(env.get("STUDIO_RUN_MIGRATIONS"), True),
            comfy_url=env.get("STUDIO_COMFY_URL", "http://rises:8188"),
            comfy_workflow_path=env.get("STUDIO_COMFY_WORKFLOW_PATH") or None,
            comfy_poll_interval_s=float(env.get("STUDIO_COMFY_POLL_INTERVAL_S", "4")),
            media_dir=env.get("STUDIO_MEDIA_DIR", "./data/media"),
            max_upload_mb=int(env.get("STUDIO_MAX_UPLOAD_MB", "2048")),
            ffmpeg=env.get("STUDIO_FFMPEG", "ffmpeg"),
        )
