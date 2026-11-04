import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/features/auth/data/auth_repository.dart';
import 'package:ai_vhrs_mobile/features/auth/domain/models/user.dart';
import 'package:ai_vhrs_mobile/features/auth/presentation/auth_notifier.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/main.dart';

/// Stands in for the backend in this test only; the app itself has no such thing.
class _StubAuth implements AuthRepository {
  @override
  Future<AuthSession> login({required String email, required String password}) async {
    if (password != 'ChangeMe@123') throw const UnauthorizedException('bad', 'INVALID_CREDENTIALS');
    return (
      accessToken: 'a',
      refreshToken: 'r',
      user: User(id: '4', email: email, fullName: 'Technical Staff', role: UserRole.technicalStaff, createdAt: DateTime(2026)),
    );
  }

  @override
  Future<User> getProfile() async => throw const UnauthorizedException();
  @override
  Future<void> logout() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  test('every text key written in the code exists', () {
    final d = techDictionaries[Lang.en]!;
    final key = RegExp(r"""\bt\('((?:dk|td|rb|rail|po|js|wk|login|lang|ot|co|common)\.[\w.]+)'""");
    final missing = <String>{};
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart') && !f.path.contains('/gen/'))) {
      for (final m in key.allMatches(f.readAsStringSync())) {
        if (!d.containsKey(m[1])) missing.add('${m[1]} (${f.path})');
      }
    }
    expect(missing, isEmpty);
  });

  test('no mock data or prototype shortcuts are left in the app', () {
    final words = RegExp(r'tech_store|seed_orders|prototypeProvider|mock store|sample photo', caseSensitive: false);
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
      expect(words.hasMatch(f.readAsStringSync()), isFalse, reason: f.path);
    }
  });

  testWidgets('sign in: a wrong password stays on the form, then the dashboard opens', (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    FlutterSecureStorage.setMockInitialValues({});
    SharedPreferences.setMockInitialValues({'aivhrs-lang': 'en'});
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(ProviderScope(
      overrides: [
        prefsProvider.overrideWithValue(prefs),
        authRepositoryProvider.overrideWithValue(_StubAuth()),
        techJobsProvider.overrideWith((ref) => Stream.value(const [])),
        robotStatusProvider.overrideWith((ref) => Stream.value(const [])),
      ],
      child: const TechDesktopApp(),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Technician desk'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(0), 'tech@netviet.vn');
    await tester.enterText(find.byType(TextFormField).at(1), 'wrong-pass1');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Email or password is incorrect.'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(1), 'ChangeMe@123');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('My jobs'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
