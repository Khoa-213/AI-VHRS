import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/widgets.dart';
import '../../auth/domain/models/auth_state.dart';
import '../../auth/presentation/auth_notifier.dart';
import '../i18n/tech_strings.dart';
import 'screens/jobs_screen.dart';
import 'screens/job_detail_screen.dart';
import 'screens/job_photos_screen.dart';
import 'screens/robot_control_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/tech_dashboard_screen.dart';
import 'screens/tech_login_screen.dart';
import 'widgets/tech_shell.dart';

/// Routes for the technician app, the same paths as the FE `/tech/*` pages.
final desktopRouterProvider = Provider<GoRouter>((ref) {
  final auth = ValueNotifier<AuthState>(ref.read(authNotifierProvider));
  ref.listen<AuthState>(authNotifierProvider, (_, next) => auth.value = next);
  ref.onDispose(auth.dispose);

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: auth,
    redirect: (context, state) {
      final a = auth.value;
      final at = state.matchedLocation;
      // Restoring the saved session: wait on the splash. A sign-in in progress stays on /login.
      if (a is AuthInitial) return at == '/splash' ? null : '/splash';
      if (a is AuthLoading) return null;
      if (a is AuthAuthenticated) return at == '/login' || at == '/splash' ? '/tech' : null;
      return at == '/login' ? null : '/login';
    },
    routes: [
      GoRoute(path: '/splash', pageBuilder: (_, _) => const NoTransitionPage(child: _Splash())),
      GoRoute(path: '/login', pageBuilder: (_, _) => const NoTransitionPage(child: TechLoginScreen())),
      ShellRoute(
        pageBuilder: (context, state, child) =>
            NoTransitionPage(child: TechShell(location: state.uri.toString(), child: child)),
        routes: [
          GoRoute(path: '/tech', pageBuilder: (_, _) => const NoTransitionPage(child: TechDashboardScreen())),
          GoRoute(
            path: '/tech/jobs',
            pageBuilder: (_, s) => NoTransitionPage(child: JobsScreen(filter: JobFilter.parse(s.uri.queryParameters['filter']))),
          ),
          GoRoute(
            path: '/tech/jobs/:id',
            pageBuilder: (_, s) {
              // A bad id reaches the backend's check as 0 and reads as "not found".
              final id = int.tryParse(s.pathParameters['id']!) ?? 0;
              final filter = s.uri.queryParameters['filter'];
              return NoTransitionPage(
                key: ValueKey('job-$id'),
                child: JobDetailScreen(key: ValueKey(id), jobId: id, backTo: filter == null ? '/tech/jobs' : '/tech/jobs?filter=$filter'),
              );
            },
          ),
          GoRoute(
            path: '/tech/jobs/:id/control',
            pageBuilder: (_, s) {
              final id = int.tryParse(s.pathParameters['id']!) ?? 0;
              return NoTransitionPage(key: ValueKey('control-$id'), child: RobotControlScreen(key: ValueKey(id), jobId: id));
            },
          ),
          GoRoute(
            path: '/tech/qc',
            pageBuilder: (_, _) => const NoTransitionPage(child: JobsScreen(filter: JobFilter.qc)),
          ),
          GoRoute(
            path: '/tech/qc/:id',
            pageBuilder: (_, s) {
              final id = int.tryParse(s.pathParameters['id']!) ?? 0;
              return NoTransitionPage(key: ValueKey('photos-$id'), child: JobPhotosScreen(key: ValueKey(id), jobId: id));
            },
          ),
          GoRoute(path: '/settings', pageBuilder: (_, _) => const NoTransitionPage(child: SettingsScreen())),
        ],
      ),
    ],
    errorBuilder: (context, state) => Consumer(
      builder: (context, ref, _) {
        final t = ref.watch(tProvider);
        return Scaffold(
          body: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const QuillPaperArt(size: 96),
                const SizedBox(height: 28),
                Text(t('dk.blank'), style: Theme.of(context).textTheme.displaySmall),
                const SizedBox(height: 8),
                Text(state.matchedLocation, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 28),
                CustomButton(label: t('rail.dashboard'), isExpanded: false, onPressed: () => context.go('/tech')),
              ],
            ),
          ),
        );
      },
    ),
  );
});

/// Shown while the saved session is checked against `GET /me`.
class _Splash extends ConsumerWidget {
  const _Splash();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const QuillPaperArt(size: 88),
            const SizedBox(height: 24),
            const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(height: 16),
            Text(t('dk.restoring'), style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}
