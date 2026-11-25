-- Vinhetas (abertura/final) enviadas pelo editor e usadas na montagem do vídeo final.
CREATE TABLE content_studio.render_assets (
    id          uuid PRIMARY KEY,
    kind        text             NOT NULL CHECK (kind IN ('intro','outro')),
    filename    text             NOT NULL,
    stored_name text             NOT NULL,
    size_bytes  bigint           NOT NULL,
    duration    double precision NOT NULL,
    width       integer          NOT NULL,
    height      integer          NOT NULL,
    fps         double precision NOT NULL,
    has_audio   boolean          NOT NULL,
    created_at  timestamptz      NOT NULL DEFAULT now()
);
CREATE INDEX render_assets_kind_idx ON content_studio.render_assets (kind, created_at DESC);

ALTER TABLE content_studio.renders
    ADD COLUMN intro_asset_id uuid REFERENCES content_studio.render_assets (id) ON DELETE SET NULL,
    ADD COLUMN outro_asset_id uuid REFERENCES content_studio.render_assets (id) ON DELETE SET NULL,
    ADD COLUMN stage          text NOT NULL DEFAULT 'comfyui' CHECK (stage IN ('comfyui','composing','done')),
    ADD COLUMN final_path     text;
