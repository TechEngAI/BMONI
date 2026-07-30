# GhostGuard Backend

FastAPI backend for GhostGuard Part 1: Supabase Auth registration/login, company setup, role management, worker onboarding, and Squad bank verification.

## Local Setup

1. Create a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```
```

4. Run `migrations/001_init.sql` in the Supabase SQL editor.
5. Start the API:

```bash
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Swagger docs are at `http://127.0.0.1:8000/docs`.

## Supabase Auth Setup

In Supabase, enable Email auth under `Authentication -> Providers -> Email`.

For password reset links, set your site URL and redirect URLs under `Authentication -> URL Configuration`. Use your frontend URL, for example:

```text
http://localhost:3000
http://localhost:3000/reset-password
```

Optional phone verification uses Supabase Phone Auth. Enable it under `Authentication -> Providers -> Phone` and connect Twilio in the Supabase dashboard.

This backend does not send email or SMS directly. Supabase Auth sends signup confirmation and password reset emails automatically.

## Auth Model

Supabase owns authentication in `auth.users`. GhostGuard profile tables link to Supabase users through:

```text
admins.auth_user_id -> auth.users.id
workers.auth_user_id -> auth.users.id
```

Protected routes validate the bearer token with `supabase.auth.get_user(token)`.

## Key Endpoints

- `POST /auth/admin/register`
- `POST /auth/admin/login`
- `POST /auth/admin/refresh`
- `POST /auth/admin/logout`
- `POST /auth/admin/forgot-password`
- `POST /auth/admin/reset-password`
- `GET /admin/company`
- `PUT /admin/company`
- `POST /admin/roles`
- `GET /admin/roles`
- `PATCH /admin/workers/{worker_id}/verify-bank`
- `PATCH /admin/workers/{worker_id}/reactivate`
- `POST /auth/worker/register`
- `POST /auth/worker/login`
- `GET /worker/profile`
- `POST /worker/bank/lookup`
- `POST /worker/bank/submit`

## Railway

Railway uses the included `Procfile` and `railway.json`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

