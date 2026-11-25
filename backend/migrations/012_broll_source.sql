-- Origem de cada sugestão de B-roll: 'lumiere' (busca automática) ou 'manual' (escolhida pelo editor).
-- As manuais sobrevivem a "rebuscar B-roll".
ALTER TABLE content_studio.broll_suggestions
    ADD COLUMN source text NOT NULL DEFAULT 'lumiere' CHECK (source IN ('lumiere','manual'));
