import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/presentation/auth_notifier.dart';
import 'routing/app_router.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock to portrait orientation
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  runApp(const ProviderScope(child: AiVhrsApp()));
}

/// Root application widget for AI-VHRS Customer Portal.
class AiVhrsApp extends ConsumerStatefulWidget {
  const AiVhrsApp({super.key});

  @override
  ConsumerState<AiVhrsApp> createState() => _AiVhrsAppState();
}

class _AiVhrsAppState extends ConsumerState<AiVhrsApp> {
  @override
  void initState() {
    super.initState();
    // Check for existing auth session on startup
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authNotifierProvider.notifier).checkAuthStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'AI-VHRS',
      debugShowCheckedModeBanner: false,

      // Theme
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      // Light only for now: the ink-on-paper screens use light surface
      // tokens directly, so a system dark mode would mix palettes.
      themeMode: ThemeMode.light,

      // Router
      routerConfig: router,
    );
  }
}
