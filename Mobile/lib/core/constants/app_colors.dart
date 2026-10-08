import 'package:flutter/material.dart';

/// Application-wide color constants — an ink-on-paper palette.
///
/// One cool neutral gray family (zinc) plus ink black. Semantic colors are
/// deliberately muted so nothing on screen competes with the handwriting.
class AppColors {
  AppColors._();

  // Ink & Paper
  static const Color ink = Color(0xFF121212);
  static const Color inkSoft = Color(0xFF232326);
  static const Color paper = Color(0xFFF7F7F8);
  static const Color onInk = Color(0xFFFAFAFA);
  static const Color onInkMuted = Color(0xFF9A9AA2);

  // Primary Brand Colors (ink)
  static const Color primary = Color(0xFF18181B);
  static const Color primaryLight = Color(0xFF3F3F46);
  static const Color primaryDark = Color(0xFF09090B);

  // Secondary (charcoal)
  static const Color secondary = Color(0xFF3F3F46);
  static const Color secondaryLight = Color(0xFF52525B);
  static const Color secondaryDark = Color(0xFF27272A);

  // Semantic Colors — desaturated
  static const Color success = Color(0xFF3F6B4E);
  static const Color warning = Color(0xFF8A6420);
  static const Color error = Color(0xFFA8322A);
  static const Color info = Color(0xFF52525B);

  // Neutral / Surface Colors
  static const Color background = paper;
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceVariant = Color(0xFFEFEFF1);
  static const Color border = Color(0xFFE6E6E9);
  static const Color divider = Color(0xFFEDEDEF);

  // Text Colors
  static const Color textPrimary = Color(0xFF18181B);
  static const Color textSecondary = Color(0xFF71717A);
  static const Color textTertiary = Color(0xFFA1A1AA);
  static const Color textOnPrimary = Color(0xFFFFFFFF);

  // Dark Mode Colors
  static const Color darkBackground = Color(0xFF0E0E10);
  static const Color darkSurface = Color(0xFF18181B);
  static const Color darkSurfaceVariant = Color(0xFF232326);
  static const Color darkBorder = Color(0xFF2E2E33);
  static const Color darkTextPrimary = Color(0xFFF4F4F5);
  static const Color darkTextSecondary = Color(0xFFA1A1AA);

  // Status Colors (for request tracking) — an ink ramp that darkens as the
  // order progresses; only the finished state carries a hue.
  static const Color statusAwaitingPayment = Color(0xFFA1A1AA);
  static const Color statusPaid = Color(0xFF71717A);
  static const Color statusApproved = Color(0xFF52525B);
  static const Color statusWriting = Color(0xFF18181B);
  static const Color statusDone = success;

  // Shadows — tinted to the paper hue rather than pure black
  static const Color shadow = Color(0x0F1B1B2A);
}
