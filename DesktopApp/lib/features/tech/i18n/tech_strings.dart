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
  'dk.prototype': 'Prototype mode',
  'dk.prototypeHint': 'Shows shortcut buttons that skip steps of the simulated flow.',
  'dk.reset': 'Reset demo orders',
  'dk.resetDone': 'Demo orders restored.',
  'dk.blank': 'This page is blank.',
  'dk.photoPick': 'Choose a photo of the sheet',
  'dk.techDesk': 'Technician desk',
  'dk.login.lede': 'Sign in with your technical staff account.',
  'dk.login.forgot': 'Forgot password?',
  'dk.login.waking': 'The first sign-in after a quiet spell can take up to a minute while the server wakes up.',
  'dk.reset.title': 'Reset password',
  'dk.reset.body': 'We will email you a link to choose a new password.',
  'dk.reset.send': 'Send reset link',
  'dk.reset.sent': 'If {email} has an account, a reset link is on its way.',
  'dk.restoring': 'Restoring your session…',
  'dk.err.credentials': 'Email or password is incorrect.',
  'dk.err.disabled': 'This account is locked or disabled. Ask an admin to unlock it.',
  'dk.err.locked': 'Too many wrong passwords. Wait a few minutes and try again.',
  'dk.err.rate': 'Too many attempts. Wait a moment and try again.',
  'dk.err.validation': 'Please check the email and password.',
  'dk.err.timeout': 'The server is taking too long to answer. It may be waking up, try again.',
  'dk.err.offline': 'No connection to the server. Check your network.',
  'dk.err.server': 'The server had a problem. Try again later.',
  'dk.err.unknown': 'Something went wrong. Try again.',
  'dk.err.role': 'This desk is for technical staff. Customers and office staff use their own apps.',
  'dk.err.expired': 'Your session has expired. Please sign in again.',
};

const _desktopJa = {
  'dk.appTitle': 'AI-VHRS 技術者デスク',
  'dk.prototype': 'プロトタイプモード',
  'dk.prototypeHint': 'シミュレーションの手順を飛ばすショートカットボタンを表示します。',
  'dk.reset': 'デモ注文をリセット',
  'dk.resetDone': 'デモ注文を元に戻しました。',
  'dk.blank': 'このページは空白です。',
  'dk.photoPick': '用紙の写真を選択',
  'dk.techDesk': '技術者デスク',
  'dk.login.lede': '技術スタッフのアカウントでサインインしてください。',
  'dk.login.forgot': 'パスワードをお忘れですか？',
  'dk.login.waking': 'しばらく使われていないと、サーバーの起動に最大1分ほどかかります。',
  'dk.reset.title': 'パスワードの再設定',
  'dk.reset.body': '新しいパスワードを設定するためのリンクをメールでお送りします。',
  'dk.reset.send': '再設定リンクを送信',
  'dk.reset.sent': '{email} のアカウントがあれば、再設定リンクを送信しました。',
  'dk.restoring': 'セッションを復元しています…',
  'dk.err.credentials': 'メールアドレスまたはパスワードが正しくありません。',
  'dk.err.disabled': 'このアカウントはロックまたは無効化されています。管理者に解除を依頼してください。',
  'dk.err.locked': 'パスワードの誤りが多すぎます。数分待ってから再度お試しください。',
  'dk.err.rate': '操作が多すぎます。少し待ってから再度お試しください。',
  'dk.err.validation': 'メールアドレスとパスワードを確認してください。',
  'dk.err.timeout': 'サーバーの応答に時間がかかっています。起動中の可能性があります。もう一度お試しください。',
  'dk.err.offline': 'サーバーに接続できません。ネットワークを確認してください。',
  'dk.err.server': 'サーバーで問題が発生しました。後でもう一度お試しください。',
  'dk.err.unknown': '問題が発生しました。もう一度お試しください。',
  'dk.err.role': 'このデスクは技術スタッフ専用です。お客様と事務スタッフはそれぞれのアプリをご利用ください。',
  'dk.err.expired': 'セッションの有効期限が切れました。もう一度サインインしてください。',
};

const _desktopVi = {
  'dk.appTitle': 'AI-VHRS Kỹ thuật viên',
  'dk.prototype': 'Chế độ mẫu thử',
  'dk.prototypeHint': 'Hiện các nút tắt để bỏ qua bước trong quy trình mô phỏng.',
  'dk.reset': 'Đặt lại đơn mẫu',
  'dk.resetDone': 'Đã khôi phục đơn mẫu.',
  'dk.blank': 'Trang này đang trống.',
  'dk.photoPick': 'Chọn ảnh của tờ giấy',
  'dk.techDesk': 'Bàn kỹ thuật viên',
  'dk.login.lede': 'Đăng nhập bằng tài khoản nhân viên kỹ thuật.',
  'dk.login.forgot': 'Quên mật khẩu?',
  'dk.login.waking': 'Lần đăng nhập đầu sau một lúc không dùng có thể mất tới một phút để máy chủ khởi động.',
  'dk.reset.title': 'Đặt lại mật khẩu',
  'dk.reset.body': 'Chúng tôi sẽ gửi email kèm liên kết để bạn đặt mật khẩu mới.',
  'dk.reset.send': 'Gửi liên kết',
  'dk.reset.sent': 'Nếu {email} có tài khoản, liên kết đặt lại đã được gửi.',
  'dk.restoring': 'Đang khôi phục phiên đăng nhập…',
  'dk.err.credentials': 'Email hoặc mật khẩu không đúng.',
  'dk.err.disabled': 'Tài khoản đã bị khoá hoặc vô hiệu hoá. Nhờ quản trị viên mở khoá.',
  'dk.err.locked': 'Nhập sai mật khẩu quá nhiều lần. Đợi vài phút rồi thử lại.',
  'dk.err.rate': 'Thao tác quá nhanh. Đợi một chút rồi thử lại.',
  'dk.err.validation': 'Hãy kiểm tra lại email và mật khẩu.',
  'dk.err.timeout': 'Máy chủ phản hồi quá lâu, có thể đang khởi động. Hãy thử lại.',
  'dk.err.offline': 'Không kết nối được máy chủ. Hãy kiểm tra mạng.',
  'dk.err.server': 'Máy chủ gặp sự cố. Hãy thử lại sau.',
  'dk.err.unknown': 'Đã có lỗi xảy ra. Hãy thử lại.',
  'dk.err.role': 'Bàn làm việc này dành cho nhân viên kỹ thuật. Khách hàng và nhân viên văn phòng dùng ứng dụng riêng.',
  'dk.err.expired': 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
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
