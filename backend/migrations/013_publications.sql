-- Publicação do vídeo gerado no YouTube: rascunho (título, descrição, tags, links) revisável e o resultado do envio.
CREATE TABLE content_studio.publications (
    id                 uuid PRIMARY KEY,
    render_id          uuid        NOT NULL REFERENCES content_studio.renders (id) ON DELETE CASCADE,
    script_id          uuid        NOT NULL REFERENCES content_studio.scripts (id) ON DELETE CASCADE,
    status             text        NOT NULL CHECK (status IN ('drafting','ready','publishing','published','failed')),
    title              text        NOT NULL DEFAULT '',
    title_alternatives jsonb       NOT NULL DEFAULT '[]'::jsonb,
    description        text        NOT NULL DEFAULT '',
    tags               jsonb       NOT NULL DEFAULT '[]'::jsonb,
    links              jsonb       NOT NULL DEFAULT '[]'::jsonb,
    privacy            text        NOT NULL DEFAULT 'private' CHECK (privacy IN ('private','unlisted')),
    category_id        text        NOT NULL DEFAULT '28',
    language           text        NOT NULL DEFAULT 'pt',
    notify_subscribers boolean     NOT NULL DEFAULT false,
    rationale          text,
    error              text,
    error_stage        text,
    video_id           text,
    video_url          text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    published_at       timestamptz
);
CREATE INDEX publications_render_idx ON content_studio.publications (render_id, created_at DESC);
