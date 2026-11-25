from dataclasses import dataclass

from studio.conversation.application.use_cases import (
    GetConversation,
    ListConversations,
    OpenConversation,
    SendMessage,
)
from studio.guidance.application.use_cases import AddGuideline, DeleteGuideline, ListGuidelines, SetGuidelineActive
from studio.discovery.application.use_cases import GetNewsSearch, ListNewsSearches, StartNewsSearch
from studio.rendering.application.use_cases import (
    DeleteRenderAsset,
    GetRender,
    ListRenderAssets,
    ListRenders,
    OpenRenderVideo,
    PreviewRender,
    RemixRender,
    StartRender,
    UploadRenderAsset,
)
from studio.scripting.application.use_cases import AddCut, DeleteCut, GetLatestScript, GetScript, SetCutExcerpt, RetryBroll, StartScriptGeneration


@dataclass(frozen=True)
class UseCases:
    start_news_search: StartNewsSearch
    get_news_search: GetNewsSearch
    list_news_searches: ListNewsSearches
    start_script: StartScriptGeneration
    get_script: GetScript
    get_latest_script: GetLatestScript
    retry_broll: RetryBroll
    add_cut: AddCut
    delete_cut: DeleteCut
    set_cut_excerpt: SetCutExcerpt
    open_conversation: OpenConversation
    send_message: SendMessage
    get_conversation: GetConversation
    list_conversations: ListConversations
    add_guideline: AddGuideline
    list_guidelines: ListGuidelines
    set_guideline_active: SetGuidelineActive
    delete_guideline: DeleteGuideline
    preview_render: PreviewRender
    start_render: StartRender
    remix_render: RemixRender
    get_render: GetRender
    list_renders: ListRenders
    open_render_video: OpenRenderVideo
    upload_render_asset: UploadRenderAsset
    list_render_assets: ListRenderAssets
    delete_render_asset: DeleteRenderAsset
