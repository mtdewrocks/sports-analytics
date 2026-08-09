# Security & Code Review — sports-analytics
Reviewed: 2026-07-24. Scope: backend (FastAPI), frontend (React/Vite), deploy config, utility scripts.

Overall: solid foundation — passwords are bcrypt-hashed, Stripe webhooks verify signatures, SQL goes through SQLAlchemy ORM (no injection found), user-facing data filtering is pandas-based (no query injection), no XSS sinks found in the frontend, and no secrets are committed to git. The issues below are ranked by priority.

---

## High priority — fix before public release

### 1. Unauthenticated debug/ops endpoints
- `GET /api/db-test` (backend/app/main.py) returns the first 30 characters of `DATABASE_URL`. For a Render Postgres URL (`postgresql://user:password@...`) that exposes part of your credentials, plus raw DB error strings on failure.
- `GET /api/clear-cache` (main.py) lets anyone wipe every data cache. Each reload re-downloads ~10 files from GitHub; hitting it in a loop is an easy denial-of-service.
- `GET /api/mlb/debug` (backend/app/routers/mlb.py) is explicitly no-auth and triggers a full data load; also reveals internal file/column structure.

**Fix:** delete these endpoints, or protect them with `require_access` (better: an admin-only dependency). Never return any part of `DATABASE_URL` or raw exception text.

### 2. Hardcoded fallback SECRET_KEY
`config.py` defaults to `"changeme-in-production-use-long-random-string"`. If the env var is ever missing (misconfigured deploy, new environment), every JWT becomes forgeable — anyone could mint tokens for any user ID. render.yaml does set `generateValue: true`, but the safe pattern is to fail loudly:

```python
SECRET_KEY: str  # no default — app refuses to start without it
```

### 3. No rate limiting on auth endpoints
`/auth/login` and `/auth/register` accept unlimited attempts — credential-stuffing and brute-force are trivial, and bots can mass-register trial accounts. Add [slowapi](https://slowapi.readthedocs.io/) (e.g. 5/min on login, 3/hour on register per IP) or put Cloudflare in front.

### 4. Internal error details returned to clients
`register`/`login` return `detail=f"...: {str(e)}"` on unexpected errors. Exception text can leak DB schema, file paths, or library internals. Log the exception server-side (you already do) and return a generic message.

### 5. Production database is SQLite on ephemeral disk
`render.yaml` sets `DATABASE_URL: sqlite:///./sports_analytics.db`. On Render, the filesystem is wiped on every deploy/restart — **all users and subscriptions would be lost**. If you've overridden this with Postgres in the dashboard, remove the misleading default from render.yaml; otherwise switch to Render Postgres before launch.

---

## Medium priority

### 6. `is_active` is never checked
`models.User.is_active` exists but `get_current_user` ignores it, and JWTs live 7 days with no revocation. You currently have **no way to ban or disable an account**. Add `if not user.is_active: raise 401` in `get_current_user` (dependencies.py).

### 7. No password policy
`UserRegister` accepts any password, including `"a"`. Add a Pydantic validator: minimum 8 characters is a reasonable floor.

### 8. bcrypt rounds lowered to 8
`bcrypt__rounds=8` in auth/router.py is weaker than the default 12 (~16x faster to crack offline). If 12 is too slow on your instance, use 10 — but 8 is below current guidance.

### 9. Email enumeration on /auth/register
"Email already registered" confirms which emails have accounts. Combined with no rate limiting, an attacker can harvest your user list. Common mitigation: generic response + rate limiting (this one is often accepted as a business tradeoff — but fix #3 regardless).

### 10. query_users.py output not gitignored
The script exports all user PII (emails, names, states) to `users_export.xlsx` in the repo root. It is **not** in .gitignore — one careless `git add .` publishes your customer list. Add `users_export.xlsx` (and consider `query_users.py` itself) to .gitignore. Note: frontend/.env was committed in your initial commit — it only contained an empty `VITE_API_URL`, so no action needed, but be aware it lives in git history.

### 11. Data supply chain runs through public GitHub
All stats files load at runtime from raw.githubusercontent.com URLs (config.py), including this repo itself (`MLB_BASE_URL`). Implications: (a) if the repo is public, anyone can download the exact data your customers pay for, free; (b) anyone with push access to those repos controls what your app serves; (c) GitHub raw is not a CDN — outages or rate limits take your app down. Consider moving paid data to private object storage (S3/R2) fetched with credentials.

---

## Low priority / code quality

- **CORS** allows `localhost:3000` and `localhost:5173` in production (main.py). Harmless-ish, but make the origin list env-driven so prod only allows your real domain.
- **JWT lifetime** of 7 days with no refresh/revocation is long for a paid product; consider shorter access tokens.
- **Token in localStorage** (frontend) is standard but XSS-exposed; you have no XSS sinks today — keep it that way (avoid `dangerouslySetInnerHTML`).
- **requirements.txt is unpinned** (only bcrypt is pinned). A bad upstream release can break or compromise a deploy. Pin versions (`pip freeze > requirements.txt`) and consider `pip-audit` in CI.
- **_run_migrations() swallows all exceptions** (main.py) — a real migration failure (disk full, permissions) is silently ignored. Catch the specific "duplicate column" error, log everything else. Longer term: you already have alembic in requirements — use it.
- **`@app.on_event("startup")`** is deprecated in FastAPI; migrate to lifespan handlers.
- **NBA/NFL `stat` query params** index DataFrame columns directly; an unknown stat raises KeyError → 500. Validate against an allowlist and return 400.
- **backend/sports_analytics.db** exists locally with possible real user data — it's gitignored (good), just don't share the folder.

---

## What checked out fine
No SQL injection (ORM throughout), no command execution/eval/pickle, Stripe webhook signature verification correct, checkout/portal properly authed, no secrets in git history, `.env` files gitignored, password hashing with per-user salts via bcrypt, generic error on failed login, frontend has no XSS sinks, API routes consistently gated by `require_access`.
