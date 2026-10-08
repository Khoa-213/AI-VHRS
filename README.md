# Folder Structure
## FE Folder Structure
src/
├── assets/                          # Static assets (images, svg)
├── components/
│   └── ui/
│       └── Reveal.tsx               # ♻️ Shared animation component
├── constants/
│   └── index.ts                     # ORDER_HREF, svgProps
├── hooks/
│   ├── useReveal.ts                 # ♻️ IntersectionObserver hook
│   └── useScrollProgress.ts         # ♻️ Scroll progress hook
├── pages/
│   └── landing/
│       ├── components/
│       │   ├── Header.tsx           # Sticky header + nav
│       │   ├── Hero.tsx             # Hero section
│       │   ├── Showcase.tsx         # Robot parallax showcase
│       │   ├── Modes.tsx            # 3 input modes cards
│       │   └── Cta.tsx              # Bottom CTA
│       ├── Landing.tsx              # ✨ Clean composition (18 lines)
│       └── landing.css              # Landing styles
├── types/
│   └── index.ts                     # Shared TS types
├── utils/
│   └── math.ts                      # clamp01, seg, ease
├── App.tsx
├── main.tsx
└── index.css

## Mobile Folder Structure

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