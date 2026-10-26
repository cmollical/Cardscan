-- Freeze model/rate/limit assumptions for each explicitly authorized paid job.
-- Existing observations, catalog, inventory and media are untouched.
ALTER TABLE vision_jobs ADD COLUMN settings_json TEXT;
ALTER TABLE vision_jobs ADD COLUMN started_at TEXT;
CREATE INDEX vision_execution_day ON vision_jobs(owner_id,started_at);
PRAGMA user_version=6;
