import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/widgets/widgets.dart';
import '../features/auth/domain/models/auth_state.dart';
import '../features/auth/presentation/auth_notifier.dart';
import '../features/auth/presentation/screens/login_screen.dart';
import '../features/auth/presentation/screens/register_screen.dart';
import '../features/gallery/presentation/screens/gallery_screen.dart';
import '../features/input_handwriting/domain/input_mode.dart';
import '../features/profile/presentation/screens/profile_screen.dart';
import '../features/project/presentation/screens/project_dashboard_screen.dart';
import '../features/project/presentation/screens/create_project_screen.dart';
import '../features/input_handwriting/presentation/screens/input_selection_screen.dart';
import '../features/shell/app_shell.dart';
import '../features/trajectory_preview/presentation/screens/trajectory_preview_screen.dart';
import '../features/checkout_payment/presentation/screens/checkout_screen.dart';
import '../features/request_tracking/presentation/screens/track_status_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

/// GoRouter configuration with authentication-aware route guards.
/// Unauthenticated users are automatically redirected to the login screen.
///
/// The router is created once; auth changes re-run [redirect] through
/// `refreshListenable` instead of rebuilding the router (which would reset
/// every tab's navigation stack).
final appRouterProvider = Provider<GoRouter>((ref) {
  final authListenable = ValueNotifier<AuthState>(ref.read(authNotifierProvider));
  ref.listen<AuthState>(authNotifierProvider, (_, next) => authListenable.value = next);
  ref.onDispose(authListenable.dispose);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/projects',
    debugLogDiagnostics: true,
    refreshListenable: authListenable,

    // ─── Route Guard ─────────────────────────────────────────────────
    redirect: (context, state) {
      final authState = authListenable.value;
      final isAuthenticated = authState is AuthAuthenticated;
      final isAuthRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      final isLoading = authState is AuthLoading || authState is AuthInitial;

      // While auth status is loading, don't redirect
      if (isLoading) return null;

      // Unauthenticated user trying to access protected route → login
      if (!isAuthenticated && !isAuthRoute) {
        return '/login';
      }

      // Authenticated user on auth route → dashboard
      if (isAuthenticated && isAuthRoute) {
        return '/projects';
      }

      return null;
    },

    // ─── Routes ──────────────────────────────────────────────────────
    routes: [
      // Auth Routes
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterScreen(),
      ),

      // Tabbed shell: Today · Inspirations · Orders · Profile.
      // Flow screens use the root navigator so they cover the bottom bar.
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(navigationShell: shell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/projects',
                name: 'projects',
                builder: (context, state) => const ProjectDashboardScreen(),
                routes: [
                  GoRoute(
                    path: 'create',
                    name: 'create-project',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) => CreateProjectScreen(
                      mode: InputMode.fromName(state.uri.queryParameters['mode']),
                    ),
                  ),
                  GoRoute(
                    path: ':projectId/input',
                    name: 'input-selection',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) {
                      final projectId = state.pathParameters['projectId']!;
                      return InputSelectionScreen(
                        projectId: projectId,
                        initialMode: InputMode.fromName(state.uri.queryParameters['mode']),
                      );
                    },
                  ),
                  GoRoute(
                    path: ':projectId/trajectory',
                    name: 'trajectory-preview',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) {
                      final projectId = state.pathParameters['projectId']!;
                      return TrajectoryPreviewScreen(projectId: projectId);
                    },
                  ),
                  GoRoute(
                    path: ':projectId/checkout',
                    name: 'checkout',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) {
                      final projectId = state.pathParameters['projectId']!;
                      return CheckoutScreen(projectId: projectId);
                    },
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/gallery',
                name: 'gallery',
                builder: (context, state) => const GalleryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/tracking',
                name: 'tracking',
                builder: (context, state) => const TrackStatusScreen(),
                routes: [
                  GoRoute(
                    path: ':requestId',
                    name: 'tracking-detail',
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (context, state) {
                      final requestId = state.pathParameters['requestId']!;
                      return TrackStatusScreen(requestId: requestId);
                    },
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                name: 'profile',
                builder: (context, state) => const ProfileScreen(),
              ),
            ],
          ),
        ],
      ),
    ],

    // ─── Error Page ──────────────────────────────────────────────────
    errorBuilder: (context, state) => Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const QuillPaperArt(size: 96),
              const SizedBox(height: 28),
              Text(
                'this page is blank.',
                style: Theme.of(context).textTheme.displaySmall,
              ),
              const SizedBox(height: 8),
              Text(
                state.matchedLocation,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 28),
              CustomButton(
                label: 'Back to today',
                isExpanded: false,
                onPressed: () => context.go('/projects'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
});
