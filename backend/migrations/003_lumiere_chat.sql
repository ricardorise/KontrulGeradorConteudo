-- Libera o histórico de conversas com Lumière sem alterar conversas existentes.
ALTER TABLE content_studio.conversations DROP CONSTRAINT conversations_bot_check;
ALTER TABLE content_studio.conversations ADD CONSTRAINT conversations_bot_check
    CHECK (bot IN ('tonton', 'julesverne', 'lumiere', 'baru'));
