# AI-VHRS Technician Desk — Project Architecture Summary

Flutter desktop app (Windows; macOS for development) for the workshop's technical staff.
The customer app was removed from this project; customers use the web.

```bash
flutter run -d macos        # or -d windows
```

---

## 📂 File Structure

```
lib/
├── main.dart                          # Entry: prefs, theme, session restore, router
├── core/
│   ├── constants/
│   │   ├── app_colors.dart            # Ink-on-paper palette
│   │   └── api_constants.dart         # Base URL (Render), timeouts, auth endpoints
│   ├── network/
│   │   ├── network_exceptions.dart    # Sealed exceptions, carry the backend error code
│   │   ├── error_handler.dart         # DioException → NetworkException ({"error": {code, message, details}})
│   │   ├── auth_interceptor.dart      # Bearer token + auto refresh on 401, signs out when refresh fails
│   │   └── dio_client.dart            # Shared HTTP client
│   ├── storage/secure_storage_service.dart  # Access/refresh tokens
│   ├── theme/app_theme.dart           # Material 3 theme (desktop tightens radii in main.dart)
│   ├── utils/                         # Validators, formatters
│   └── widgets/                       # CustomButton, CustomTextField, Pressable, line art
└── features/
    ├── auth/                          # Real API: login, refresh, logout, /me, password reset
    └── tech/
        ├── data/                      # Mock store for orders/robots/QC, seed orders, QC photos
        ├── domain/                    # Order model + phases, roster, QC checklist
        ├── i18n/                      # en / ja / vi (shared keys generated from FE)
        ├── sim/                       # Robot simulator: path plan, 2-link IK, painter
        └── presentation/              # Router, rail shell, login, dashboard, preview, QC
```

---

## 🏗 Architecture Decisions

| Layer | Technology | Pattern |
|---|---|---|
| **State** | `flutter_riverpod` 2.x | `StateNotifier` + `StateNotifierProvider` |
| **Routing** | `go_router` | Auth-aware `redirect` (splash → login → /tech) |
| **Network** | `dio` | `QueuedInterceptor` for JWT + auto-refresh |
| **Storage** | `flutter_secure_storage`, `shared_preferences` | Tokens / mock orders and settings |
| **Errors** | Sealed classes + backend error codes | Codes mapped to `dk.err.*` translations |

---

## 🔐 Auth Flow

```mermaid
graph TD
    A[App starts] --> B{Stored token?}
    B -->|No| C[/login]
    B -->|Yes| D[GET /me]
    D -->|200, TECHNICAL_STAFF| E[/tech dashboard]
    D -->|401| F[POST /auth/refresh]
    F -->|Success| E
    F -->|Fail| G[Clear tokens → /login]
    C --> H[POST /auth/login]
    H -->|TECHNICAL_STAFF| I[Save tokens → /tech]
    H -->|Other role| J[Revoke session, show error]
    H -->|Error| K[Show translated error]
```

Test account: `tech@netviet.vn` / `ChangeMe@123` (seeded by the BE migrations).

---

## 📱 Screen Flow

```
Login → Dashboard (orders by phase, robots, queue)
          ├─ Preview → pick order → simulator + preflight → start robot → live run
          └─ QC → 11-item checklist → 2 required photos → send to customer / reschedule
```

Orders, robots and QC run on the local mock store until the backend has technician endpoints.
