import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/prefs.dart';
import 'gen/en.dart';
import 'gen/ja.dart';
import 'gen/vi.dart';

/// Languages for the technician desk: English, Japanese, Vietnamese, as in the FE.
///
/// Shared strings are generated from `FE/src/i18n/*.ts` into `gen/` so both
/// apps read the same words. Keys only the desktop needs live below, under `dk.`.
enum Lang {
  en('EN', 'English', 'en_GB'),
  ja('JA', '日本語', 'ja_JP'),
  vi('VI', 'Tiếng Việt', 'vi_VN');

  final String code;
  final String label;

  /// intl locale for dates and numbers.
  final String locale;
  const Lang(this.code, this.label, this.locale);
}

const _desktopEn = {
  'dk.appTitle': 'AI-VHRS Technician',
  'dk.login.lede': 'Sign in with your technician account to open your desk.',
  'dk.login.notTech': 'This desk is for technicians. Use one of the accounts below.',
  'dk.login.accounts': 'Technician accounts',
  'dk.prototype': 'Prototype mode',
  'dk.prototypeHint': 'Shows shortcut buttons that skip steps of the simulated flow.',
  'dk.reset': 'Reset demo orders',
  'dk.resetDone': 'Demo orders restored.',
  'dk.blank': 'This page is blank.',
  'dk.photoPick': 'Choose a photo of the sheet',
  'dk.techDesk': 'Technician desk',
};

const _desktopJa = {
  'dk.appTitle': 'AI-VHRS 技術者デスク',
  'dk.login.lede': '技術者アカウントでサインインしてデスクを開きます。',
  'dk.login.notTech': 'このデスクは技術者専用です。下のアカウントを使ってください。',
  'dk.login.accounts': '技術者アカウント',
  'dk.prototype': 'プロトタイプモード',
  'dk.prototypeHint': 'シミュレーションの手順を飛ばすショートカットボタンを表示します。',
  'dk.reset': 'デモ注文をリセット',
  'dk.resetDone': 'デモ注文を元に戻しました。',
  'dk.blank': 'このページは空白です。',
  'dk.photoPick': '用紙の写真を選択',
  'dk.techDesk': '技術者デスク',
};

const _desktopVi = {
  'dk.appTitle': 'AI-VHRS Kỹ thuật viên',
  'dk.login.lede': 'Đăng nhập bằng tài khoản kỹ thuật viên để mở bàn làm việc.',
  'dk.login.notTech': 'Bàn làm việc này dành cho kỹ thuật viên. Hãy dùng một tài khoản bên dưới.',
  'dk.login.accounts': 'Tài khoản kỹ thuật viên',
  'dk.prototype': 'Chế độ mẫu thử',
  'dk.prototypeHint': 'Hiện các nút tắt để bỏ qua bước trong quy trình mô phỏng.',
  'dk.reset': 'Đặt lại đơn mẫu',
  'dk.resetDone': 'Đã khôi phục đơn mẫu.',
  'dk.blank': 'Trang này đang trống.',
  'dk.photoPick': 'Chọn ảnh của tờ giấy',
  'dk.techDesk': 'Bàn kỹ thuật viên',
};

final Map<Lang, Map<String, String>> _dict = {
  Lang.en: {...enStrings, ..._desktopEn},
  Lang.ja: {...jaStrings, ..._desktopJa},
  Lang.vi: {...viStrings, ..._desktopVi},
};

/// Every key exists in all three languages. Checked by `test/tech_i18n_test.dart`.
Map<Lang, Map<String, String>> get techDictionaries => _dict;

final _sep = RegExp(r'( · | × )');

/// Translator for one language. `t('qc.title', {'id': o.id})`, `t.tn('Cotton rag')`.
class T {
  final Lang lang;
  const T(this.lang);

  /// Unknown keys fall back to English, then to the key itself.
  String call(String key, [Map<String, Object?>? vars]) {
    var s = _dict[lang]![key] ?? _dict[Lang.en]![key] ?? key;
    vars?.forEach((k, v) => s = s.replaceAll('{$k}', '$v'));
    return s;
  }

  /// Translates catalog names (paper, ink, order titles). Unknown text is returned as is.
  String tn(String s) {
    if (lang == Lang.en) return s;
    final d = _dict[lang]!;
    final whole = d['n.$s'];
    if (whole != null) return whole;
    if (!_sep.hasMatch(s)) return s;
    return s.splitMapJoin(_sep, onMatch: (m) => m[0]!, onNonMatch: (part) => d['n.$part'] ?? part);
  }

  String get locale => lang.locale;
}

class LangNotifier extends StateNotifier<Lang> {
  final Prefs _prefs;
  LangNotifier(this._prefs) : super(_initial(_prefs));

  static const _key = 'aivhrs-lang';

  static Lang _initial(Prefs prefs) {
    final saved = prefs.getString(_key);
    for (final l in Lang.values) {
      if (l.name == saved) return l;
    }
    final sys = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    return Lang.values.firstWhere((l) => l.name == sys, orElse: () => Lang.en);
  }

  void set(Lang l) {
    state = l;
    _prefs.setString(_key, l.name);
  }

  void cycle() => set(Lang.values[(state.index + 1) % Lang.values.length]);
}

final langProvider = StateNotifierProvider<LangNotifier, Lang>((ref) => LangNotifier(ref.watch(prefsProvider)));

/// `final t = ref.watch(tProvider);`
final tProvider = Provider<T>((ref) => T(ref.watch(langProvider)));
