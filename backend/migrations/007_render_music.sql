-- Áudio de fundo (trilha) enviado pelo editor e usado no envio ao ComfyUI.
ALTER TABLE content_studio.render_assets DROP CONSTRAINT render_assets_kind_check;
ALTER TABLE content_studio.render_assets
    ADD CONSTRAINT render_assets_kind_check CHECK (kind IN ('intro','outro','music'));

ALTER TABLE content_studio.renders
    ADD COLUMN music_asset_id uuid REFERENCES content_studio.render_assets (id) ON DELETE SET NULL,
    ADD COLUMN music_volume   double precision;
