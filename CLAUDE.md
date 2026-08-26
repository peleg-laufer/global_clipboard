# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About & direction

global_clipboard started as a self-hosted, single-user clipboard sync tool (shared text buffer + three file slots) meant for one person's own devices on a LAN. **It is now mid-pivot to a real production app** — multi-user, published on the Play Store and eventually the App Store, used by real people over the internet. Treat this repo as actively migrating, not as a finished single-user tool: current code (FastAPI + MongoDB) is the *pre-migration* implementation, kept working until the target architecture below replaces it.

**Target architecture** (see Migration Roadmap for sequencing):
- **Supabase** (managed Postgres + built-in Auth + Storage + Row Level Security) replaces the hand-rolled FastAPI/MongoDB backend. This retires most of `src/clip_api.py` and `src/clip_db_handler.py`.
- **Private per-account data model**: each authenticated user gets their own text history + 3 file slots, scoped by `user_id`. Not shared "rooms" — keep it simple.
- **Rollout order**: web (browser) first, then Android, then iOS.

Why Supabase over a self-hosted Postgres + hand-rolled auth: it still delivers real SQL/Postgres/RLS experience (the explicit goal of moving off MongoDB) while retiring the auth-boilerplate and DB-ops work that has low learning value relative to the effort. See Working Agreement below for how that tradeoff was decided.

## Working agreement (how to collaborate on this project)

This was explicitly negotiated with the user and should shape how you operate here, not just what you build:

- **No real learning value (frontend/plumbing work)** → just do it directly, don't ask first.
- **Genuine decision points** (architecture, tooling, tradeoffs) → present options with pros/cons and let the user decide. Don't silently pick for them.
- **New tech/concepts worth learning** → name the technology and the basic terms, then let the user research it independently — or offer sample code plus a fuller explanation if they ask for it instead.
- **Real-company/startup terminology and working methods** (staging vs. production, CI/CD, RLS, etc.) → introduce naturally when it fits the moment. Not a goal to force, just a lens to apply when relevant.

## Commands (current, pre-migration)

### Backend (from `src/`)

```bash
pip install fastapi "pymongo[srv]" pydantic python-multipart
python -m fastapi dev clip_api.py       # dev server with reload, http://localhost:8000
```

- Requires MongoDB running on `localhost:27017` (see `constants.CONNECTION_STRING`).
- Interactive API docs: `http://localhost:8000/docs`.
- No backend test suite exists yet. No Python linter/formatter is configured.

### Frontend (from `app/flutter_front/`)

```bash
flutter pub get
flutter run                              # connects to http://localhost:8000 by default
flutter analyze                          # lints (flutter_lints, see analysis_options.yaml)
flutter test                             # currently just the default (unused) counter-app template test
```

- `lib/main.dart` is a single-file MVP (~800 lines) — app shell, home page state, file-slot widgets, all in one file. Expect this to get split up during the Supabase data-layer migration (Phase 3).
- Backend base URL is hardcoded as `kBaseUrl` in `lib/main.dart`.

## Current architecture (pre-migration, still true today)

### Backend: routes vs. business logic

- `clip_api.py` — FastAPI route handlers only: validate slot/params, call into `clip_db_handler`, translate results into HTTP responses/status codes (204 empty, 400/404/409 errors). No DB or filesystem code belongs here.
- `clip_db_handler.py` — all business logic: async `pymongo` queries, file I/O on disk, Pydantic models (`FileMeta` includes `file_path` and is internal-only; `PublicFileMeta` omits it and is what the API returns). Has no knowledge of HTTP; raises domain exceptions (`IllegalSlotError`, `TakenSlotError`).
- `constants.py` — single source of truth for slot count (`ALLOWED_SLOTS`), the pre-existing-files sentinel (`PRE_EXISTING_FILES_SLOT = -1`), text history depth (`ALLOWED_TEXT_POSITIONS`), the Mongo connection string, and log file paths.

### File slot model

- Three slots (`0, 1, 2`), one file each. Files not assigned to a slot live at slot `-1` ("pre-existing"), surfaced via `/files/pre-existing`.
- Files are stored on disk renamed to their `file_uuid` (+ original extension); the original `file_name` lives only in MongoDB metadata.
- On startup, the server reconciles disk state with the DB (`setup_db` → `files_collection_setup_and_validation`): adds untracked files as slot `-1`, drops DB records with no file on disk, resolves duplicate/illegal slot assignments by moving files to `-1`. This self-healing exists because the Pi's `files/` folder could be edited manually — that concern mostly disappears once files live in per-user Supabase Storage (see Phase 1 decision point below).

### Text history model

- Up to 5 saves (`ALLOWED_TEXT_POSITIONS`), position `0` = most recent. Writes are full delete-and-reinsert of the collection with sequential positions (`add_save_to_textbox`, `fix_positions`), not in-place updates — this is how position integrity and the 5-item cap are maintained through undo. In Postgres this becomes a trigger/function instead (Phase 1).
- `POST /text` no-ops if the new text equals the last save.

### Logging

Both backend files configure their own logger to separate files (`constants.API_LOG_FILE_PATH`, `constants.DB_LOG_FILE_PATH`), overwritten each run. Convention: `log.debug` for expected/normal paths, `log.warning` for expected 4xx client errors, `log.error`/`log.exception` for real failures. Match this when adding log calls.

### Flutter client

Single file (`lib/main.dart`), heavily commented — written collaboratively as a learning exercise. Structure: `kBaseUrl` + a `Dio` instance for all HTTP → `FileMeta` (client-side mirror of `PublicFileMeta`) → `GlobalClipApp` (StatelessWidget shell) → `HomePage`/`_HomePageState` (StatefulWidget holding textbox + slot state) → `_SlotCard`/`_SlotCardState` (one per file slot). Drag-and-drop (`desktop_drop`) and file picking (`file_picker`/`file_saver`/`cross_file`) are wired at the slot-card level.

Backend and Flutter client share no types — API shape changes must be hand-mirrored in `main.dart`.

## Migration roadmap

Each phase needs its own decision points worked out with the user before being built — this is a checklist of what's next, not a spec to implement blind.

1. **Supabase schema & RLS** — Postgres tables replacing the Mongo collections (user-scoped text saves with a trigger-based 5-cap, user-scoped files with `UNIQUE(user_id, slot)`), RLS enabled so users only see their own rows. Open question: keep a "pre-existing/unassigned file" concept at all, given Storage removes the reason it existed.
2. **Flutter auth** — `supabase_flutter`, sign-up/login/logout (email+password to start).
3. **Flutter data layer migration** — replace Dio/FastAPI calls with Supabase client calls; split `main.dart` up while doing it. Decide whether to retire or archive `clip_api.py`/`clip_db_handler.py`/MongoDB.
4. **Real tests** — replace the stale default Flutter test; cover auth + data flows; sanity-check that RLS actually isolates users.
5. **Web deploy** — `flutter build web`, pick a static host, split dev/prod Supabase projects.
6. **Android release** — real `applicationId`, privacy policy, release keystore, Play Console.
7. **iOS release** — Apple Developer Program, real bundle ID, TestFlight, App Store review (including in-app account deletion, required once accounts exist).
8. **Ongoing hygiene** — CI/CD, error monitoring, secrets management — added as the project's cadence justifies, not upfront.
