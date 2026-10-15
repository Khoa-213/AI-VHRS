import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/seed_orders.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_store.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/roster.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/tech_models.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/desktop_router.dart';
import 'package:ai_vhrs_mobile/main_desktop.dart';

void main() {
  setUpAll(() async {
    rosterDayOverride = '2026-10-15';
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  group('i18n', () {
    test('en, ja and vi define the same keys', () {
      final d = techDictionaries;
      final en = d[Lang.en]!.keys.toSet();
      for (final l in [Lang.ja, Lang.vi]) {
        final keys = d[l]!.keys.toSet();
        expect(en.difference(keys), isEmpty, reason: '${l.name} is missing keys');
        expect(keys.difference(en), isEmpty, reason: '${l.name} has extra keys');
      }
    });

    test('placeholders and catalog names translate', () {
      expect(const T(Lang.en)('qc.title', {'id': 'VH-1'}), 'Photo and QC for VH-1');
      expect(const T(Lang.vi)('rp.startReal'), 'Khởi động robot thật');
      expect(const T(Lang.ja).tn('Greeting card × 10'), 'グリーティングカード × 10');
    });
  });

  group('phases', () {
    final base = seedTechOrders().firstWhere((o) => o.id == 'VH-4821');
    final now = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;

    test('queued without a run is ready, accepted is waiting', () {
      expect(phaseOf(base, now), Phase.ready);
      expect(phaseOf(base.copyWith(status: OrderStatus.Accepted), now), Phase.wait);
      expect(phaseOf(base.copyWith(status: OrderStatus.Written), now), Phase.done);
    });

    test('a run is live until its end time, then needs QC', () {
      final o = base.copyWith(run: RobotRun(robotId: 'FR3-01', startedAt: now, seconds: 45));
      expect(phaseOf(o, now + 10000), Phase.live);
      expect(phaseOf(o, now + 45000), Phase.qc);
    });
  });

  group('store', () {
    late ProviderContainer c;
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      c = ProviderContainer(overrides: [prefsProvider.overrideWithValue(await SharedPreferences.getInstance())]);
    });
    tearDown(() => c.dispose());

    test('start, finish, pass QC', () {
      final store = c.read(techOrdersProvider.notifier);
      store.startRobotRun('VH-4821', 'FR3-01');
      expect(store.byId('VH-4821')!.run, isNotNull);
      store.finishRobotRun('VH-4821');
      expect(runDone(store.byId('VH-4821')!, DateTime.now().millisecondsSinceEpoch), isTrue);
      store.submitQc('VH-4821', QcReport(checked: const [], total: 11, photos: const [], note: '', by: 'Hà', at: DateTime.now()));
      final o = store.byId('VH-4821')!;
      expect(o.status, OrderStatus.Written);
      expect(o.run, isNull);
    });

    test('failing QC goes back to the queue with reasons, and survives a reload', () async {
      final store = c.read(techOrdersProvider.notifier);
      store.startRobotRun('VH-4821', 'FR3-01');
      store.failQc('VH-4821', ['Ink smudge'], 'smudged');
      final reloaded = ProviderContainer(overrides: [prefsProvider.overrideWithValue(await SharedPreferences.getInstance())]);
      final o = reloaded.read(techOrdersProvider.notifier).byId('VH-4821')!;
      expect(o.status, OrderStatus.Queued);
      expect(o.run, isNull);
      expect(o.qcFail!.reasons, ['Ink smudge']);
      reloaded.dispose();
    });

    test('only technician accounts sign in', () {
      final s = c.read(sessionProvider.notifier);
      expect(s.login('minh@aivhrs.vn'), isFalse);
      expect(s.login('ha@aivhrs.vn'), isTrue);
      expect(c.read(myOrdersProvider).every((o) => o.assignment!.techId == 'T-01'), isTrue);
    });
  });

  testWidgets('sign in, preview, start the robot, then open QC', (tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    SharedPreferences.setMockInitialValues({'aivhrs-lang': 'en'});
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(ProviderScope(overrides: [prefsProvider.overrideWithValue(prefs)], child: const TechDesktopApp()));
    await tester.pumpAndSettle();
    expect(find.text('Technician desk'), findsOneWidget);

    await tester.tap(find.text('Hà Trần · T-01'));
    await tester.pump();
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Hà Trần'), findsWidgets);
    expect(find.text('My orders'), findsOneWidget);

    final container = ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));
    container.read(desktopRouterProvider).go('/tech/preview/VH-4821');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Preview VH-4821'), findsOneWidget);

    await tester.ensureVisible(find.text('Prototype: play preview and pass preflight'));
    await tester.tap(find.text('Prototype: play preview and pass preflight'));
    await tester.pump();
    await tester.pump();
    await tester.ensureVisible(find.text('Start real robot'));
    await tester.pump();
    await tester.tap(find.text('Start real robot'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Start writing'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(container.read(orderByIdProvider('VH-4821'))!.run, isNotNull);

    container.read(techOrdersProvider.notifier).finishRobotRun('VH-4821');
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Writing finished'), findsOneWidget);

    await tester.ensureVisible(find.text('Go to photo and QC'));
    await tester.tap(find.text('Go to photo and QC'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Photo and QC for VH-4821'), findsOneWidget);

    await tester.ensureVisible(find.text('Prototype: tick all checks'));
    await tester.tap(find.text('Prototype: tick all checks'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Photos for the customer'), findsOneWidget);

    // Leave the page so its ticker and the clock stop before the test ends.
    container.read(desktopRouterProvider).go('/tech');
    await tester.pumpAndSettle();
    expect(container.read(desktopRouterProvider).routerDelegate.currentConfiguration.uri.path, '/tech');
    expect(GoRouter.of(tester.element(find.text('My orders'))), isNotNull);
  });
}
