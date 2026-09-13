# global_clipboard

> Sync text and files across your devices - fast and easy.

[![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-8.x-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## About

global_clipboard is a self-hosted clipboard sync backend. It keeps a shared text buffer (with undo history) and three file slots in sync across all your devices: paste on your laptop, pick it up on your phone, no third-party account needed.

It is an async REST API built with **FastAPI** and **MongoDB**, meant to run on a machine on your local network. Any HTTP client can use it. A cross-platform Flutter client lives in a separate repository.

This project was built as a structured learning exercise in Python async web servers, REST API design, and MongoDB.

---

## Features

- **Text sync**: save and retrieve clipboard text from any device
- **Undo history**: the last five text saves are kept; step back through them one at a time
- **Three file slots**: upload a file to a slot, then download, replace, or delete it from any device
- **Self-healing startup**: on boot the server reconciles the files directory with the database, so manual edits to the folder don't corrupt state
- **Typed API**: Pydantic models validate every request and response, and OpenAPI docs are generated automatically

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | FastAPI | async-native, automatic OpenAPI docs, Pydantic integration |
| Validation | Pydantic v2 | data models defined once, reused for DB reads and API responses |
| Database | MongoDB (async via `pymongo`) | was familiar with SQL, wanted to try a document database |
| Language | Python 3.14 | learning target; type hints used throughout |

---

## Project Structure

```
global_clipboard/
├── src/
│   ├── clip_api.py             # FastAPI route handlers - thin, delegate to the handler
│   ├── clip_db_handler.py      # Business logic: DB queries, file I/O, Pydantic models
│   └── constants.py            # Slot count, text history depth, DB URI, log paths
└── files/                      # Uploaded files, stored under UUID filenames (git-ignored)
```

Routes are kept thin by design. Handlers validate input and delegate everything else to `clip_db_handler`, which has no knowledge of HTTP and raises domain exceptions instead.

---

## Getting Started

### Prerequisites

- Python 3.12+
- MongoDB running on `localhost:27017`

### Installation

```bash
git clone https://github.com/peleg-laufer/global_clipboard.git
cd global_clipboard

pip install fastapi "pymongo[srv]" pydantic python-multipart
```

### Run the server

```bash
cd src
python -m fastapi dev clip_api.py
```

The server starts on `http://localhost:8000`. On first boot it creates the `files/` directory, verifies the MongoDB connection, and reconciles any existing files with the database.

Interactive API docs are available at `http://localhost:8000/docs`.

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
| `GET` | `/files/pre-existing` | List files found on disk but not assigned to a slot | 200 |
| `GET` | `/files/{slot}` | Get metadata for slot 0, 1, or 2 | 200, 204, 400 |
| `GET` | `/files/{slot}/download` | Download raw file bytes | 200, 400, 404 |
| `POST` | `/files?slot={slot}` | Upload a file to an empty slot | 200, 400, 409 |
| `PUT` | `/files/{slot}/replace` | Replace the file in an occupied slot | 200, 400, 404 |
| `DELETE` | `/files/{slot}` | Delete the file in a slot | 200, 400, 404 |

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

The backend (`clip_api.py`, `clip_db_handler.py`, `constants.py`) was written by hand as the primary learning objective: working through async FastAPI patterns, MongoDB driver behavior, and REST API design decisions without code generation. The goal was to understand why things work, not just that they work.

The Flutter client (separate repository) was developed with [Claude Code](https://claude.ai/code) as a pair-programmer, so I could focus my own effort on the backend.

---

## Roadmap

- [ ] Fix known bugs and move configuration to environment variables
- [ ] pytest suite running against a dedicated test database
- [ ] Docker + docker-compose for a one-command setup
- [ ] GitHub Actions CI (lint + tests)

---

## License

MIT - see [LICENSE](LICENSE) for details.
