-- Volumes por trecho, nivelamento das vinhetas e o vídeo da fala guardado para "remixar" sem refazer o ComfyUI.
ALTER TABLE content_studio.renders
    ADD COLUMN intro_volume       double precision NOT NULL DEFAULT 1.0,
    ADD COLUMN outro_volume       double precision NOT NULL DEFAULT 1.0,
    ADD COLUMN background_volume  double precision NOT NULL DEFAULT 0.0,
    ADD COLUMN normalize_vignettes boolean         NOT NULL DEFAULT true,
    ADD COLUMN main_path          text,
    ADD COLUMN music_in_video     boolean          NOT NULL DEFAULT false;  -- trilha mixada dentro do vídeo do ComfyUI
