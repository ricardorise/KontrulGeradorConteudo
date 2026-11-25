-- Nível médio do áudio (dB) medido no upload: permite avisar quando a faixa de áudio da vinheta está muda.
ALTER TABLE content_studio.render_assets ADD COLUMN mean_volume_db double precision;
