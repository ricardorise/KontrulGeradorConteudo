export type JobStatus = 'pending' | 'running' | 'done' | 'failed'
export type ChatBot = 'tonton' | 'julesverne' | 'lumiere' | 'baru'

export interface RadarInfo {
  temporal_note?: string
  ranking_reason?: string
  category?: string
  status?: string
  nature?: string
  why_now?: string
  velocity?: string
  where_growing?: string[]
  evidence?: string[]
  started_at?: string
  content_potential?: string
  angles?: string[]
  sources?: string[]
  divergences?: string
}

export interface NewsItem {
  id: string
  position: number
  title: string
  summary: string
  details: string | null
  source_url: string | null
  published_at: string | null
  radar?: RadarInfo
}

export interface RadarSearchOptions {
  radar_scope?: string
  window_hours?: number
  window_end?: string
}

export interface RadarContext {
  policy?: string
  scope?: string
  window_start?: string
  window_end?: string
  window_hours?: number
  ranking_rule?: string
  coverage?: Record<string, string>
  temporal_validation?: string
  coverage_note?: string
  google_trends_note?: string
  discarded?: string[]
  stage?: string
}

export interface NewsSearch {
  id: string
  topic: string
  status: JobStatus
  error: string | null
  instructions: string | null
  created_at: string
  finished_at: string | null
  report_context?: RadarContext
  items: NewsItem[]
}

export interface Broll {
  id: string
  video_url: string
  video_id: string
  start_seconds: number | null
  title: string | null
  description: string
  justification: string | null
}

export interface Paragraph {
  id: string
  position: number
  text: string
  broll: Broll[]
}

export interface Cut {
  id: string
  paragraph_id: string
  video_id: string
  video_url: string
  video_title: string | null
  start_seconds: number
  end_seconds: number
  duration: number
  created_at: string
  excerpt: { id: string; start: number; end: number; text: string } | null
}

export interface Script {
  id: string
  news_item_id: string
  title: string | null
  status: JobStatus
  error: string | null
  broll_status: JobStatus
  broll_error: string | null
  instructions: string | null
  created_at: string
  paragraphs: Paragraph[]
  cuts: Cut[]
}

export interface ChatAction {
  type: 'search_news' | 'generate_script' | 'rebuild_broll' | 'save_guideline' | string
  status: JobStatus
  label: string
  error: string | null
  refs: Record<string, string>
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: JobStatus
  error: string | null
  created_at: string
  actions: ChatAction[]
}

export interface ScreenContext {
  search_id: string | null
  script_id: string | null
}

export type GuidelineScope = 'news' | 'script' | 'broll' | 'all'

export interface Guideline {
  id: string
  scope: GuidelineScope
  text: string
  active: boolean
  source: 'manual' | 'chat'
  created_at: string
}

export interface Conversation {
  id: string
  bot: ChatBot
  title: string
  created_at: string
  updated_at: string
  messages: Message[]
}

export interface RenderPreview {
  background: string
  roteiro_chars: number
  edit_list: string
  lines: { order: number; paragraph: number; text: string; phrase: string }[]
  problems: string[]
  can_send: boolean
  music_volume: number
  background_volume_supported: boolean
}

export interface Render {
  id: string
  script_id: string
  status: JobStatus
  queued: boolean
  prompt_id: string | null
  background: string
  edit_list: string
  error: string | null
  has_video: boolean
  video_name: string | null
  stage: 'comfyui' | 'composing' | 'done'
  intro_asset_id: string | null
  outro_asset_id: string | null
  music_asset_id: string | null
  music_volume: number | null
  music_intro_volume: number | null
  music_outro_volume: number | null
  intro_volume: number
  outro_volume: number
  background_volume: number
  normalize_vignettes: boolean
  can_remix: boolean
  music_baked: boolean
  created_at: string
  finished_at: string | null
}

export type VignetteKind = 'intro' | 'outro' | 'music' | 'background'

export interface RenderAsset {
  id: string
  kind: VignetteKind
  filename: string
  size_bytes: number
  duration: number
  width: number
  height: number
  has_audio: boolean
  audio_silent: boolean
  mean_volume_db: number | null
  created_at: string
}
