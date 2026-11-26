import { apiUrl } from './base'
import type { ChatBot, Conversation, Guideline, GuidelineScope, NewsSearch, RadarSearchOptions, Narration, Publication, ScriptConfigInput, ScriptEntry, ScriptOptions, ScriptProfile, PublicationEdit, Render, RenderAsset, RenderPreview, Script, VignetteKind, ScreenContext } from './types'

export class ApiError extends Error {}

export interface MixOptions {
  introVolume: number // 0–1,5
  outroVolume: number
  backgroundVolume: number // áudio do vídeo de background
  normalize: boolean // nivela o loudness das vinhetas com a fala
  musicIntroVolume: number | null // nível do áudio de fundo na abertura (null = igual ao da fala)
  musicOutroVolume: number | null // ... e no final
  narration: Narration | null // voz da narração (nó PapoNarration); null mantém a do workflow
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `Erro ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(detail)
  }
  return response.json() as Promise<T>
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  startNewsSearch: (topic: string, options?: RadarSearchOptions) => post<NewsSearch>('/news-searches', { topic, ...options }),
  getNewsSearch: (id: string) => request<NewsSearch>(`/news-searches/${id}`),
  listNewsSearches: () => request<NewsSearch[]>('/news-searches?limit=15'),

  generateScript: (newsItemId: string, force = false, config?: ScriptConfigInput) =>
    post<Script>(`/news-items/${newsItemId}/script${force ? '?force=true' : ''}`, config ? { config } : undefined),
  listScripts: () => request<ScriptEntry[]>('/scripts?limit=150'),
  scriptOptions: () => request<ScriptOptions>('/script-options'),
  addScriptProfile: (name: string, instructions: string, description = '') =>
    post<ScriptProfile>('/script-profiles', { name, instructions, description }),
  deleteScriptProfile: async (id: string) => {
    const response = await fetch(apiUrl(`/script-profiles/${id}`), { method: 'DELETE' })
    if (!response.ok) throw new ApiError((await response.json().catch(() => ({}))).detail ?? `Erro ${response.status}`)
  },
  getLatestScript: (newsItemId: string) => request<Script | null>(`/news-items/${newsItemId}/script`),
  getScript: (id: string) => request<Script>(`/scripts/${id}`),
  retryBroll: (id: string, paragraphIds?: string[]) =>
    post<Script>(`/scripts/${id}/broll`, paragraphIds?.length ? { paragraph_ids: paragraphIds } : undefined),
  addBroll: (scriptId: string, paragraphId: string, videoUrl: string) =>
    post<Script>(`/scripts/${scriptId}/paragraphs/${paragraphId}/broll`, { video_url: videoUrl }),
  replaceBroll: (scriptId: string, brollId: string, videoUrl: string) =>
    request<Script>(`/scripts/${scriptId}/broll/${brollId}`, { method: 'PUT', body: JSON.stringify({ video_url: videoUrl }) }),
  removeBroll: (scriptId: string, brollId: string) => request<Script>(`/scripts/${scriptId}/broll/${brollId}`, { method: 'DELETE' }),
  addCut: (
    scriptId: string,
    cut: { paragraph_id: string; video_url: string; start_seconds: number; end_seconds: number; video_title: string | null; text_start?: number; text_end?: number },
  ) => post<Script>(`/scripts/${scriptId}/cuts`, cut),
  setCutExcerpt: (scriptId: string, cutId: string, range: { text_start: number; text_end: number } | null) =>
    request<Script>(`/scripts/${scriptId}/cuts/${cutId}/excerpt`, { method: 'PATCH', body: JSON.stringify(range ?? {}) }),
  deleteCut: (scriptId: string, cutId: string) => request<Script>(`/scripts/${scriptId}/cuts/${cutId}`, { method: 'DELETE' }),

  openConversation: (bot: ChatBot) => post<Conversation>('/conversations', { bot }),
  listConversations: (bot: ChatBot) => request<Conversation[]>(`/conversations?bot=${bot}&limit=20`),
  getConversation: (id: string) => request<Conversation>(`/conversations/${id}`),
  sendMessage: (id: string, content: string, context: ScreenContext) =>
    post<Conversation>(`/conversations/${id}/messages`, { content, context }),

  renderPreview: (scriptId: string, background?: string) =>
    request<RenderPreview>(`/scripts/${scriptId}/render-preview${background ? `?background=${encodeURIComponent(background)}` : ''}`),
  startRender: (
    scriptId: string,
    background: string,
    introAssetId: string | null,
    outroAssetId: string | null,
    musicAssetId: string | null = null,
    musicVolume: number | null = null,
    backgroundAssetId: string | null = null,
    mix: Partial<MixOptions> = {},
  ) =>
    post<Render>(`/scripts/${scriptId}/renders`, {
      background,
      intro_asset_id: introAssetId,
      outro_asset_id: outroAssetId,
      music_asset_id: musicAssetId,
      music_volume: musicAssetId ? musicVolume : null,
      background_asset_id: backgroundAssetId,
      intro_volume: mix.introVolume ?? 1,
      outro_volume: mix.outroVolume ?? 1,
      background_volume: mix.backgroundVolume ?? 0,
      normalize_vignettes: mix.normalize ?? true,
      music_intro_volume: musicAssetId ? (mix.musicIntroVolume ?? null) : null,
      music_outro_volume: musicAssetId ? (mix.musicOutroVolume ?? null) : null,
      narration: mix.narration ?? null,
    }),
  remixRender: (
    renderId: string,
    body: {
      introAssetId: string | null
      outroAssetId: string | null
      musicAssetId: string | null
      musicVolume: number | null
      musicIntroVolume: number | null
      musicOutroVolume: number | null
      introVolume: number
      outroVolume: number
      normalize: boolean
    },
  ) =>
    post<Render>(`/renders/${renderId}/remix`, {
      intro_asset_id: body.introAssetId,
      outro_asset_id: body.outroAssetId,
      music_asset_id: body.musicAssetId,
      music_volume: body.musicAssetId ? body.musicVolume : null,
      music_intro_volume: body.musicAssetId ? body.musicIntroVolume : null,
      music_outro_volume: body.musicAssetId ? body.musicOutroVolume : null,
      intro_volume: body.introVolume,
      outro_volume: body.outroVolume,
      normalize_vignettes: body.normalize,
    }),
  listRenderAssets: (kind: VignetteKind) => request<RenderAsset[]>(`/render-assets?kind=${kind}`),
  uploadRenderAsset: async (kind: VignetteKind, file: File): Promise<RenderAsset> => {
    const form = new FormData() // multipart: o navegador define o Content-Type com o boundary
    form.append('kind', kind)
    form.append('file', file)
    const response = await fetch(apiUrl('/render-assets'), { method: 'POST', body: form })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new ApiError(typeof body.detail === 'string' ? body.detail : `Erro ${response.status}`)
    return body as RenderAsset
  },
  deleteRenderAsset: async (id: string) => {
    await fetch(apiUrl(`/render-assets/${id}`), { method: 'DELETE' })
  },
  listRenders: (scriptId: string) => request<Render[]>(`/scripts/${scriptId}/renders?limit=5`),
  getRender: (id: string) => request<Render>(`/renders/${id}`),

  preparePublication: (renderId: string, force = false) => post<Publication>(`/renders/${renderId}/publication`, { force }),
  getPublication: (id: string) => request<Publication>(`/publications/${id}`),
  getPublicationForRender: (renderId: string) => request<Publication | null>(`/renders/${renderId}/publication`),
  editPublication: (id: string, edit: PublicationEdit) =>
    request<Publication>(`/publications/${id}`, { method: 'PATCH', body: JSON.stringify(edit) }),
  revisePublication: (id: string, target: 'title' | 'description' | 'tags' | 'all', instructions: string) =>
    post<Publication>(`/publications/${id}/revise`, { target, instructions }),
  regeneratePublication: (id: string) => post<Publication>(`/publications/${id}/regenerate`),
  publishPublication: (id: string) => post<Publication>(`/publications/${id}/publish`, { confirm: true }),

  listGuidelines: () => request<Guideline[]>('/guidelines'),
  addGuideline: (scope: GuidelineScope, text: string) => post<Guideline>('/guidelines', { scope, text }),
  setGuidelineActive: (id: string, active: boolean) =>
    request<Guideline>(`/guidelines/${id}`, { method: 'PATCH', body: JSON.stringify({ active }) }),
  deleteGuideline: async (id: string) => {
    await fetch(apiUrl(`/guidelines/${id}`), { method: 'DELETE' })
  },
}

export type Api = typeof api
