# TrueScore — Architecture

Education platform for classes 1–12: video library, student progress profile, secure exam engine and results.
Source of requirements: `../Project_Knowledge.md`. This file records **how** it is built and every decision that
deviates from or refines that document. Keep it current when the design changes.

## 1. System overview

```
                    ┌──────────────────────────── Browser ────────────────────────────┐
                    │  Next.js pages (student / admin)                                 │
                    │  video bytes ▲ ▼ (signed URL)            all JSON via /api/* ▼  │
                    └──────────────┼─────────────────────────────────────┼────────────┘
                                   │                                     │ same-origin
                       ┌───────────┴──────────┐            ┌─────────────┴──────────────┐
                       │ Cloudflare R2        │            │ Next.js (Vercel)            │
                       │ private bucket       │            │ rewrites /api/* → Django    │
                       │ MP4 now, HLS phase 2 │            │ middleware.ts route guard   │
                       └───────────▲──────────┘            └─────────────┬──────────────┘
                                   │ presign only                        │
                       ┌───────────┴─────────────────────────────────────▼──────────────┐
                       │ Django 5 + DRF (Render, gunicorn ×2)                            │
                       │ auth · academics · videos · exams · attempts · results · audit │
                       └───────┬───────────────────────────────┬────────────────────────┘
                               │                               │
                     ┌─────────▼─────────┐           ┌─────────▼─────────┐
                     │ PostgreSQL        │           │ Redis (Upstash)   │
                     │ (Supabase, DB only)│          │ throttles, lockout│
                     └───────────────────┘           └───────────────────┘
        GitHub Actions cron ──(X-Internal-Secret)──▶ /api/v1/internal/sweep-attempts · /warmup · backups
```

Rules that hold everywhere:

1. **Django is the only thing that talks to Postgres and Redis.** Next.js renders pages and proxies `/api/*`.
2. **The browser never holds the answer key, the clock, or the score.** It only deters and reports.
3. **Every query is filtered by `request.user` on the server.** IDs from the browser are never trusted on their own.
4. **Video bytes never pass through Django.** It only signs short-lived R2 URLs (PUT for upload, GET for play).

## 2. Repository layout

```
TrueScore/
  architecture.md        ← this file
  task.md                ← living task list / progress
  backend/               ← Django + DRF
    config/settings/     base.py, dev.py, prod.py, test.py
    apps/
      core/              permissions, throttles, storage (R2 + local dev), pagination, ip utils, internal auth
      accounts/          User, StudentProfile, cookie-JWT auth, login lockout, admin student mgmt, CSV import, promotion
      academics/         AcademicYear, SchoolClass, Section, Subject, Chapter
      videos/            Video, WatchProgress, play/upload URL signing, heartbeat
      exams/             Question(+versions), QuestionOption, Exam, ExamTarget, ExamPart, ExamQuestion, generator
      attempts/          Attempt, AttemptAnswer, ProctorEvent, start/save/submit, grading, sweep
      results/           ResultPublication, analytics, rank, student results, progress dashboard
      audit/             AuditLog (append-only) + audit() helper
  frontend/              ← Next.js App Router + TS + Tailwind
  .github/workflows/     ci.yml, cron-sweep.yml, warmup.yml, backup.yml
```

## 3. Backend

### 3.1 Authentication & sessions

| Concern | Implementation |
| --- | --- |
| Password hashing | `Argon2PasswordHasher` first in `PASSWORD_HASHERS`; min length 8 |
| Tokens | SimpleJWT access (15 min) + refresh (7 days, `ROTATE_REFRESH_TOKENS`, `BLACKLIST_AFTER_ROTATION`) |
| Transport | Both tokens in `httpOnly`, `Secure` (prod), `SameSite=Lax` cookies: `ts_access` (path `/`), `ts_refresh` (path `/api/v1/auth/`) |
| Auth class | `accounts.authentication.CookieJWTAuthentication` reads `ts_access`, verifies JWT, checks `token_version` claim == `user.token_version`, then **enforces CSRF** (same as DRF `SessionAuthentication`) |
| CSRF | Django CSRF cookie `csrftoken` (readable by JS) set by `GET /auth/csrf`; frontend sends `X-CSRFToken` on every unsafe request |
| Force logout | `user.token_version += 1` invalidates every access and refresh token at once |
| First login | `must_change_password=True` → every endpoint except `/me`, `/auth/change-password`, `/auth/logout` returns 403 `password_change_required` |
| Login lockout | 5 failures per username (and per IP) → 15-minute lockout, counter in cache |
| Device id | On login the server sets a long-lived httpOnly cookie `ts_device` (random). Used for the one-device exam rule |
| Route hint | `ts_role` (`student:0`, `admin:1` = role : must-change-password), httpOnly, lifetime = refresh token. Lets `middleware.ts` route page requests, because `ts_refresh` is path-scoped to `/api/v1/auth/` and invisible on page routes. Grants nothing by itself |

### 3.2 Authorization

- Permission classes in `core.permissions`: `IsAdmin`, `IsStudent`, `IsTeacher`, `PasswordChanged`, `InternalSecret`.
- URL prefixes split by audience: `/api/v1/…` (student + shared), `/api/v1/admin/…` (admin only), `/api/v1/internal/…` (cron, secret header). Each prefix has its own throttle scope.
- Student querysets always start from `request.user` (e.g. `Attempt.objects.filter(student=request.user)`), and videos/exams are filtered to the student's own class/section.

### 3.3 Data model (20 tables + framework tables)

Matches the schema in Project_Knowledge.md, with these **refinements**:

| Table | Addition | Why |
| --- | --- | --- |
| users | `must_change_password`, `full_name` | forced first-login change; display name for watermark |
| student_profiles | `academic_year_id` | roll_no unique per (academic_year, roll_no) |
| questions | `version`, `parent_id`, `numeric_answer`, `numeric_tolerance`, `created_by` | versioning on edit-after-use; numeric questions need a key |
| attempts | `section_id`, `device_id`, `last_seen_at`, `fullscreen_exits`, `grading_status`, `max_score` | rank per section at attempt time; one-device rule; live monitor "Disconnected"; auto-submit after N exits |
| attempt_answers | `change_count` | post-exam review ("20 answers changed in the last 30 s") |
| audit_logs | `reason` | interventions require a reason |

Unique constraints that enforce exam rules: `attempts (exam, student)`, `attempt_answers (attempt, question)`,
`watch_progress (student, video)`, `sections (class, name)`, `student_profiles (academic_year, roll_no)`,
`exam_targets (exam, section)`, `result_publications (exam, section)`, one `academic_years.is_current=True`.

Day-one indexes: `attempts (exam, status)`, `attempt_answers (attempt)`, `watch_progress (student)`,
`questions (subject, chapter, difficulty)`, `proctor_events (attempt)`.

### 3.4 Exam engine

**Lifecycle.** Stored `status`: `draft → scheduled → graded → published` (plus `closed` once the window ends).
`live` and `closed` are *derived* from the clock (`effective_status`) so no cron is needed to flip them:
`scheduled` + now in `[start_at, end_at]` ⇒ live; `scheduled` + now > `end_at` ⇒ closed.

**Paper lock.** Parts, exam questions and marks are editable only in `draft`. `schedule` validates the paper and
locks it. After that the only way to change grading is `POST /admin/exams/{id}/regrade` (audited, reason required).

**Generation.** `ExamPart.rule = {"chapters": [ids], "easy": n, "medium": n, "hard": n, "per_student": bool}`.
- `per_student=false`: generator picks the questions once and writes `exam_questions`.
- `per_student=true`: generator writes the whole eligible pool to `exam_questions` (so it is locked with the paper),
  and each attempt draws its own `n` per difficulty from that pool at start.

**Per-student shuffle and option tokens.** At start the server builds `attempt.question_order`:
`[{"q": question_id, "part": part_id, "marks": "2.00", "opts": [["k3Jf9a", option_id], …]}, …]`.
Question order and option order are shuffled per attempt, and each option is shown with a random per-attempt token
— never A/B/C/D and never the DB id — so "Q5 is C" or "option 1234" cannot be shared. Answers are sent as tokens and
mapped back to option ids server-side.

**Server-owned clock.** `deadline_at = min(started_at + duration, end_at)` (+ admin extensions). Saves after
`deadline_at + 10 s` are rejected; any request touching an expired attempt auto-submits it; the cron sweep
auto-submits the rest.

**One attempt / one device.** `unique(exam, student)` + start inside a transaction (IntegrityError ⇒ resume path).
The attempt stores the `ts_device` cookie value; requests from another device get 409 and log `second_login`.
Admin can release the device lock. *Refinement:* the lock is stored on the attempt row rather than only in Redis,
so a Redis eviction or free-tier outage cannot unlock an exam; Redis is used for throttles and lockouts.

**Grading** (`attempts.grading`):

| Type | Rule |
| --- | --- |
| `mcq_single`, `true_false` | correct option ⇒ +marks; wrong ⇒ −negative_marks; blank ⇒ 0 |
| `mcq_multi` | exact set match ⇒ +marks; any other non-empty ⇒ −negative_marks |
| `numeric` | `abs(answer − numeric_answer) ≤ numeric_tolerance` |
| `short_answer` | `is_correct=null`, goes to the marking screen; attempt `grading_status=pending_manual` |

**Refusals that leave evidence.** Checks that *log an event or auto-submit and then refuse* (second device,
late answer, IP change) run **outside** any `transaction.atomic()` block; only the final answer write runs under a
row lock (`select_for_update`) with the status/deadline re-checked. Otherwise the raised error would roll back the
very event or submit it was meant to record.

**Proctoring.** `POST /attempts/{id}/events` accepts `tab_switch, blur, fullscreen_exit, paste, copy, context_menu,
print, offline, heartbeat`. `heartbeat` only updates `last_seen_at`. `fullscreen_exit` past
`settings.max_fullscreen_exits` auto-submits. Server-detected events: `second_login`, `ip_change`, `late_answer`.

**Exam settings JSON**: `shuffle_questions`, `shuffle_options`, `max_fullscreen_exits` (0 = off),
`access_code`, `ip_allowlist` (CIDRs), `require_seb` + `seb_config_key`, `show_answers`.

### 3.5 Results

- `GET /results/{examId}` returns **403** unless a `ResultPublication` exists for (exam, attempt.section).
- Publish (`POST /admin/exams/{id}/publish`, all or chosen sections) requires the window to be over and no pending
  manual marking; it computes dense rank by score within each section and stores it on the attempt.
- Analytics: average, highest, lowest, pass rate, score distribution (10 buckets), per-question accuracy.
- `show_answers=false` hides the per-question review even after publish.

### 3.6 Videos

- Upload: `POST /admin/videos/upload-url` → presigned R2 PUT → browser uploads → `POST /admin/videos` saves metadata.
- Play: `GET /videos/{id}/play-url` → presigned GET valid `VIDEO_URL_TTL` (default 300 s), only for a published
  video of the student's own class.
- Heartbeat `POST /videos/{id}/progress {position_s, delta_s}` every 15 s; `delta_s` is capped at 20 s so progress
  cannot be faked by one request; complete at `seconds_watched ≥ 90 % of duration`.
- **Dev fallback:** if R2 env vars are absent, `core.storage.LocalSignedStorage` signs URLs to Django endpoints
  (`/api/v1/dev-storage/…`) that read/write `MEDIA_ROOT`, using `django.core.signing` with the same TTL. The app is
  fully runnable locally without any cloud account.

### 3.7 Audit

`audit.AuditLog` is append-only (`save()` refuses updates, `delete()` raises). `audit.services.audit(request, action,
entity, entity_id, before, after, reason)` is called by every admin mutation, re-grade, time extension, attempt reset
and publish.

### 3.8 Hardening

- `SecurityMiddleware` + HSTS, `X-Frame-Options: DENY`, `Referrer-Policy`, a strict API CSP
  (`default-src 'none'; frame-ancestors 'none'`) and `Permissions-Policy` set by `core.middleware.SecurityHeaders`.
- `Cache-Control: no-store` on every `/api/` response.
- DRF serializers validate input; uploads checked for type/size; pagination max 100.
- Throttles (Redis-backed cache): `login`, `password`, `answers`, `video_url`, `admin`.
- Client IP from `X-Forwarded-For` honouring `TRUSTED_PROXY_COUNT` only (Vercel + Render = 2 hops).
- No passwords/tokens/answers in logs; Sentry with `send_default_pii=False`.

## 4. Frontend

- Next.js App Router, TypeScript, Tailwind, hand-written shadcn-style primitives in `components/ui`.
- **Same-origin API:** `next.config` rewrites `/api/:path*` → `${BACKEND_URL}/api/:path*`. *Refinement:* Vercel
  and Render are different sites, so `SameSite=Lax` cookies would not be sent on cross-site `fetch`; proxying keeps
  cookies first-party and removes CORS from the hot path.
- `middleware.ts` reads the `ts_role` hint cookie purely to route students vs admins and to force the first-login
  password page; real authorization is always Django's.
- The API client (`lib/api.ts`) sends `X-CSRFToken` on unsafe methods, and on a 401 calls `/auth/refresh` once
  (shared across concurrent requests) and retries; if that fails it redirects to `/login?next=…`.
- Exam attempt page: `FullscreenGuard`, `ProctorWatch` (visibility/blur/copy/paste/contextmenu/print), `Timer`
  synced from server `deadline_at` + server time offset, `Navigator` with mark-for-review, answer queue in
  `localStorage` retried on reconnect, tiled watermark, `beforeunload` / back-button guard.
- Video page: `<video>` with `controlsList="nodownload"`, speed 0.75–2×, moving watermark, 15 s heartbeat,
  resume from last position, URL refetch on expiry.

## 5. Background jobs (GitHub Actions)

| Workflow | Schedule | Calls |
| --- | --- | --- |
| `cron-sweep.yml` | every 5 min | `POST /api/v1/internal/sweep-attempts` |
| `warmup.yml` | every 10 min 07:00–19:00 IST, Mon–Sat | `POST /api/v1/internal/warmup` (UptimeRobot can do 5 min) |
| `backup.yml` | nightly | `pg_dump | gpg` → R2, 14-day retention |
| `ci.yml` | PR / push | backend tests + `pip-audit`, frontend lint/typecheck/build + `npm audit` |

Cron and uptime pings target the **frontend** URL (`/api/v1/internal/*` through the Vercel rewrite), so the same
proxy path and `TRUSTED_PROXY_COUNT=2` apply to every request.

## 5a. Dependency baseline (2026-10-23)

| Package | Version | Note |
| --- | --- | --- |
| Django | 5.2.x LTS | |
| djangorestframework | 3.18.3 | ≥ 3.18.2 required (pip-audit: PYSEC-2026-3827/3828, CVE-2026-114136..8) |
| Next.js | 15.5.28 | ≥ 15.5.28 required (GHSA-9qr9-h5gf-34mp RCE in React flight protocol, and others) |
| React | 19.1.10 | |
| postcss / sharp | overridden in `package.json` | Next's nested copies had advisories; `next/image` optimisation is disabled |

## 6. Decisions log

| # | Decision | Reason |
| --- | --- | --- |
| D1 | Next.js proxies `/api/*` to Django | First-party cookies, CSRF works, no cross-site cookie issues |
| D2 | One-device lock on the attempt row (not only Redis) | Survives Redis eviction / free-tier outage |
| D3 | `live`/`closed` derived from the clock | No cron dependency for state flips |
| D4 | Per-attempt random option tokens | Defeats "answer is C" and DB-id sharing |
| D5 | Local signed-storage fallback | Runs locally / in CI without R2 |
| D6 | Username = roll number | Login is "roll number + password"; graduates are deactivated, not deleted |
| D7 | `deadline = min(start + duration, end_at)` | Late starters cannot run past the window |
| D8 | `ts_role` routing-hint cookie | Refresh cookie is path-scoped; middleware needs a long-lived signal |
| D9 | Evidence-logging checks run outside transactions | A refusal must not roll back the event it records |
| D10 | Charts are hand-written SVG/CSS, no chart library | Three small single-series charts; keeps the bundle ~110 kB |
