CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  industry VARCHAR(100),
  size VARCHAR(50),
  office_lat DECIMAL(10,8),
  office_lng DECIMAL(11,8),
  geofence_radius INTEGER DEFAULT 100,
  work_start_time TIME DEFAULT '08:00',
  work_end_time TIME DEFAULT '18:00',
  working_days VARCHAR(20) DEFAULT 'MON-FRI',
  payroll_cycle VARCHAR(20) DEFAULT 'MONTHLY',
  timezone VARCHAR(50) DEFAULT 'Africa/Lagos',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admins (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID REFERENCES companies(id),
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  middle_name VARCHAR(100),
  email VARCHAR(255) UNIQUE NOT NULL,
  phone_number VARCHAR(20) UNIQUE,
  gender VARCHAR(20),
  date_of_birth DATE,
  status VARCHAR(20) DEFAULT 'ACTIVE',
  verif_channel VARCHAR(10) DEFAULT 'email',
  last_login TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  role_name VARCHAR(150) NOT NULL,
  department VARCHAR(100),
  grade_level VARCHAR(50),
  headcount_max INTEGER NOT NULL,
  headcount_filled INTEGER DEFAULT 0,
  gross_salary DECIMAL(15,2) NOT NULL,
  pension_deduct DECIMAL(15,2) DEFAULT 0,
  health_deduct DECIMAL(15,2) DEFAULT 0,
  other_deductions DECIMAL(15,2) DEFAULT 0,
  work_type VARCHAR(20) DEFAULT 'ONSITE',
  invite_code VARCHAR(30) UNIQUE NOT NULL,
  code_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  company_id UUID REFERENCES companies(id),
  role_id UUID REFERENCES roles(id),
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  middle_name VARCHAR(100),
  email VARCHAR(255) UNIQUE NOT NULL,
  phone_number VARCHAR(20) UNIQUE,
  gender VARCHAR(20),
  date_of_birth DATE,
  home_address TEXT,
  state_of_origin VARCHAR(100),
  next_of_kin_name VARCHAR(200),
  next_of_kin_phone VARCHAR(20),
  emergency_contact_name VARCHAR(200),
  emergency_contact_phone VARCHAR(20),
  nin VARCHAR(20),
  bank_verified BOOLEAN DEFAULT FALSE,
  status VARCHAR(20) DEFAULT 'PENDING_BANK',
  verif_channel VARCHAR(10) DEFAULT 'email',
  completeness_score DECIMAL(3,2) DEFAULT 0.00,
  has_company_device BOOLEAN DEFAULT FALSE,
  device_id VARCHAR(255),
  last_login TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS worker_bank_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id UUID REFERENCES workers(id) ON DELETE CASCADE,
  bank_name VARCHAR(100) NOT NULL,
  bank_code VARCHAR(10) NOT NULL,
  account_number VARCHAR(20) NOT NULL,
  account_name VARCHAR(200) NOT NULL,
  match_score DECIMAL(5,2),
  match_status VARCHAR(20),
  is_active BOOLEAN DEFAULT TRUE,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bank_account_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id UUID REFERENCES workers(id),
  old_account VARCHAR(20),
  new_account VARCHAR(20),
  old_bank_code VARCHAR(10),
  new_bank_code VARCHAR(10),
  changed_at TIMESTAMPTZ DEFAULT NOW(),
  approved_by UUID REFERENCES admins(id),
  reason TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id UUID NOT NULL,
  actor_type VARCHAR(10) NOT NULL,
  action VARCHAR(100) NOT NULL,
  target_id UUID,
  target_type VARCHAR(20),
  metadata JSONB,
  ip_address VARCHAR(45),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admins_auth_user_id ON admins(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_admins_company_id ON admins(company_id);
CREATE INDEX IF NOT EXISTS idx_workers_auth_user_id ON workers(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_workers_company_id ON workers(company_id);
CREATE INDEX IF NOT EXISTS idx_workers_role_id ON workers(role_id);
CREATE INDEX IF NOT EXISTS idx_roles_company_id ON roles(company_id);
CREATE INDEX IF NOT EXISTS idx_worker_bank_accounts_worker ON worker_bank_accounts(worker_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_id, actor_type);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_roles_updated_at ON roles;
CREATE TRIGGER trg_roles_updated_at
BEFORE UPDATE ON roles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- Grant table-level permissions to the service_role.
-- Without this every backend DB query (all service-role key calls) fails with 42501.
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

