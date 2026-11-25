-- Orientações aprendidas (persistentes), instruções por execução e ações executadas pelo chat.
CREATE TABLE content_studio.guidelines (
    id         uuid PRIMARY KEY,
    scope      text        NOT NULL CHECK (scope IN ('news','script','broll','all')),
    text       text        NOT NULL,
    active     boolean     NOT NULL DEFAULT true,
    source     text        NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','chat')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX guidelines_active_idx ON content_studio.guidelines (active, scope);

ALTER TABLE content_studio.news_searches ADD COLUMN instructions text;
ALTER TABLE content_studio.scripts       ADD COLUMN instructions text;
ALTER TABLE content_studio.messages      ADD COLUMN actions jsonb NOT NULL DEFAULT '[]'::jsonb;
