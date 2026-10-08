# AI-VHRS Mobile — Project Architecture Summary

## ✅ Build Status: **0 errors** | 64 info-level deprecation hints | All dependencies resolved

---

## 📂 Complete File Structure (44 Dart files)

```
lib/
├── main.dart                          # App entry point, ProviderScope, auth check
├── core/
│   ├── constants/
│   │   ├── app_colors.dart            # Brand palette, semantic, dark mode, status colors
│   │   ├── api_constants.dart         # All API endpoints, timeouts, env-based base URL
│   │   ├── app_constants.dart         # Paper sizes, pen types, canvas config, status flow
│   │   └── constants.dart             # Barrel export
│   ├── network/
│   │   ├── network_exceptions.dart    # Sealed class hierarchy (12 exception types)
│   │   ├── error_handler.dart         # DioException → NetworkException mapper
│   │   ├── auth_interceptor.dart      # JWT attach + auto 401 refresh (QueuedInterceptor)
│   │   ├── dio_client.dart            # Centralized HTTP client + file upload
│   │   └── network.dart              # Barrel export
│   ├── storage/
│   │   ├── secure_storage_service.dart # JWT token manager (Keychain/EncryptedSharedPrefs)
│   │   └── storage.dart              # Barrel export
│   ├── theme/
│   │   ├── app_theme.dart            # Light + Dark themes, Material 3, Inter typography
│   │   └── theme.dart                # Barrel export
│   ├── utils/
│   │   ├── validators.dart           # Email, password, VN phone, required, compose
│   │   ├── formatters.dart           # Date, VND/USD currency, timeAgo, text utilities
│   │   └── utils.dart                # Barrel export
│   └── widgets/
│       ├── custom_button.dart        # 4 styles (primary/secondary/outline/text) + loading
│       ├── custom_text_field.dart     # Label, validation, password toggle, prefix/suffix
│       ├── base_screen.dart          # SafeArea wrapper + AppBar + status bar config
│       ├── loading_view.dart         # Overlay + inline modes with optional message
│       ├── empty_state_view.dart     # Icon + title + description + action CTA
│       ├── error_view.dart           # Error display with retry button
│       └── widgets.dart              # Barrel export
├── features/
│   ├── auth/
│   │   ├── domain/models/
│   │   │   ├── user.dart             # User model with JSON/copyWith/Equatable
│   │   │   └── auth_state.dart       # Sealed: Initial|Loading|Authenticated|Unauth|Error
│   │   ├── data/
│   │   │   └── auth_repository.dart  # Login/Register/Profile CRUD (Dart 3 records)
│   │   └── presentation/
│   │       ├── auth_notifier.dart     # StateNotifier: login, register, logout, session check
│   │       └── screens/
│   │           ├── login_screen.dart  # Branded login form with validation
│   │           └── register_screen.dart # Full registration with password strength
│   ├── project/
│   │   ├── domain/models/
│   │   │   └── project.dart          # Project model with paper/pen/status
│   │   ├── data/
│   │   │   └── project_repository.dart # CRUD + pagination
│   │   └── presentation/
│   │       ├── project_notifier.dart  # List state with pagination, create, delete
│   │       └── screens/
│   │           ├── project_dashboard_screen.dart # Grid/List toggle, pull-to-refresh
│   │           └── create_project_screen.dart    # Paper size chips + pen type radio list
│   ├── input_handwriting/
│   │   └── presentation/
│   │       ├── screens/
│   │       │   ├── input_selection_screen.dart # Tabbed UI (3 methods)
│   │       │   ├── image_upload_tab.dart       # Camera/gallery + rotate + contrast slider
│   │       │   ├── text_font_tab.dart          # Text input + font selector + live preview
│   │       │   └── canvas_draw_tab.dart        # Interactive drawing with pen controls
│   │       └── widgets/
│   │           └── handwriting_canvas_painter.dart # CustomPainter with bezier strokes
│   ├── trajectory_preview/
│   │   └── presentation/screens/
│   │       └── trajectory_preview_screen.dart   # Animated path replay + price estimation
│   ├── checkout_payment/
│   │   └── presentation/screens/
│   │       └── checkout_screen.dart             # Order summary + VNPay/MoMo WebView
│   └── request_tracking/
│       └── presentation/screens/
│           └── track_status_screen.dart         # Vertical timeline + result viewer
└── routing/
    └── app_router.dart                          # GoRouter + auth guards + 404 page
```

---

## 🏗 Architecture Decisions

| Layer | Technology | Pattern |
|---|---|---|
| **State** | `flutter_riverpod` 2.x | `StateNotifier` + `StateNotifierProvider` |
| **Routing** | `go_router` | Auth-aware `redirect` guard |
| **Network** | `dio` | `QueuedInterceptor` for JWT + auto-refresh |
| **Storage** | `flutter_secure_storage` | Keychain (iOS) / EncryptedSharedPrefs (Android) |
| **Errors** | Sealed classes | Exhaustive pattern matching |
| **Models** | `equatable` | Value equality + JSON serialization |

---

## 🚀 Launch Commands

```bash
# 1. Install dependencies (already done)
flutter pub get

# 2. Run on connected device/emulator
flutter run

# 3. Run with custom API base URL
flutter run --dart-define=API_BASE_URL=https://your-api.com/v1

# 4. Run analysis
flutter analyze

# 5. Run tests
flutter test
```

---

## 🔐 Auth Flow

```mermaid
graph TD
    A[App Starts] --> B{Stored Token?}
    B -->|No| C[/login]
    B -->|Yes| D[GET /auth/profile]
    D -->|200 OK| E[AuthAuthenticated → /projects]
    D -->|401| F[Refresh Token]
    F -->|Success| E
    F -->|Fail| G[Clear Tokens → /login]
    C --> H[POST /auth/login]
    H -->|Success| I[Save Tokens → /projects]
    H -->|Error| J[Show Error Message]
```

---

## 📱 Screen Flow

```
Login/Register → Project Dashboard → Create Project
                                         ↓
                              Input Selection (3 tabs)
                                         ↓
                              Trajectory Preview + Price
                                         ↓
                              Checkout (VNPay/MoMo WebView)
                                         ↓
                              Track Status (Timeline)
```

> [!TIP]
> The `withOpacity` deprecation warnings (64 info items) are cosmetic and relate to Flutter's migration to `Color.withValues()`. They don't affect functionality.
