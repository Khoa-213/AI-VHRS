import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:ai_vhrs_mobile/features/tech/i18n/tech_strings.dart';

import '../tool/gen_i18n.dart' as gen;

final _placeholder = RegExp(r'\{(\w+)\}');
Set<String> _vars(String s) => {for (final m in _placeholder.allMatches(s)) m[1]!};

void main() {
  test('generated files match the FE dictionaries', () {
    gen.generateAll().forEach((lang, text) {
      expect(File('${gen.outDir}/$lang.dart').readAsStringSync(), text, reason: 'run: dart run tool/gen_i18n.dart');
    });
  });

  test('every key exists in all three languages with the same placeholders', () {
    final en = techDictionaries[Lang.en]!;
    for (final lang in [Lang.ja, Lang.vi]) {
      final d = techDictionaries[lang]!;
      expect(d.keys.toSet(), en.keys.toSet(), reason: lang.name);
      for (final k in en.keys.where((k) => k.startsWith('dk.'))) {
        expect(_vars(d[k]!), _vars(en[k]!), reason: '${lang.name} $k');
      }
    }
  });

  test('the areas the robot and job screens need are generated', () {
    final en = techDictionaries[Lang.en]!;
    for (final area in ['td.flow.', 'rb.', 'js.', 'wk.', 'err.', 'role.']) {
      expect(en.keys.any((k) => k.startsWith(area)), true, reason: area);
    }
  });

  test('the parser reads both quote styles and escapes, and refuses anything else', () {
    final d = gen.parseDictionary(
      'export const en = {\n'
      '  // a comment\n'
      r'''  "a.one": "say \"hi\" {n}",''' '\n'
      r"""  'a.two': 'it\'s $5\nnext',""" '\n'
      '}\n',
      'test',
    );
    expect(d, {'a.one': 'say "hi" {n}', 'a.two': "it's \$5\nnext"});
    expect(() => gen.parseDictionary("  'a.three': 'x' + y,", 'test'), throwsFormatException);
  });
}
