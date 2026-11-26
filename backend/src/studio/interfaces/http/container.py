from dataclasses import dataclass

from studio.conversation.application.use_cases import (
    GetConversation,
    ListConversations,
    OpenConversation,
    SendMessage,
)
from studio.guidance.application.use_cases import AddGuideline, DeleteGuideline, ListGuidelines, SetGuidelineActive
from studio.discovery.application.use_cases import GetNewsSearch, ListNewsSearches, StartNewsSearch
from studio.publishing.application.use_cases import (
    EditPublication,
    GetPublication,
    GetPublicationForRender,
    PreparePublication,
    PublishToYoutube,
    RegeneratePublication,
    RevisePublication,
)
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
from studio.scripting.application.catalog import ListScripts
from studio.scripting.application.use_cases import (
    AddBroll,
    AddCut,
    AddScriptProfile,
    DeleteCut,
    DeleteScriptProfile,
    GetLatestScript,
    GetScript,
    RemoveBroll,
    ReplaceBroll,
    RetryBroll,
    ScriptConfigOptions,
    SetCutExcerpt,
    StartScriptGeneration,
)


@dataclass(frozen=True)
class UseCases:
    start_news_search: StartNewsSearch
    get_news_search: GetNewsSearch
    list_news_searches: ListNewsSearches
    start_script: StartScriptGeneration
    list_scripts: ListScripts
    script_options: ScriptConfigOptions
    add_script_profile: AddScriptProfile
    delete_script_profile: DeleteScriptProfile
    get_script: GetScript
    get_latest_script: GetLatestScript
    retry_broll: RetryBroll
    add_broll: AddBroll
    replace_broll: ReplaceBroll
    remove_broll: RemoveBroll
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
    prepare_publication: PreparePublication
    get_publication: GetPublication
    get_publication_for_render: GetPublicationForRender
    edit_publication: EditPublication
    revise_publication: RevisePublication
    regenerate_publication: RegeneratePublication
    publish_publication: PublishToYoutube
    upload_render_asset: UploadRenderAsset
    list_render_assets: ListRenderAssets
    delete_render_asset: DeleteRenderAsset
