ALTER TABLE content_studio.news_items ADD COLUMN radar jsonb NOT NULL DEFAULT '{}'::jsonb;
