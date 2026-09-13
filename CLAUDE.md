# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About & direction

global_clipboard is a self-hosted, single-user clipboard sync backend (shared text buffer + three file slots) built with **FastAPI + MongoDB**. The earlier plan to migrate to Supabase and ship to app stores was **dropped (2026-09-13)**. The goal now is to finish this as a polished **Python backend resume project**, pinned on GitHub. The Flutter client is being moved to its own repo, so this repo should read as Python.

**Finishing scope, in order:** bug fixes + cleanup (env-based config, lifespan, requirements.txt, ruff) → pytest suite against a test MongoDB → Docker + docker-compose → GitHub Actions CI → README rewrite. Timebox is ~1.5 days; CI is the first thing cut if behind. Nothing beyond this scope.

## Working agreement (how to collaborate on this project)

This was explicitly negotiated with the user and should shape how you operate here, not just what you build:

- **The user writes all in-scope code themselves** (fixes, tests, Docker, CI, README). Don't write it for them unless asked. Review, hint, and name the concepts to research instead.
- **No real learning value (plumbing, housekeeping like this file)** → just do it directly, don't ask first.
- **Genuine decision points** (architecture, tooling, tradeoffs) → present options with pros/cons and let the user decide. Don't silently pick for them.
- **New tech/concepts worth learning** → name the technology and the basic terms, then let the user research it independently — or offer sample code plus a fuller explanation if they ask for it instead.
- **Real-company terminology and working methods** (CI/CD, containers, test isolation, etc.) → introduce naturally when it fits the moment. Not a goal to force, just a lens to apply when relevant.

## Commands

From `src/`:

```bash
pip install fastapi "pymongo[srv]" pydantic python-multipart
python -m fastapi dev clip_api.py       # dev server with reload, http://localhost:8000
```

- Requires MongoDB running on `localhost:27017` (see `constants.CONNECTION_STRING`).
- Interactive API docs: `http://localhost:8000/docs`.
- No test suite, requirements file, linter, Dockerfile, or CI exists yet; they're in progress (see scope above). Update this section as they land.

## Architecture

### Backend: routes vs. business logic

- `clip_api.py` — FastAPI route handlers only: validate slot/params, call into `clip_db_handler`, translate results into HTTP responses/status codes (204 empty, 400/404/409 errors). No DB or filesystem code belongs here.
- `clip_db_handler.py` — all business logic: async `pymongo` queries, file I/O on disk, Pydantic models (`FileMeta` includes `file_path` and is internal-only; `PublicFileMeta` omits it and is what the API returns). Has no knowledge of HTTP; raises domain exceptions (`IllegalSlotError`, `TakenSlotError`).
- `constants.py` — single source of truth for slot count (`ALLOWED_SLOTS`), the pre-existing-files sentinel (`PRE_EXISTING_FILES_SLOT = -1`), text history depth (`ALLOWED_TEXT_POSITIONS`), the Mongo connection string, and log file paths.

### File slot model

- Three slots (`0, 1, 2`), one file each. Files not assigned to a slot live at slot `-1` ("pre-existing"), surfaced via `/files/pre-existing`.
- Files are stored on disk renamed to their `file_uuid` (+ original extension); the original `file_name` lives only in MongoDB metadata.
- On startup, the server reconciles disk state with the DB (`setup_db` → `files_collection_setup_and_validation`): adds untracked files as slot `-1`, drops DB records with no file on disk, resolves duplicate/illegal slot assignments by moving files to `-1`. This self-healing exists because the `files/` folder can be edited manually on the host.

### Text history model

- Up to 5 saves (`ALLOWED_TEXT_POSITIONS`), position `0` = most recent. Writes are full delete-and-reinsert of the collection with sequential positions (`add_save_to_textbox`, `fix_positions`), not in-place updates — this is how position integrity and the 5-item cap are maintained through undo.
- `POST /text` no-ops if the new text equals the last save.

### Logging

Both backend files configure their own logger to separate files (`constants.API_LOG_FILE_PATH`, `constants.DB_LOG_FILE_PATH`), overwritten each run. Convention: `log.debug` for expected/normal paths, `log.warning` for expected 4xx client errors, `log.error`/`log.exception` for real failures. Match this when adding log calls.

### Client

The Flutter client (`app/flutter_front/`) is being moved to a separate repo and is out of scope here. It shares no types with the backend, so any API shape change must be mirrored there by hand.
