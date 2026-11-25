-- Envios do roteiro + cortes ao ComfyUI (workflow "videos do papotechcast") e o MP4 resultante.
CREATE TABLE content_studio.renders (
    id              uuid PRIMARY KEY,
    script_id       uuid        NOT NULL REFERENCES content_studio.scripts (id) ON DELETE CASCADE,
    status          text        NOT NULL CHECK (status IN ('pending','running','done','failed')),
    prompt_id       text,
    background      text        NOT NULL,
    roteiro         text        NOT NULL,
    edit_list       text        NOT NULL,
    output_filename text,
    output_subfolder text,
    output_type     text,
    queued          boolean     NOT NULL DEFAULT true,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz
);
CREATE INDEX renders_script_idx ON content_studio.renders (script_id, created_at DESC);
