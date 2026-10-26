import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef Prefs = SharedPreferences;

/// Loaded once in `main_desktop.dart` and injected with an override, so every
/// store can read its saved state synchronously on first build.
final prefsProvider = Provider<Prefs>((ref) => throw UnimplementedError('Override prefsProvider in main'));
