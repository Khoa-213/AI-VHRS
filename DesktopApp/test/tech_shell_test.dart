import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';
import 'package:ai_vhrs_mobile/features/auth/domain/models/user.dart';
import 'package:ai_vhrs_mobile/features/auth/presentation/auth_notifier.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/screens/settings_screen.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/tech_shell.dart';

class _FakeAuth implements AuthRepository {
  final changes = <(String, String)>[];

  @override
  Future<AuthSession> login({required String email, required String password}) async => (
        accessToken: 'a',
        refreshToken: 'r',
        user: User(id: '4', email: email, fullName: 'Technical Staff', role: UserRole.technicalStaff, createdAt: DateTime(2026)),
      );

  @override
  Future<void> changePassword({required String currentPassword, required String newPassword}) async {
    if (currentPassword != 'right-one') throw const BadRequestException('wrong', null, 'WRONG_PASSWORD');
    changes.add((currentPassword, newPassword));
  }

  @override
  Future<void> logout() async {}
  @override
  Future<void> requestPasswordReset(String email) async {}
  @override
  Future<User> getProfile() async => throw const UnauthorizedException();
  @override
  Future<User> updateProfile({String? fullName, String? phoneNumber}) async => throw UnimplementedError();
}

Future<_FakeAuth> _pump(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  FlutterSecureStorage.setMockInitialValues({});
  SharedPreferences.setMockInitialValues({'aivhrs-lang': 'en'});
  final prefs = await SharedPreferences.getInstance();
  final fake = _FakeAuth();
  final router = GoRouter(
    initialLocation: '/settings',
    routes: [
      ShellRoute(
        builder: (_, s, child) => TechShell(location: s.matchedLocation, child: child),
        routes: [
          GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
          GoRoute(path: '/tech', builder: (_, _) => const Text('dashboard page')),
          GoRoute(path: '/tech/jobs', builder: (_, _) => const Text('jobs page')),
          GoRoute(path: '/tech/qc', builder: (_, _) => const Text('qc page')),
        ],
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(prefs),
      authRepositoryProvider.overrideWithValue(fake),
      techJobsProvider.overrideWith((ref) => Stream.value(const [])),
      robotStatusProvider.overrideWith((ref) => Stream.value(const [])),
    ],
    child: MaterialApp.router(routerConfig: router),
  ));
  final c = ProviderScope.containerOf(tester.element(find.byType(TechShell)));
  await c.read(authNotifierProvider.notifier).login(email: 'tech@netviet.vn', password: 'x');
  await tester.pumpAndSettle();
  return fake;
}

void main() {
  testWidgets('a wide window gets the rail, with sign out on it', (tester) async {
    await _pump(tester, const Size(1440, 900));
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.text('AV'), findsOneWidget);
    await tester.tap(find.text('Jobs'));
    await tester.pumpAndSettle();
    expect(find.text('jobs page'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a phone gets bottom tabs and no rail, without overflow', (tester) async {
    await _pump(tester, const Size(390, 844));
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('AV'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('QC'));
    await tester.pumpAndSettle();
    expect(find.text('qc page'), findsOneWidget);
    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('tech@netviet.vn'), findsOneWidget);
    expect(find.text('Sign out'), findsOneWidget);
  });

  testWidgets('just under the breakpoint is the phone layout', (tester) async {
    await _pump(tester, const Size(699, 800));
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('at the breakpoint the rail fits a short window by scrolling', (tester) async {
    await _pump(tester, const Size(700, 400));
    expect(find.byType(NavigationBar), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('on a tall window the rail keeps settings and sign out at the bottom', (tester) async {
    await _pump(tester, const Size(1440, 900));
    expect(tester.getBottomLeft(find.text('Sign out').first).dy, greaterThan(800));
    expect(tester.getTopLeft(find.text('Dashboard')).dy, lessThan(200));
  });

  testWidgets('the language buttons switch the app', (tester) async {
    await _pump(tester, const Size(1440, 900));
    await tester.tap(find.text('Tiếng Việt'));
    await tester.pumpAndSettle();
    expect(find.text('Đổi mật khẩu'), findsOneWidget);
    await tester.tap(find.text('日本語'));
    await tester.pumpAndSettle();
    expect(find.text('パスワードの変更'), findsOneWidget);
  });

  testWidgets('change password checks the fields and the server answer', (tester) async {
    final fake = await _pump(tester, const Size(390, 844));
    await tester.tap(find.text('Change password'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save password'));
    await tester.pumpAndSettle();
    expect(find.text('Enter your current password.'), findsOneWidget);
    expect(find.text('Use 8 to 72 characters.'), findsOneWidget);

    final fields = find.byType(TextFormField);
    await tester.enterText(fields.at(0), 'wrong-one');
    await tester.enterText(fields.at(1), 'brand-new-pass');
    await tester.enterText(fields.at(2), 'different');
    await tester.tap(find.text('Save password'));
    await tester.pumpAndSettle();
    expect(find.text('The two passwords do not match.'), findsOneWidget);
    expect(fake.changes, isEmpty);

    await tester.enterText(fields.at(2), 'brand-new-pass');
    await tester.tap(find.text('Save password'));
    await tester.pumpAndSettle();
    expect(find.text('The current password is incorrect.'), findsOneWidget);

    await tester.enterText(fields.at(0), 'right-one');
    await tester.tap(find.text('Save password'));
    await tester.pumpAndSettle();
    expect(fake.changes, [('right-one', 'brand-new-pass')]);
    expect(find.text('Password changed. Other devices have been signed out.'), findsOneWidget);
  });
}
