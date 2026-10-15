# ai_vhrs_mobile

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Windows technician desk

A second entry point turns this project into the technician app for Windows. It keeps the mobile
theme (`lib/core/theme`) and follows the technician flow of the web FE (`FE/src/pages/tech`).

```bash
flutter run -d windows -t lib/main_desktop.dart     # or -d macos while developing on a Mac
flutter build windows -t lib/main_desktop.dart
flutter test test/tech_desktop_test.dart
```

- Sign in with a prototype technician account (`ha@`, `phuc@`, `anh@`, `thao@aivhrs.vn`, any password).
- Flow: Dashboard → Preview (pick order → simulator, preflight, start robot) → QC (11 checks, 2 photos, send or reschedule).
- Data is a local mock store (`lib/features/tech/data/tech_store.dart`, saved with shared_preferences).
  Swap the method bodies for API calls when the backend has order endpoints.
- Strings exist in English, Japanese and Vietnamese. Shared ones are generated from `FE/src/i18n`
  into `lib/features/tech/i18n/gen/`. Desktop-only keys (`dk.*`) live in `tech_strings.dart`.
