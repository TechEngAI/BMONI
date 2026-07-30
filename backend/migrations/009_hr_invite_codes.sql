CREATE TABLE IF NOT EXISTS hr_invite_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(30) UNIQUE NOT NULL,
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  created_by_admin_id UUID REFERENCES admins(id),
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone_number VARCHAR(20),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
  used_at TIMESTAMPTZ,
  hr_officer_id UUID REFERENCES hr_officers(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hr_invite_codes_code ON hr_invite_codes(code);
CREATE INDEX IF NOT EXISTS idx_hr_invite_codes_company ON hr_invite_codes(company_id);
