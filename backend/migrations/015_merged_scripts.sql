-- Roteiro criado a partir de várias notícias: a principal fica em news_item_id, as demais aqui.
ALTER TABLE content_studio.scripts ADD COLUMN extra_news_item_ids uuid[] NOT NULL DEFAULT '{}';
