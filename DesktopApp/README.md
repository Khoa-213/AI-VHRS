# AI-VHRS technician desk

Flutter app (Windows and macOS desktop, Android and iOS phones) for the workshop's technical
staff. **Note (2026-11-26):** per `BE/docs/FE_TECH_WORKSPACE_HANDOFF.md` the technician's only workspace is now the
workstation screen served by the Robot Agent (`robot_agent/vhrs_agent/static/`), not this app; whether this app stays is the owner's call. It keeps the ink-on-paper theme (`lib/core/theme`). The customer app lives only on the web.

```bash
flutter run -d windows           # or -d macos on a Mac
flutter build windows            # output: build/windows/x64/runner/Release/
flutter test
flutter test test/auth_live_test.dart --dart-define=LIVE_API=true   # real sign-in against the API
flutter test test/tech_live_test.dart --dart-define=LIVE_API=true   # real job and robot reads
```

Use another backend with `--dart-define=API_BASE_URL=https://.../api/v1`.

## Robot Agent inside the app (2026-11-26)

On the workstation wired to the robot, the agent runs inside the app and **Overview holds only the agent** (2026-11-26: the
old counts, queue, job groups and My robots strip are gone; jobs stay in the Jobs and QC tabs; there is no separate Robot Agent
tab and `/tech/agent` redirects to Overview). The workstation screen fills the page below the agent's state card:

- **Starts by itself on sign-in**: once a technician signs in, the agent starts as that account (no click needed). After a
  restored session (the password is not kept on disk) the app asks for the password once. Signing out, or the session expiring,
  stops the agent the safe way. **Start the agent** is still there to start it again after a Stop or a failure.
- **Start the agent**: the app finds `robot_agent` (walking up from the app, or `--dart-define=AGENT_DIR=...`), starts
  `robot_agent\.simenv\python.exe -m vhrs_agent.cli serve --screen --stop-on-stdin-eof --parent-pid <app pid> --host 127.0.0.1 --port 8765` and gives it
  the signed-in technician's email and password in its environment only (the password typed at sign-in, kept in memory; after a
  restored session the app asks once). No terminal, no stored password.
- The agent's **workstation screen** (`http://127.0.0.1:8765/`, the 12 job steps and the "Bật REAL" button) opens on Overview,
  **already signed in** as the app's technician: the app gives the agent a random one-time code (`VHRS_SCREEN_CODE`, environment
  only) and opens the screen with `#code=...`; the screen trades it at `POST /api/screen-login` for the same session as a normal
  login. Its own Sign out button is hidden there (signing out of the app stops the agent).
- **Stop the agent** sends a `STOP` line on the agent's stdin; closing or killing the app ends the process the agent watches
  (`--parent-pid`). Either way a move in progress finishes its stroke, lifts the pen and stops, the robot session is given back
  to the backend, then the agent exits (killed only if still there after 40 s). On Windows a pipe end can outlive the app, so the
  process id is the reliable signal.
- An `IDENTIFY` refused by a robot that did answer (wrong tool slot, work object, model...) reads "Robot answered, but its setup
  does not match agent.json" (`ROBOT_CONFIG_MISMATCH`), not as a lost connection.
- **Check the robot connection** runs four read-only steps: agent running and linked, TCP to the controller (`fairino.ip`:20003),
  the backend sees the robot ONLINE, and `IDENTIFY` with `mode: REAL` through the backend. Nothing moves.
- Only one agent may hold a robot: stop an agent started from a terminal first, or the backend answers `ROBOT_IN_USE`.

## Sign in

Real API: `POST /auth/login` on `https://ai-vhrs.onrender.com/api/v1`. Only `TECHNICAL_STAFF`
accounts get in. Customers and office staff are refused and their session is revoked.

- Test account (seeded by the BE migrations): `tech@netviet.vn` / `ChangeMe@123`.
- Tokens are kept in secure storage. An expired access token is refreshed automatically. When the
  refresh token is rejected too, the app returns to the login screen.
- Render's free plan sleeps when idle, so the first sign-in after a pause can take up to a minute.

## Flow

Dashboard ("My robots": the robots the Manager gave me, `GET /technician/robots`, "Connected n / total · Working n"; a card
filters the jobs by robot) → Jobs (list and open job: the twelve steps with ✓ and the reason a step waits, package with SHA-256
check, signed package and material drift, choose one of my robots for a SCHEDULED job without one (`PUT .../robot`), prepare,
calibration from the workstation's `calibration.json` or by hand (`POST .../calibration`), the `real-enable` command to copy,
events, incidents, writing finished) → Robot control (3D view, commands, live data) → QC photos (upload, pass or
fail, Service G quality check against the sketch, submit). The header has the notifications bell (`/me/notifications`:
job assigned or cancelled) and the robot alert bell.

An E-Stop alert covers the whole app until it is acknowledged, and again when it happens again after the
acknowledgement (`last_raised_at` newer than `acknowledged_at`). A PAUSED job calibrated again needs a new passed
simulation before Write or Resume (backend `SIMULATION_STALE`); Robot control reads that from the event log and opens
"Record simulation result" on the PAUSED job.

A job may have no robot yet (`robot_id` null, migration 0032): it reads "No robot chosen", Prepare waits for the choice
and Robot control asks for it first.

Everything runs on the real API (`lib/features/tech/data/`), the same calls as the web FE. Commands go
to the backend, and the Robot Agent on the workstation pulls and runs them on the real arm.

## Languages

English, Japanese and Vietnamese. Shared strings are generated from `FE/src/i18n` into
`lib/features/tech/i18n/gen/` with `dart run tool/gen_i18n.dart`. Desktop-only keys (`dk.*`) live in `tech_strings.dart`.

## Layout

```
lib/
├── main.dart                 # entry: theme, session restore, router
├── core/                     # theme, colors, Dio client + auth interceptor, secure storage, widgets
└── features/
    ├── auth/                 # /auth/login, /auth/refresh, /auth/logout, /me, password reset
    └── tech/
        ├── data/             # API clients, polling providers, prefs
        ├── domain/           # jobs, photos, robot commands, status and alerts
        ├── i18n/             # en / ja / vi
        └── presentation/     # router, shell, login, dashboard, jobs, robot control, QC, settings
```
