# TrueScore

Lessons, progress tracking and secure exams for classes 1–12: a video library, a student progress profile,
an exam engine with server-enforced integrity, and results that stay hidden until published.

- **Design and decisions:** [architecture.md](architecture.md)
- **Progress and what's next:** [task.md](task.md)
- **Original requirements:** `../Project_Knowledge.md`

Stack: Django 5.2 + DRF (API) · Next.js 15 App Router + TypeScript + Tailwind (UI) · PostgreSQL · Redis ·
Cloudflare R2 (videos). Runs on free tiers: Render, Vercel, Supabase, Upstash, R2.

## Run locally

Prerequisites: Python 3.12, Node 20+, PostgreSQL 16, Redis (optional locally — falls back to in-memory cache).

```bash
# 1. Backend
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # then set DJANGO_SECRET_KEY to a long random string
createdb truescore
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed --demo   # classes 1–12 + demo admin, students and a live exam
.venv/bin/python manage.py runserver 127.0.0.1:8000

# 2. Frontend (new terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                     # http://localhost:3000
```

Demo logins (from `seed --demo`): admin `admin` / `admin-pass-123`; students `8A01`…`8B06` / `student-pass-123`.
Without R2 credentials, uploads and video playback use a local signed-URL store in `backend/media/`.

## Tests

```bash
cd backend && .venv/bin/pytest          # 71 tests: auth, object-level access, exam integrity, grading, results lock
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Deploy (free tier)

1. **Database:** create a Supabase project; copy the pooled connection string (`sslmode=require`).
2. **Redis:** create an Upstash database; copy the `rediss://` URL.
3. **Storage:** create a private R2 bucket. Create two API tokens: *read-only* and *write (object put)*, scoped to
   the bucket. Add a CORS rule allowing `PUT` and `GET` from your frontend origin.
4. **API:** create a Render Blueprint from `render.yaml`; fill the `sync: false` env vars.
5. **Frontend:** import `frontend/` into Vercel; set `BACKEND_URL=https://<your-render-service>.onrender.com`.
6. **GitHub secrets** for the workflows: `API_URL` (the **frontend** URL, so requests go through the same proxy),
   `INTERNAL_CRON_SECRET` (same value as on Render), and for backups `BACKUP_DATABASE_URL`, `BACKUP_PASSPHRASE`,
   `R2_ACCOUNT_ID`, `R2_BACKUP_BUCKET`, `R2_BACKUP_ACCESS_KEY_ID`, `R2_BACKUP_SECRET_ACCESS_KEY`.
7. **UptimeRobot:** HTTP monitor on `https://<frontend>/api/v1/internal/warmup` every 5 minutes, 07:00–19:00 IST.
8. In the Render shell: `python manage.py seed` (classes 1–12, sections, subjects) and
   `python manage.py createsuperuser` (superusers get the `admin` role automatically).

### Restore test (monthly)

```bash
aws s3 cp s3://$BUCKET/db/<file>.sql.gz.gpg . --endpoint-url https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com
gpg --decrypt <file>.sql.gz.gpg | gunzip | psql "$SCRATCH_DATABASE_URL"
```

### Load test (Gate 2, before the first real exam)

See the header of [`loadtest/exam.js`](loadtest/exam.js): 300 simulated students start one exam within ~90 s and
save answers. Run it against a staging copy on the real Render instance.

## Before the first real exam

See the checklist at the bottom of [task.md](task.md).
