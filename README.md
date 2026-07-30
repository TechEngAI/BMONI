# GhostGuard

AI-powered ghost worker detection and payroll fraud prevention for Nigerian businesses.

GhostGuard combines GPS attendance, device fingerprinting, IP geolocation, BMONI payment rails, and a machine learning anomaly engine to flag suspicious payroll behavior before salaries are disbursed — protecting the payroll pool so every worker gets paid correctly.

## What it does

- Detects ghost workers, proxy check-ins, and impossible travel using GPS and attendance patterns (physical workers).
- Detects device-fingerprint reuse, IP reuse, and impossible-travel patterns for remote workers.
- Uses a batch-scored Isolation Forest ML model to score payroll risk and generate trust verdicts across the full worker pool.
- Integrates with BMONI for bank account verification, smart wallet funding, and payroll disbursement.
- Supports Admin, HR, and Worker workflows with role-based access.

## Repo structure

- `backend/` — FastAPI backend, Supabase integration, BMONI payment orchestration, fraud/risk scoring, and API endpoints.
- `frontend/` — Next.js 14 App Router frontend for auth, dashboards, attendance, HR review, and admin controls.

## Key features

- GPS geofencing and attendance validation (physical workers)
- Device fingerprinting and buddy-punch detection (physical workers)
- Device fingerprinting, IP-reuse, and impossible-travel detection (remote workers)
- BMONI bank account verification, smart wallet, and payout disbursement flows
- Async payout status resolution (BMONI payouts resolve pending → success/failed) with a polling fallback for status confirmation
- HR invite-code flow (admin generates code → HR enters code to register)
- Payroll run scoring with fraud signal analysis, run once per payroll batch across all workers
- Wallet funding and payout management
- Audit logs and multi-tenant company isolation
- Disclosed (non-covert) device/location data collection notice for remote workers

## Tech stack

- Frontend: Next.js 14, TypeScript, Tailwind CSS
- Backend: FastAPI, Python, Pydantic
- Database/Auth: Supabase PostgreSQL + Supabase Auth
- ML: scikit-learn Isolation Forest (batch-scored)
- Payments: BMONI API (bank verification, smart wallet, offramp/disbursement)
- Deployment: Vercel + Railway

## Getting started

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# fill in environment variables
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# fill in environment variables
npm run dev
```

## Documentation

- `docs/TECHNICAL.md` — full technical architecture and backend flow summary
- `docs/PITCH_SLIDES.md` — investor/demo pitch slide deck structure

## Notes

- HR invites use an invite-code flow (admin generates a code, HR enters it to register) rather than email redirect links.
- BMONI uses 3-digit CBN bank codes (e.g. `058`, `044`), not 6-digit padded codes.
- BMONI payouts are asynchronous; status is confirmed via a polling endpoint (`POST /admin/payroll/receipts/{receipt_id}/refresh-status`) rather than a webhook, since no public webhook endpoint is reachable from localhost.
- The backend links Supabase auth users to application profiles for admins, workers, and HR officers.

## Contact

For more details, open `backend/app/main.py` for the API entry point and `frontend/app` for the route structure.