# AI-VHRS technician desk

Flutter desktop app (Windows, also runs on macOS while developing) for the workshop's technical
staff. It keeps the ink-on-paper theme (`lib/core/theme`) and follows the technician flow of the web
FE (`FE/src/pages/tech`). The customer app now lives only on the web.

```bash
flutter run -d windows           # or -d macos on a Mac
flutter build windows            # output: build/windows/x64/runner/Release/
flutter test
flutter test test/auth_live_test.dart --dart-define=LIVE_API=true   # real sign-in against the API
```

Use another backend with `--dart-define=API_BASE_URL=https://.../api/v1`.

## Sign in

Real API: `POST /auth/login` on `https://ai-vhrs.onrender.com/api/v1`. Only `TECHNICAL_STAFF`
accounts get in. Customers and office staff are refused and their session is revoked.

- Test account (seeded by the BE migrations): `tech@netviet.vn` / `ChangeMe@123`.
- Tokens are kept in secure storage. An expired access token is refreshed automatically. When the
  refresh token is rejected too, the app returns to the login screen.
- Render's free plan sleeps when idle, so the first sign-in after a pause can take up to a minute.

## Flow

Dashboard → Preview (pick an order → simulator, preflight, start robot) → QC (11 checks, 2 photos,
send or reschedule).

Orders, robots and QC use a local mock store (`lib/features/tech/data/tech_store.dart`, saved with
shared_preferences) because the backend has no technician endpoints yet. Replace the method bodies
with API calls when it does. The signed-in account is matched to a mock roster queue by email
(`rosterIdForEmail` in `domain/roster.dart`).

## Languages

English, Japanese and Vietnamese. Shared strings are generated from `FE/src/i18n` into
`lib/features/tech/i18n/gen/`. Desktop-only keys (`dk.*`) live in `tech_strings.dart`.

## Layout

```
lib/
├── main.dart                 # entry: theme, session restore, router
├── core/                     # theme, colors, Dio client + auth interceptor, secure storage, widgets
└── features/
    ├── auth/                 # /auth/login, /auth/refresh, /auth/logout, /me, password reset
    └── tech/
        ├── data/             # mock store, seed orders, QC photos, prefs
        ├── domain/           # order model + phases, roster, QC checklist
        ├── i18n/             # en / ja / vi
        ├── sim/              # robot simulator (path planning, IK arm, painter)
        └── presentation/     # router, shell + rail, login, dashboard, preview, QC
```
