# eQueue Desktop — Python rebuild

A queue management system for clinics, rebuilt as a Python desktop app
(PyQt6 client + FastAPI server) so multiple machines on the same LAN can
share one live queue.

## Architecture

- **server/** — FastAPI app. Run it on one always-on machine (or a small
  server/NAS). Handles patients, queue, users, departments, and pushes
  live updates to every connected client over WebSocket.
- **client/** — PyQt6 desktop app. Run it on every reception/staff/admin
  computer. Talks to the server over HTTP + WebSocket.
- **shared/** — constants (roles, statuses, colors) used by both sides.

## Setup

### 1. Server (run once, on the machine that will host the shared DB)

```bash
cd server
pip install -r requirements.txt

# Default: local SQLite file (fine for testing on one machine).
# For real multi-machine use, set EQUEUE_DATABASE_URL to Postgres/MySQL, e.g.:
#   export EQUEUE_DATABASE_URL="postgresql+psycopg2://equeue:password@0.0.0.0:5432/equeue"

uvicorn main:app --host 0.0.0.0 --port 8000
```

The server seeds a default admin account (`admin` / `admin123`) and the
four original departments (Laboratory, Radiology, TB DOTS Unit, OPD) on
first run.

### 2. Client (run on every machine that needs the queue app)

```bash
cd client
pip install -r requirements.txt

# Point at the server's LAN IP if not running on the same machine:
#   export EQUEUE_SERVER_URL="http://192.168.1.10:8000"

uvicorn main:app --host 127.0.0.1 --port 8000
python main.py
```

## What's built vs. what's next

Done:
- Database schema (patients, departments, users, queue entries, SMS
  templates/logs, audit log)
- FastAPI CRUD for patients, queue, users, departments
- WebSocket broadcast on queue create/update
- Redesigned login screen and Reception dashboard (registration + live
  queue cards)

Next steps to reach feature parity with the original:
- Staff dashboard (start/complete consultation, view patient details)
- Admin dashboard (user management, SMS templates, reports, audit log
  viewer)
- Wire the WebSocket client-side so dashboards update live instead of
  polling
- SMS sending (reuse IPROG, or swap providers) via a `sms.py` router
- Packaging: `pyinstaller` to produce a distributable `.exe`/binary for
  each machine
