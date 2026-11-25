-- Um único áudio de fundo com nível por etapa: abertura, fala (music_volume) e final. NULL = igual ao da fala.
ALTER TABLE content_studio.renders
    ADD COLUMN music_intro_volume double precision,
    ADD COLUMN music_outro_volume double precision;
