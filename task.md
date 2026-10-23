# TrueScore — Task Tracker

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` deferred (with reason)
Update this file whenever a task changes state. Design details live in `architecture.md`.

## Phase 0 — Repo & docs
- [x] Read Project_Knowledge.md, define architecture (`architecture.md`)
- [x] Task tracker (`task.md`)
- [x] Repo skeleton, `.gitignore`, README with local setup

## Phase 1 — Foundation (accounts, academics, audit)
- [x] Django project, split settings (base/dev/prod/test), env loading
- [x] `core`: permissions, throttles, pagination (max 100), client IP, security headers, internal secret
- [x] `academics`: AcademicYear, SchoolClass, Section, Subject, Chapter + admin CRUD API
- [x] `accounts`: custom User (role, token_version, must_change_password), StudentProfile
- [x] Cookie JWT auth (access 15 min / refresh 7 d rotated + blacklisted), CSRF enforced, token_version check
- [x] Login lockout (5 tries → 15 min), forced password change on first login, `/me`
- [x] Admin students: CRUD, CSV import with generated passwords, reset password, suspend, force logout
- [x] Year-end promotion
- [x] `audit`: append-only AuditLog + helper, admin list API
- [x] Seed command (classes 1–12, sections, subjects, demo admin/students)

## Phase 2 — Video library & progress
- [x] Video + WatchProgress models
- [x] Storage: R2 presign (boto3) + local signed dev fallback
- [x] Admin: upload-url, video CRUD (draft/published, order)
- [x] Student: list own class's published videos with progress, play-url, 15 s heartbeat (capped delta, 90 % rule)
- [x] Student progress dashboard endpoint (`/me/progress`)

**Gate 1:** videos + progress can go live to students once Phase 2 tests pass.

## Phase 3 — Exam engine
- [x] Question bank models (+ options, versioning on edit-after-use) and admin CRUD
- [x] Question CSV import
- [x] Exam, ExamTarget, ExamPart, ExamQuestion + admin CRUD (paper editable only in draft)
- [x] Generator (manual pick + rule fill, per-student pools)
- [x] Schedule / unschedule (paper lock)
- [x] Student: upcoming exams, start (atomic, window, section, access code, IP allowlist, SEB), shuffled paper with option tokens
- [x] Save answer (deadline + 10 s grace, device lock, ip_change), resume, events, submit (idempotent), auto-submit
- [x] Grading engine (all 5 types, negative marks), manual marking for short answers
- [x] Internal sweep + warmup endpoints

## Phase 4 — Results, monitor, hardening
- [x] Publish per section, rank in section, 403 before publish
- [x] Student results list + detail (review with explanations if allowed)
- [x] Analytics (avg/high/low/pass rate/distribution/per-question accuracy)
- [x] Regrade with answer-key fix (audited)
- [x] Live monitor + interventions: extend / terminate / reset / release device (reason required, audited)
- [x] Post-exam flags report (timeline + late answer changes)
- [x] Security test suite (object-level access, answer key never in payload, clock, one attempt, results lock)

**Gate 2:** no real exam until security tests pass **and** a 300-user load test passes.
  - Security tests: ✅ 71 backend tests passing (`cd backend && .venv/bin/pytest`)
  - Load test: ⏳ script ready (`loadtest/exam.js`); must be **run** against the deployed Render instance
- [ ] Run the 300-user k6 load test on staging and record p95 numbers here

## Phase 5 — Frontend (Next.js)
- [x] Scaffold: Next.js + TS + Tailwind, `/api` rewrite, api client with CSRF, `middleware.ts` route guard
- [x] UI primitives (button, card, input, badge, table, dialog)
- [x] Login + forced password change
- [x] Student: dashboard, videos (subject → chapter → player with watermark + heartbeat), profile
- [x] Student: exams list, attempt page (fullscreen guard, proctor watch, timer, navigator, offline queue, watermark)
- [x] Student: results list + detail
- [x] Admin: dashboard, classes/sections/subjects/chapters, students (+CSV import), videos (upload)
- [x] Admin: question bank, exam builder (parts, rules, generate, schedule), monitor, results/analytics/publish, audit log
- [x] Simple mode for classes 1–3 (large buttons)

## Phase 6 — DevOps
- [x] GitHub Actions: CI (tests, pip-audit, npm audit, build)
- [x] GitHub Actions: sweep cron, warm-up, nightly encrypted backup to R2
- [x] Render blueprint (`render.yaml`), Vercel config, env var docs
- [x] k6 load test script (300 users: start burst + answer saves)

## Next up
- [ ] Deploy: Supabase, Upstash, R2 bucket + CORS, Render (render.yaml), Vercel; set GitHub secrets
- [ ] Visual QA of every page in a real browser (desktop + phone); only API flows were smoke-tested end-to-end
- [ ] Frontend tests (Playwright): login, start/answer/submit exam, publish → student sees result
- [ ] Bulk "download credentials" for a whole section after password resets
- [ ] Image upload size check client-side (compress to WebP < 200 KB)

## Deferred (phase 2 of the product)
- [-] Teacher role UI (role + `IsTeacher` permission exist; no screens or class-scoped endpoints yet)
- [-] HLS conversion via GitHub Actions ffmpeg; AES-128 encrypted segments
- [-] Report card PDF
- [-] 4-digit PIN login for classes 1–3
- [-] Excel question import (CSV only in v1)
- [-] Email notifications via HTTP email API

## Before the first real exam (operational checklist)
- [ ] Warm-up pings scheduled for school hours and 30 minutes before the exam
- [ ] Exam access code and target sections set; paper locked (Scheduled)
- [ ] Every student has logged in once and changed their password
- [ ] Invigilator briefed: what full-screen warnings mean, how to extend time
- [ ] Live monitor open on the admin laptop; Sentry alerts on
- [ ] Results left unpublished until analytics and the answer key are checked
- [ ] Parental consent process confirmed with the school (DPDP Act)

## Log
- 2026-10-23 — Frontend complete (23 routes, lint/typecheck/build clean, 0 npm audit vulns after upgrading Next 15.5.4 → 15.5.28 for a critical RCE advisory). DevOps files added. DRF bumped to 3.18.3 after pip-audit findings. End-to-end smoke test through the Next proxy passes.
- 2026-10-23 — Backend Phases 1–4 complete: 8 apps, ~45 endpoints, 71 tests passing. Starting frontend.
- 2026-10-23 — Architecture and task tracker created; starting Phase 0/1.
