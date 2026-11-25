ALTER TABLE content_studio.news_searches ADD COLUMN report_context jsonb NOT NULL DEFAULT '{}'::jsonb;
