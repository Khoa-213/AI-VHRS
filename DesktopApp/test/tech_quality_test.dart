import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_vhrs_mobile/core/network/network_exceptions.dart';
import 'package:ai_vhrs_mobile/features/tech/data/prefs.dart';
import 'package:ai_vhrs_mobile/features/tech/data/providers.dart';
import 'package:ai_vhrs_mobile/features/tech/data/tech_api.dart';
import 'package:ai_vhrs_mobile/features/tech/domain/job.dart';
import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';
import 'package:ai_vhrs_mobile/features/tech/presentation/widgets/job_quality.dart';

QualityEvaluation _result(int id, int photo, String verdict, {int page = 1}) => QualityEvaluation.fromJson({
      'id': id,
      'photo_id': photo,
      'job_id': 9,
      'page': page,
      'method': 'chamfer-v1',
      'verdict': verdict,
      'metrics': {'coverage_pct': 91.5, 'chamfer_mm': 0.42, 'warnings': ['Ảnh hơi tối'], 'thresholds': {'source': 'default'}},
      'overlay_url': null,
      'created_at': '2026-11-26T03:00:00Z',
      'advisory': 'Nét khớp phác thảo.',
    });

class _Api implements TechApi {
  final results = <QualityEvaluation>[];
  final calls = <(int, int)>[];
  bool fail = false;

  @override
  Future<List<QualityEvaluation>> quality(int id) async => List.of(results.reversed);

  @override
  Future<QualityEvaluation> evaluatePhoto(int id, int photoId, {int page = 1}) async {
    calls.add((photoId, page));
    if (fail) throw const ConflictException('No sketch', 'NO_APPROVED_SKETCH');
    final r = _result(results.length + 1, photoId, 'NEEDS_REVIEW', page: page);
    results.add(r);
    return r;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _photos = [
  ProductPhoto(id: 5, kind: PhotoKind.overall, urlExpiresIn: 0, createdAt: DateTime.utc(2026)),
  ProductPhoto(id: 6, kind: PhotoKind.closeUp, urlExpiresIn: 0, createdAt: DateTime.utc(2026)),
];

Future<void> _pump(WidgetTester tester, _Api api, {String lang = 'en', Size size = const Size(1200, 1400)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({'aivhrs-lang': lang});
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(ProviderScope(
    overrides: [prefsProvider.overrideWithValue(prefs), techApiProvider.overrideWithValue(api)],
    child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: JobQualityCard(jobId: 9, photos: _photos, disabled: false)))),
  ));
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() async {
    for (final l in Lang.values) {
      await initializeDateFormatting(l.locale);
    }
  });

  test('a result reads its numbers and warnings; unknown metrics are left out', () {
    final r = _result(1, 5, 'PASS');
    expect(r.numbers.map((n) => n.$1), ['coverage_pct', 'chamfer_mm']);
    expect(r.warnings, ['Ảnh hơi tối']);
  });

  testWidgets('each photo can be evaluated against a chosen sketch page; the verdict is the backend\'s', (tester) async {
    final api = _Api();
    await _pump(tester, api);
    expect(find.text('Quality check against the sketch'), findsOneWidget);
    expect(find.text('Not evaluated'), findsNWidgets(2));
    expect(find.text('No evaluations for this job yet.'), findsOneWidget);

    await tester.tap(find.byType(DropdownButtonFormField<int>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('3').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Evaluate').first);
    await tester.pumpAndSettle();

    expect(api.calls, [(5, 3)]);
    expect(find.text('Needs review'), findsWidgets);
    expect(find.text('Evaluate again'), findsOneWidget);
    expect(find.text('All evaluations (1)'), findsOneWidget);
    expect(find.text('Verdicts use the backend\'s default thresholds, which are not validated yet.'), findsOneWidget);

    await tester.tap(find.text('All evaluations (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Nét khớp phác thảo.'), findsOneWidget);
    expect(find.text('91.5 %'), findsOneWidget);
    expect(find.text('Ảnh hơi tối'), findsOneWidget);
  });

  testWidgets('a refused evaluation says why under that photo', (tester) async {
    final api = _Api()..fail = true;
    await _pump(tester, api);
    await tester.tap(find.text('Evaluate').last);
    await tester.pumpAndSettle();
    expect(api.calls, [(6, 1)]);
    expect(find.text('Not evaluated'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('it fits a phone in Vietnamese and Japanese', (tester) async {
    for (final lang in ['vi', 'ja']) {
      await _pump(tester, _Api(), lang: lang, size: const Size(390, 1400));
      expect(find.text('Quality check against the sketch'), findsNothing);
      expect(tester.takeException(), isNull);
    }
  });
}
