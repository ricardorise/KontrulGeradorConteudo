-- Schema dedicado do Gerador de Conteúdo (banco kontrul-postgres-1 / db sofia).
CREATE SCHEMA IF NOT EXISTS content_studio;

CREATE TABLE content_studio.news_searches (
    id          uuid PRIMARY KEY,
    topic       text        NOT NULL,
    status      text        NOT NULL CHECK (status IN ('pending','running','done','failed')),
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX news_searches_created_idx ON content_studio.news_searches (created_at DESC);

CREATE TABLE content_studio.news_items (
    id           uuid PRIMARY KEY,
    search_id    uuid    NOT NULL REFERENCES content_studio.news_searches (id) ON DELETE CASCADE,
    position     integer NOT NULL,
    title        text    NOT NULL,
    summary      text    NOT NULL,
    details      text,
    source_url   text,
    published_at text,
    UNIQUE (search_id, position)
);

CREATE TABLE content_studio.scripts (
    id           uuid PRIMARY KEY,
    news_item_id uuid        NOT NULL REFERENCES content_studio.news_items (id) ON DELETE CASCADE,
    title        text,
    status       text        NOT NULL CHECK (status IN ('pending','running','done','failed')),
    error        text,
    broll_status text        NOT NULL DEFAULT 'pending' CHECK (broll_status IN ('pending','running','done','failed')),
    broll_error  text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
CREATE INDEX scripts_news_item_idx ON content_studio.scripts (news_item_id, created_at DESC);

CREATE TABLE content_studio.script_paragraphs (
    id        uuid PRIMARY KEY,
    script_id uuid    NOT NULL REFERENCES content_studio.scripts (id) ON DELETE CASCADE,
    position  integer NOT NULL,
    text      text    NOT NULL,
    UNIQUE (script_id, position)
);

CREATE TABLE content_studio.broll_suggestions (
    id            uuid PRIMARY KEY,
    paragraph_id  uuid    NOT NULL REFERENCES content_studio.script_paragraphs (id) ON DELETE CASCADE,
    position      integer NOT NULL,
    video_url     text    NOT NULL,
    video_id      text    NOT NULL,
    start_seconds integer,
    title         text,
    description   text    NOT NULL,
    justification text
);
CREATE INDEX broll_paragraph_idx ON content_studio.broll_suggestions (paragraph_id, position);

CREATE TABLE content_studio.conversations (
    id         uuid PRIMARY KEY,
    bot        text        NOT NULL CHECK (bot IN ('tonton','julesverne','baru')),
    title      text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversations_updated_idx ON content_studio.conversations (bot, updated_at DESC);

CREATE TABLE content_studio.messages (
    seq             bigint GENERATED ALWAYS AS IDENTITY,
    id              uuid PRIMARY KEY,
    conversation_id uuid        NOT NULL REFERENCES content_studio.conversations (id) ON DELETE CASCADE,
    role            text        NOT NULL CHECK (role IN ('user','assistant')),
    content         text        NOT NULL DEFAULT '',
    status          text        NOT NULL CHECK (status IN ('pending','running','done','failed')),
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_conversation_idx ON content_studio.messages (conversation_id, seq);
