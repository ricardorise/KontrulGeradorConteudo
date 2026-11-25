-- Trecho do texto do parágrafo ao qual um corte de vídeo está vinculado (FK em script_cuts.excerpt_id).
CREATE TABLE content_studio.paragraph_excerpts (
    id           uuid PRIMARY KEY,
    paragraph_id uuid    NOT NULL REFERENCES content_studio.script_paragraphs (id) ON DELETE CASCADE,
    start_offset integer NOT NULL CHECK (start_offset >= 0),
    end_offset   integer NOT NULL,
    text         text    NOT NULL,
    CHECK (end_offset > start_offset),
    UNIQUE (paragraph_id, start_offset, end_offset)
);

-- No máximo um corte por trecho; apagar o trecho apaga o corte.
ALTER TABLE content_studio.script_cuts
    ADD COLUMN excerpt_id uuid UNIQUE REFERENCES content_studio.paragraph_excerpts (id) ON DELETE CASCADE;
