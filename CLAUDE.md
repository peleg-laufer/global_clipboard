# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About & direction

global_clipboard is a self-hosted, single-user clipboard sync backend (shared text buffer + three file slots) built with **FastAPI + MongoDB**. The earlier plan to migrate to Supabase and ship to app stores was **dropped (2026-09-13)**. The goal now is to finish this as a **Python backend portfolio project**, pinned on GitHub. The Flutter client is being moved to its own repo, so this repo should read as Python.

**Quality bar (set 2026-09-20 — this narrowed the goal):** the project exists to show the user taught themselves these technologies, which they consider already achieved. A recruiter will barely look at it. It does **not** need to be polished or production-grade. The only standard that matters: **if someone clones the repo and runs it, it works.** Anything that doesn't serve that is out of scope — see "Deliberately not doing" below. Do not re-raise polish items as if they were defects.

**Finishing scope, in order:** bug fixes + cleanup (env-based config, lifespan, requirements.txt, ruff) → pytest suite against a test MongoDB → Docker + docker-compose → GitHub Actions CI → README rewrite. Timebox is ~1.5 days; CI is the first thing cut if behind. Nothing beyond this scope.

## Plan

Full version with research hints: `~/.claude/plans/i-want-to-finish-zesty-hippo.md`.

### Step 0: Split Flutter client to its own repo — done

### Step 1: Bug fixes + cleanup — done
- Bugs 1, 2, 3, 5, 6 — fixed (`replace_file` 404 on empty slot; two separate log files; dead `get_file_path` deleted; `TextBody.text` has `max_length=512`; `remove_file` returns a `FileMeta`).
- Bug 4 — half done. `add_file` now raises `TakenSlotError` correctly, but `TakenSlotError`'s docstring is still `IllegalSlotError`'s, copy-pasted, and `add_file`'s docstring still claims a taken slot raises `IllegalSlotError`. **Knowingly left** under the quality bar.
- Cleanups 7–10 — done (env-based settings, `lifespan`, pinned `requirements.txt` + `ruff`, reference block deleted).
- Optional 11 (exception handlers) — **dropped.** Every route pre-checks the slot, so the domain exceptions are unreachable in practice.

### Step 1b: Docker-era bug found 2026-09-20 — fixed
`remove_file` crashed with `FileNotFoundError` when the file was already gone from disk — which is exactly what startup reconciliation calls it for. Reproduced in the running container: the API died on boot and stayed dead. It now guards with `os.path.exists` and logs a warning instead. Keep this path tolerant of a missing file; it is the self-healing feature the README advertises.

### Step 2: pytest suite — done
- `tests/conftest.py` (one `client` fixture: monkeypatched settings, test DB dropped around each test, files dir in `tmp_path`) and `tests/test_clip_api.py` (24 tests, text + files + pre-existing, in one file rather than the planned split). `pytest.ini` sets `pythonpath = src`.
- The loop gotcha is handled by `with TestClient(api)`, which runs lifespan (and so `connect_to_db`) on the right loop.
- Tests landed on day 1, so **CI stays in scope**.

### Step 3: Docker + compose — done
- `Dockerfile` (python:3.12-slim, `PYTHONPATH=/app/src`, uvicorn), `.dockerignore`, `docker-compose.yaml` — note `.yaml`, not `.yml`.
- Two services: `clip_api` (published on 8000) and `clip_db` (mongo:7.0, **port deliberately not published**). Named volumes `files-folder` → `/data/files` and `mongo-data` → `/data/db`. `clip_db` has a `mongosh` healthcheck; `clip_api` waits on it via `depends_on: condition: service_healthy`.
- Compose injects `FILES_PATH` and `CONNECTION_STRING` as real env vars, which beat `src/.env` — that file is in `.dockerignore` so it never reaches the image.
- **Verified 2026-09-20:** `docker compose up` works, API answers, and an upload survives `down && up`.
- Because `clip_db` publishes no port, `pytest` cannot use the compose Mongo; it needs a Mongo on the host at `localhost:27017`. Accepted as-is.

### Step 4: GitHub Actions CI — next
- `.github/workflows/ci.yml`: install `requirements-dev.txt` → `ruff check src tests` → `pytest`, Mongo as a service container.
- Use **Python 3.12** to match the Dockerfile. (The user's machine runs 3.14; the Dockerfile is the thing that ships.)
- **Done when:** green run on `main`, badge renders.

### Step 5: README + GitHub polish
- Remove Flutter content, link client repo, add Docker quickstart, tests section, CI badge, fix project structure.
- Repo description, topics, pin.

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
pip install -r requirements-dev.txt     # runtime deps + pytest/ruff/fastapi-cli
python -m fastapi dev src/clip_api.py   # dev server with reload, http://localhost:8000
pytest                                  # from the repo root, needs a local Mongo
ruff check src tests
```

Docker (from the repo root — this is the supported way to run the project):

```bash
docker compose up -d        # builds the image, starts api + mongo
docker compose config       # validate the compose file without starting anything
docker compose logs clip_api
docker compose down         # keeps the named volumes, so uploads survive
```

- `requirements.txt` is runtime only (what the Docker image installs); `requirements-dev.txt` pulls it in via `-r` and adds the tooling. CI installs the dev file.
- Requires MongoDB running on `localhost:27017` (see `settings.CONNECTION_STRING`).
- Config: every setting in `src/constants.py` has a default anchored to the repo, not the working directory. Override via real env vars or `src/.env` (gitignored); env vars win, which is how compose will inject them. `.env.example` is the committed reference.
- Interactive API docs: `http://localhost:8000/docs`.
- CI does not exist yet; it's next (see Step 4). Update this section when it lands.

## Deliberately not doing

Reviewed on 2026-09-20 and consciously dropped under the quality bar above. These are **not** open defects — don't re-report them:

- Container runs as `root`; no non-root `USER` in the Dockerfile.
- App logs go to files inside the container, so `docker compose logs` shows only uvicorn output, not `log.debug`/`log.info` calls.
- No `HEALTHCHECK` for `clip_api` (only `clip_db` has one).
- Stale docstrings on `TakenSlotError` and `add_file` (Bug 4 above).
- No exception handlers for the domain exceptions (Optional 11 above).
- `GET /files/{slot}` is annotated `-> PublicFileMeta` but returns a bare `Response` for 204, so `/docs` overstates it.
- The `replace_file` route calls the handler before checking whether the slot was occupied. Correct, but reads backwards and costs an extra query.
- No test for the reconciliation path (a DB record whose file vanished from disk) — the Step 1b bug was found by hand, not by the suite.
- Dockerfile `ENV` lines sit between `COPY` and `RUN pip install` rather than above them.

## Architecture

### Backend: routes vs. business logic

- `clip_api.py` — FastAPI route handlers only: validate slot/params, call into `clip_db_handler`, translate results into HTTP responses/status codes (204 empty, 400/404/409 errors). No DB or filesystem code belongs here.
- `clip_db_handler.py` — all business logic: async `pymongo` queries, file I/O on disk, Pydantic models (`FileMeta` includes `file_path` and is internal-only; `PublicFileMeta` omits it and is what the API returns). Has no knowledge of HTTP; raises domain exceptions (`IllegalSlotError`, `TakenSlotError`).
- `constants.py` — single source of truth for slot count (`ALLOWED_SLOTS`), the pre-existing-files sentinel (`PRE_EXISTING_FILES_SLOT = -1`), text history depth (`ALLOWED_TEXT_POSITIONS`), the Mongo connection string, and log file paths.

### File slot model

- Three slots (`0, 1, 2`), one file each. Files not assigned to a slot live at slot `-1` ("pre-existing"), surfaced via `/files/pre-existing`.
- Files are stored on disk renamed to their `file_uuid` (+ original extension); the original `file_name` lives only in MongoDB metadata.
- On startup, the server reconciles disk state with the DB (`setup_db` → `files_collection_setup_and_validation`): adds untracked files as slot `-1`, drops DB records with no file on disk, resolves duplicate/illegal slot assignments by moving files to `-1`. This self-healing exists because the `files/` folder can be edited manually on the host.
- Reconciliation drops stale records by calling `remove_file`, so **`remove_file` must tolerate a file that is already missing from disk**. It used to raise there and killed startup (Step 1b).
- `file_path` is stored in Mongo as an absolute path, so a DB and a files directory are only valid together. Changing `FILES_PATH` against an existing DB makes every record look stale and reconciliation deletes them.

### Text history model

- Up to 5 saves (`ALLOWED_TEXT_POSITIONS`), position `0` = most recent. Writes are full delete-and-reinsert of the collection with sequential positions (`add_save_to_textbox`, `fix_positions`), not in-place updates — this is how position integrity and the 5-item cap are maintained through undo.
- `POST /text` no-ops if the new text equals the last save.

### Logging

Both backend files configure their own logger to separate files (`constants.API_LOG_FILE_PATH`, `constants.DB_LOG_FILE_PATH`), overwritten each run. Convention: `log.debug` for expected/normal paths, `log.warning` for expected 4xx client errors, `log.error`/`log.exception` for real failures. Match this when adding log calls.

### Client

The Flutter client has been split out to its own repo (Step 0) and is out of scope here. It shares no types with the backend, so any API shape change must be mirrored there by hand.
