import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/features/tech/data/notification_api.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/notification.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/notification_bell.dart';

Map<String, dynamic> _n(int id, String code, {bool read = false}) => {
      'id': id,
      'order_id': 100 + id,
      'type': 'PRODUCTION_STATUS_CHANGED',
      'msg_code': code,
      'title': code == 'JOB_CANCELLED' ? 'Job bị huỷ' : 'Bạn có job mới',
      'body': 'Đơn VHRS-$id',
      'is_read': read,
      'read_at': null,
      'created_at': '2026-11-26T0$id:00:00Z',
    };

class _Api implements NotificationApi {
  var items = [_n(2, 'JOB_CANCELLED'), _n(1, 'JOB_ASSIGNED', read: true)];
  final read = <int>[];
  var readAll = 0;
  int? before;

  @override
  Future<NotificationPage> list({int? beforeId, int limit = 20}) async {
    before = beforeId;
    if (beforeId != null) return NotificationPage.fromJson({'items': [_n(0, 'JOB_ASSIGNED', read: true)], 'unread_count': 0, 'next_before_id': null});
    return NotificationPage.fromJson({
      'items': items,
      'unread_count': items.where((n) => n['is_read'] != true).length,
      'next_before_id': 1,
    });
  }

  @override
  Future<void> markRead(int id) async {
    read.add(id);
    items = [for (final n in items) n['id'] == id ? {...n, 'is_read': true} : n];
  }

  @override
  Future<void> markAllRead() async {
    readAll++;
    items = [for (final n in items) {...n, 'is_read': true}];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, _Api api, {String lang = 'en', Size size = const Size(1440, 900)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({'aivhrs-lang': lang});
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(ProviderScope(
    overrides: [prefsProvider.overrideWithValue(prefs), notificationApiProvider.overrideWithValue(api)],
    child: const MaterialApp(home: Scaffold(body: Align(alignment: Alignment.topRight, child: NotificationBell()))),
  ));
  await tester.pump();
  await tester.pump();
}

Future<void> _leave(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  testWidgets('the bell shows the unread count and lists the job notifications', (tester) async {
    final api = _Api();
    await _pump(tester, api);
    expect(find.text('1'), findsOneWidget);
    await tester.tap(find.byType(NotificationBell));
    await tester.pumpAndSettle();
    expect(find.text('Job bị huỷ'), findsOneWidget);
    expect(find.text('Bạn có job mới'), findsOneWidget);
    expect(find.text('Order #102'), findsOneWidget);
    expect(find.text('Unread'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('opening one marks it read; mark all clears the rest; load more pages back', (tester) async {
    final api = _Api();
    await _pump(tester, api);
    await tester.tap(find.byType(NotificationBell));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Job bị huỷ'));
    await tester.pumpAndSettle();
    expect(api.read, [2]);
    expect(find.text('Unread'), findsNothing);

    api.items = [_n(3, 'JOB_ASSIGNED'), ...api.items];
    final c = ProviderScope.containerOf(tester.element(find.byType(NotificationList)));
    c.invalidate(notificationsProvider);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mark all as read'));
    await tester.pumpAndSettle();
    expect(api.readAll, 1);
    expect(find.text('Mark all as read'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();
    expect(api.before, 1);
    expect(find.text('Order #100'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('it fits a phone in Vietnamese and Japanese', (tester) async {
    for (final lang in ['vi', 'ja']) {
      await _pump(tester, _Api(), lang: lang, size: const Size(390, 844));
      await tester.tap(find.byType(NotificationBell));
      await tester.pumpAndSettle();
      expect(find.text('Notifications'), findsNothing);
      expect(tester.takeException(), isNull);
      await _leave(tester);
    }
  });
}
