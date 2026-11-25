-- Vídeo de background enviado pelo editor (em vez de digitar o caminho do servidor).
ALTER TABLE content_studio.render_assets DROP CONSTRAINT render_assets_kind_check;
ALTER TABLE content_studio.render_assets
    ADD CONSTRAINT render_assets_kind_check CHECK (kind IN ('intro','outro','music','background'));

ALTER TABLE content_studio.renders
    ADD COLUMN background_asset_id uuid REFERENCES content_studio.render_assets (id) ON DELETE SET NULL;
