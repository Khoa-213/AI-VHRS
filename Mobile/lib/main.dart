import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'core/theme/app_theme.dart';
import 'features/tech/data/prefs.dart';
import 'features/tech/i18n/tech_strings.dart';
import 'features/tech/presentation/desktop_router.dart';
import 'features/tech/presentation/widgets/tech_ui.dart';

/// Entry point for the Windows technician desk.
///
///   flutter run -d windows -t lib/main_desktop.dart
///   flutter build windows -t lib/main_desktop.dart
///
/// Same theme as the customer app (`AppTheme`), technician flow from the FE
/// (`/tech`, `/tech/preview/:id`, `/tech/qc/:id`), data from a local mock store.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  await Future.wait([for (final l in Lang.values) initializeDateFormatting(l.locale)]);
  runApp(ProviderScope(overrides: [prefsProvider.overrideWithValue(prefs)], child: const TechDesktopApp()));
}

class TechDesktopApp extends ConsumerWidget {
  const TechDesktopApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return MaterialApp.router(
      title: t('dk.appTitle'),
      debugShowCheckedModeBanner: false,
      theme: _desktopTheme(AppTheme.lightTheme),
      // Light only, like the mobile app: the screens use light tokens directly.
      themeMode: ThemeMode.light,
      routerConfig: ref.watch(desktopRouterProvider),
    );
  }
}

/// Mobile theme with the desktop's tighter corners ([TechRadius]).
ThemeData _desktopTheme(ThemeData base) {
  final control = RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.control));
  OutlineInputBorder input(InputBorder? b) {
    final side = b is OutlineInputBorder ? b.borderSide : const BorderSide();
    return OutlineInputBorder(borderRadius: BorderRadius.circular(TechRadius.inner), borderSide: side);
  }

  final i = base.inputDecorationTheme;
  ButtonStyle? shaped(ButtonStyle? s) => s?.copyWith(shape: WidgetStatePropertyAll(control));
  return base.copyWith(
    elevatedButtonTheme: ElevatedButtonThemeData(style: shaped(base.elevatedButtonTheme.style)),
    filledButtonTheme: FilledButtonThemeData(style: shaped(base.filledButtonTheme.style)),
    outlinedButtonTheme: OutlinedButtonThemeData(style: shaped(base.outlinedButtonTheme.style)),
    textButtonTheme: TextButtonThemeData(style: shaped(base.textButtonTheme.style)),
    chipTheme: base.chipTheme.copyWith(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6))),
    inputDecorationTheme: i.copyWith(
      border: input(i.border),
      enabledBorder: input(i.enabledBorder),
      focusedBorder: input(i.focusedBorder),
      errorBorder: input(i.errorBorder),
      focusedErrorBorder: input(i.focusedErrorBorder),
    ),
    dialogTheme: DialogThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.card))),
    popupMenuTheme: PopupMenuThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.inner))),
    snackBarTheme: base.snackBarTheme.copyWith(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.inner)),
    ),
  );
}
