# global_clipboard

> Sync text and files across your devices - fast and easy.

[![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Flutter](https://img.shields.io/badge/Flutter-3.x-02569B?logo=flutter&logoColor=white)](https://flutter.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-8.x-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## About

global_clipboard is a self-hosted clipboard sync tool. It keeps a shared text buffer and three file slots in sync across all your devices - paste on your laptop, pick it up on your tablet, no third-party account needed.

The server is designed to run on a Raspberry Pi on your local network. A cross-platform Flutter client (Windows, macOS, iOS, Android) connects to it over HTTP. Currently single-user; the architecture is intentionally simple to match that scope.

This project was built as a structured learning exercise in Python async web servers, REST API design, and cross-platform mobile development.

---

## Features

- **Self-healing startup** — server reconciles disk state with the database on boot, survives manual edits to the files directory
- **Text sync** — save and retrieve your clipboard text from any device
- **Undo history** — up to five text saves; step back through history with one tap
- **Three file slots** — assign files to named slots; replace or delete them from any device
- **Drag-and-drop uploads** — drop a file onto a slot card in the desktop client
- **Cross-platform Flutter client** — one codebase, runs on Windows, macOS, iOS, and Android


---

## Tech Stack

### Backend

| Layer | Choice | Why |
|---|---|---|
| Framework | FastAPI | async-native, automatic OpenAPI docs, Pydantic integration |
| Validation | Pydantic v2 | data models defined once, reused for DB reads and API responses |
| Database | MongoDB (async via `pymongo`) | was familiar with SQL, wanted to try something new |
| Language | Python 3.14 | learning target; type hints enforced project-wide |

### Frontend

| Layer | Choice | Why |
|---|---|---|
| Framework | Flutter (Dart) | single codebase, native performance on desktop and mobile |
| HTTP client | Dio | multipart file uploads, binary download responses, interceptors |
| File I/O | `file_picker`, `file_saver`, `cross_file` | cross-platform open/save dialogs with no platform branches in app code |
| Drag-and-drop | `desktop_drop` | works on Windows and macOS without native plugin boilerplate |

---

## Project Structure

```
global_clipboard/
├── src/
│   ├── clip_api.py             # FastAPI route handlers — thin, delegate to handler
│   ├── clip_db_handler.py      # All business logic: DB queries, file I/O, validation
│   └── constants.py            # Single source of truth for slot count, text limits, DB URI
├── app/
│   └── lib/
│       └── main.dart           # Complete Flutter client (~800 lines, single-file MVP)
├── files/                      # Uploaded files, stored with UUID filenames (git-ignored)
└── log.log                     # Server logs
```

Routes are kept thin by design — handlers validate input and delegate everything else to `clip_db_handler`. Business logic has no knowledge of HTTP.

---

## Getting Started

### Prerequisites

- Python 3.12+
- MongoDB running on `localhost:27017`
- Flutter SDK 3.x (for the client only)

### Installation

```bash
git clone https://github.com/peleg-laufer/global_clipboard.git
cd global_clipboard

pip install fastapi "pymongo[srv]" pydantic python-multipart
```

### Run the server

```bash
python -m fastapi dev src/clip_api.py
```

The server starts on `http://localhost:8000`. On first boot it creates the `files/` directory, verifies the MongoDB connection, and reconciles any existing files with the database.

Interactive API docs are available at `http://localhost:8000/docs`.

### Run the Flutter client

```bash
cd app
flutter pub get
flutter run
```

The client connects to `http://localhost:8000` by default.

---

## API Reference

### Text

| Method | Path | Description | Status codes |
|---|---|---|---|
| `GET` | `/text` | Fetch the most recent text save | 200, 204 |
| `POST` | `/text` | Push new text to history (max 512 chars) | 200 |
| `POST` | `/text/undo` | Revert to the previous save | 200, 204 |

### Files

| Method | Path | Description | Status codes |
|---|---|---|---|
| `GET` | `/files` | List all files assigned to slots | 200 |
| `GET` | `/files/{slot}` | Get metadata for slot 0, 1, or 2 | 200, 204 |
| `GET` | `/files/{slot}/download` | Download raw file bytes | 200, 404 |
| `POST` | `/files?slot={slot}` | Upload a file to an empty slot | 200, 409, 400 |
| `PUT` | `/files/{slot}/replace` | Replace the file in an occupied slot | 200, 404 |
| `DELETE` | `/files/{slot}` | Delete the file in a slot | 200, 404 |

File metadata response shape:

```json
{
  "file_name": "report.pdf",
  "file_type": "application/pdf",
  "file_size": 204800,
  "file_uuid": "3f2a1b...",
  "file_slot": 0
}
```

---

## Development Notes

The backend (`clip_api.py`, `clip_db_handler.py`, `constants.py`) was written by hand as the primary learning objective - working through async FastAPI patterns, MongoDB driver behavior, and REST API design decisions without code generation. The goal was to understand why things work, not just that they work.

The Flutter client was developed with [Claude Code](https://claude.ai/code) acting as a pair-programmer and tutor. Most of the Dart and Flutter-specific code in `main.dart` came from that collaboration, with explanations woven into the comments. This mirrors how I'd expect to use AI tooling on a team: writing and owning the core logic, using AI to accelerate in unfamiliar territory and to review decisions.

---

## Roadmap

- [ ] Deploy server to a Raspberry Pi on the local network
- [ ] Add a pytest suite (unit tests for service layer, integration tests against a real MongoDB instance)
- [ ] Restructure into `server/src/clip_server/` with `routes/`, `services/`, `db.py`, `models.py`, `config.py`
- [ ] Migrate Flutter client to Riverpod for state management
- [ ] Polish iPad and Android layouts
- [ ] Tighten CORS config for Pi deployment

---

## License

MIT - see [LICENSE](LICENSE) for details.
