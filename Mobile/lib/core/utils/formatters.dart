import 'package:intl/intl.dart';

/// Formatting utilities for dates, currency, and text throughout the app.
class Formatters {
  Formatters._();

  // ─── Date & Time ───────────────────────────────────────────────────

  static final DateFormat _dateFormat = DateFormat('dd/MM/yyyy');
  static final DateFormat _dateTimeFormat = DateFormat('dd/MM/yyyy HH:mm');
  static final DateFormat _timeFormat = DateFormat('HH:mm');
  static final DateFormat _shortDateFormat = DateFormat('dd MMM');
  static final DateFormat _fullDateFormat = DateFormat('dd MMMM yyyy');

  static String formatDate(DateTime date) => _dateFormat.format(date);
  static String formatDateTime(DateTime date) => _dateTimeFormat.format(date);
  static String formatTime(DateTime date) => _timeFormat.format(date);
  static String formatShortDate(DateTime date) => _shortDateFormat.format(date);
  static String formatFullDate(DateTime date) => _fullDateFormat.format(date);

  /// Returns a human-readable relative time string (e.g., "2 hours ago").
  static String timeAgo(DateTime dateTime) {
    final now = DateTime.now();
    final diff = now.difference(dateTime);

    if (diff.inSeconds < 60) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    if (diff.inDays < 30) return '${(diff.inDays / 7).floor()}w ago';
    if (diff.inDays < 365) return '${(diff.inDays / 30).floor()}mo ago';
    return '${(diff.inDays / 365).floor()}y ago';
  }

  // ─── Currency ──────────────────────────────────────────────────────

  static final NumberFormat _vnCurrencyFormat = NumberFormat.currency(
    locale: 'vi_VN',
    symbol: '₫',
    decimalDigits: 0,
  );

  static final NumberFormat _usCurrencyFormat = NumberFormat.currency(
    locale: 'en_US',
    symbol: '\$',
    decimalDigits: 2,
  );

  /// Formats a value as Vietnamese Dong.
  static String formatVND(num amount) => _vnCurrencyFormat.format(amount);

  /// Formats a value as US Dollars.
  static String formatUSD(num amount) => _usCurrencyFormat.format(amount);

  /// Formats a compact number (e.g., 1.2K, 3.4M).
  static String compactNumber(num value) {
    return NumberFormat.compact().format(value);
  }

  // ─── Text ──────────────────────────────────────────────────────────

  /// Truncates text to a maximum length with ellipsis.
  static String truncate(String text, int maxLength) {
    if (text.length <= maxLength) return text;
    return '${text.substring(0, maxLength)}…';
  }

  /// Capitalizes the first letter of a string.
  static String capitalize(String text) {
    if (text.isEmpty) return text;
    return text[0].toUpperCase() + text.substring(1);
  }

  /// Converts a snake_case status string to a display label.
  static String statusLabel(String status) {
    return status
        .split('_')
        .map((word) => capitalize(word))
        .join(' ');
  }
}
