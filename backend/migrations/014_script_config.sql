-- Configuração do roteiro: perfis de roteirista cadastrados pelo editor, configuração usada em cada roteiro
-- (perfil, tempo, apresentadores) e quem fala em cada parágrafo (roteiro com dois apresentadores).
CREATE TABLE content_studio.script_profiles (
    id          uuid PRIMARY KEY,
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    instructions text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX script_profiles_name_key ON content_studio.script_profiles (lower(name));

ALTER TABLE content_studio.scripts ADD COLUMN config jsonb;
ALTER TABLE content_studio.script_paragraphs ADD COLUMN speaker text;
