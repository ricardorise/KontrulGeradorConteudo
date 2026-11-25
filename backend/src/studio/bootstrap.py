"""Composition root: liga portas aos adaptadores e monta a aplicação."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from studio.conversation.application.use_cases import (
    GetConversation,
    ListConversations,
    OpenConversation,
    SendMessage,
)
from studio.discovery.application.use_cases import GetNewsSearch, ListNewsSearches, StartNewsSearch
from studio.guidance.application.use_cases import (
    ActiveGuidelineTexts,
    AddGuideline,
    DeleteGuideline,
    ListGuidelines,
    SetGuidelineActive,
)
from studio.infrastructure.comfyui.renderer import ComfyUiRenderer
from studio.infrastructure.agents.hermes_gateway import HermesCliGateway
from studio.infrastructure.config import Settings
from studio.infrastructure.persistence.conversation_repository import PostgresConversationRepository
from studio.infrastructure.persistence.database import create_pool, run_migrations
from studio.infrastructure.persistence.guideline_repository import PostgresGuidelineRepository
from studio.infrastructure.persistence.news_repository import PostgresNewsSearchRepository
from studio.infrastructure.persistence.news_source_reader import DiscoveryNewsSourceReader
from studio.infrastructure.media.ffmpeg import FfmpegProbe, FfmpegVideoComposer
from studio.infrastructure.media.store import LocalMediaStore
from studio.infrastructure.persistence.render_asset_repository import PostgresRenderAssetRepository
from studio.infrastructure.persistence.render_repository import PostgresRenderJobRepository
from studio.infrastructure.persistence.render_script_source import ScriptingScriptSourceReader
from studio.infrastructure.persistence.script_repository import PostgresScriptRepository
from studio.infrastructure.studio_gateway import StudioUseCaseGateway
from studio.infrastructure.runtime.background import AsyncioBackgroundRunner
from studio.interfaces.http.app import build_app
from studio.interfaces.http.container import UseCases
from studio.rendering.application.use_cases import (
    DeleteRenderAsset,
    GetRender,
    ListRenderAssets,
    ListRenders,
    OpenRenderVideo,
    PreviewRender,
    RenderFinisher,
    RemixRender,
    RenderMonitor,
    StartRender,
    UploadRenderAsset,
    resume_active,
)
from studio.scripting.application.use_cases import (
    AddCut,
    DeleteCut,
    GetLatestScript,
    GetScript,
    SetCutExcerpt,
    RetryBroll,
    ScriptWorkflow,
    StartScriptGeneration,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    runner = AsyncioBackgroundRunner()
    renderer = ComfyUiRenderer(settings.comfy_url, settings.comfy_workflow_path)
    agents = HermesCliGateway(
        container=settings.hermes_container,
        ssh_target=settings.hermes_ssh_target,
        ssh_key=settings.hermes_ssh_key,
        timeout_s=settings.agent_timeout_s,
        max_concurrent=settings.max_concurrent_agents,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = await create_pool(settings.database_url)
        if settings.run_migrations:
            await run_migrations(pool)

        news_repo = PostgresNewsSearchRepository(pool)
        script_repo = PostgresScriptRepository(pool)
        conversation_repo = PostgresConversationRepository(pool)
        interrupted = sum([await news_repo.fail_interrupted(), await script_repo.fail_interrupted(),
                           await conversation_repo.fail_interrupted()])  # fmt: skip
        if interrupted:
            log.warning("%d tarefa(s) interrompida(s) pelo último desligamento foram marcadas como falhas", interrupted)

        render_repo = PostgresRenderJobRepository(pool)
        asset_repo = PostgresRenderAssetRepository(pool)
        media_store = LocalMediaStore(settings.media_dir)
        probe = FfmpegProbe(settings.ffmpeg)
        finisher = RenderFinisher(render_repo, asset_repo, renderer, media_store, FfmpegVideoComposer(probe, settings.ffmpeg))
        render_monitor = RenderMonitor(render_repo, renderer, settings.comfy_poll_interval_s, finisher=finisher)
        preview_render = PreviewRender(ScriptingScriptSourceReader(script_repo), renderer)
        guideline_repo = PostgresGuidelineRepository(pool)
        guideline_texts = ActiveGuidelineTexts(guideline_repo)
        add_guideline = AddGuideline(guideline_repo)
        workflow = ScriptWorkflow(script_repo, DiscoveryNewsSourceReader(news_repo), agents, runner, guideline_texts)
        start_news_search = StartNewsSearch(news_repo, agents, runner, guideline_texts)
        get_news_search, get_script = GetNewsSearch(news_repo), GetScript(script_repo)
        start_script, retry_broll = StartScriptGeneration(workflow), RetryBroll(workflow)
        studio = StudioUseCaseGateway(start_news_search, get_news_search, start_script, get_script, retry_broll, add_guideline)
        app.state.use_cases = UseCases(
            start_news_search=start_news_search,
            get_news_search=get_news_search,
            list_news_searches=ListNewsSearches(news_repo),
            start_script=start_script,
            get_script=get_script,
            get_latest_script=GetLatestScript(script_repo),
            retry_broll=retry_broll,
            add_cut=AddCut(script_repo),
            delete_cut=DeleteCut(script_repo),
            set_cut_excerpt=SetCutExcerpt(script_repo),
            open_conversation=OpenConversation(conversation_repo),
            send_message=SendMessage(conversation_repo, agents, runner, studio),
            add_guideline=add_guideline,
            list_guidelines=ListGuidelines(guideline_repo),
            set_guideline_active=SetGuidelineActive(guideline_repo),
            delete_guideline=DeleteGuideline(guideline_repo),
            preview_render=preview_render,
            start_render=StartRender(render_repo, preview_render, renderer, runner, render_monitor, asset_repo, media_store),
            upload_render_asset=UploadRenderAsset(asset_repo, media_store, probe, settings.max_upload_mb * 1024 * 1024),
            list_render_assets=ListRenderAssets(asset_repo, media_store),
            delete_render_asset=DeleteRenderAsset(asset_repo, media_store),
            remix_render=RemixRender(render_repo, asset_repo, runner, finisher),
            get_render=GetRender(render_repo),
            list_renders=ListRenders(render_repo),
            open_render_video=OpenRenderVideo(render_repo, renderer, media_store),
            get_conversation=GetConversation(conversation_repo),
            list_conversations=ListConversations(conversation_repo),
        )
        resumed = await resume_active(render_repo, runner, render_monitor)
        if resumed:
            log.info("%d renderização(ões) em andamento no ComfyUI retomada(s)", resumed)
        try:
            yield
        finally:
            await runner.shutdown()
            await pool.close()

    # use_cases real é injetado no lifespan; o placeholder só satisfaz a assinatura.
    return build_app(None, api_key=settings.api_key, cors_origins=settings.cors_origins, lifespan=lifespan)  # type: ignore[arg-type]
