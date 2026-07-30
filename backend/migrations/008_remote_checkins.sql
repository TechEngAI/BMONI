CREATE TABLE IF NOT EXISTS remote_checkins (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id UUID REFERENCES workers(id) ON DELETE CASCADE NOT NULL,
  checked_in_at TIMESTAMPTZ DEFAULT NOW(),
  ip_address TEXT NOT NULL,
  device_fingerprint TEXT NOT NULL,
  geo_lat DECIMAL,
  geo_lng DECIMAL,
  geo_city TEXT,
  geo_country TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_remote_checkins_worker_checked_in ON remote_checkins(worker_id, checked_in_at DESC);

ALTER TABLE workers ADD COLUMN IF NOT EXISTS work_mode TEXT NOT NULL DEFAULT 'physical'
  CHECK (work_mode IN ('physical', 'remote'));

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
