-- Cortes escolhidos pelo editor: trecho (início/fim) de um vídeo do YouTube ligado a um parágrafo do roteiro.
CREATE TABLE content_studio.script_cuts (
    id            uuid PRIMARY KEY,
    script_id     uuid             NOT NULL REFERENCES content_studio.scripts (id) ON DELETE CASCADE,
    paragraph_id  uuid             NOT NULL REFERENCES content_studio.script_paragraphs (id) ON DELETE CASCADE,
    video_id      text             NOT NULL,
    video_url     text             NOT NULL,
    video_title   text,
    start_seconds double precision NOT NULL CHECK (start_seconds >= 0),
    end_seconds   double precision NOT NULL,
    created_at    timestamptz      NOT NULL DEFAULT now(),
    CHECK (end_seconds > start_seconds)
);
CREATE INDEX script_cuts_script_idx ON content_studio.script_cuts (script_id, created_at);
