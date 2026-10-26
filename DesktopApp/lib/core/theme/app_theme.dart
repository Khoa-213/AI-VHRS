import 'package:flutter/material.dart';
import '../constants/app_colors.dart';

/// AI-VHRS application theme configuration.
///
/// Monochrome ink-on-paper: pill buttons, soft 28px cards, lowercase display
/// headings with tight tracking. Both themes are built from one recipe so
/// they never drift apart.
class AppTheme {
  AppTheme._();

  // ─── Tokens ────────────────────────────────────────────────────────

  static const String fontFamily = 'BeVietnamPro';

  static const double radiusCard = 28;
  static const double radiusInner = 16;
  static const double radiusSmall = 10;

  static const Duration motionFast = Duration(milliseconds: 180);
  static const Duration motionMedium = Duration(milliseconds: 280);
  static const Curve motionCurve = Curves.easeOutCubic;

  // ─── Typography ────────────────────────────────────────────────────

  static TextTheme _textTheme(Color primary, Color secondary) => TextTheme(
        displayLarge: TextStyle(
          fontSize: 34,
          fontWeight: FontWeight.w600,
          letterSpacing: -1.2,
          height: 1.1,
          color: primary,
        ),
        displayMedium: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.9,
          height: 1.15,
          color: primary,
        ),
        displaySmall: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.6,
          height: 1.2,
          color: primary,
        ),
        headlineLarge: TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.5,
          height: 1.25,
          color: primary,
        ),
        headlineMedium: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.4,
          height: 1.3,
          color: primary,
        ),
        headlineSmall: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.3,
          height: 1.3,
          color: primary,
        ),
        titleLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.2,
          height: 1.4,
          color: primary,
        ),
        titleMedium: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          height: 1.4,
          color: primary,
        ),
        titleSmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          height: 1.4,
          color: primary,
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w400,
          height: 1.55,
          color: primary,
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w400,
          height: 1.55,
          color: primary,
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w400,
          height: 1.5,
          color: secondary,
        ),
        labelLarge: const TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.1,
          height: 1.3,
        ),
        labelMedium: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          height: 1.3,
          color: secondary,
        ),
        labelSmall: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          letterSpacing: 0.2,
          height: 1.3,
          color: secondary,
        ),
      );

  // ─── Themes ────────────────────────────────────────────────────────

  static ThemeData get lightTheme => _build(
        brightness: Brightness.light,
        background: AppColors.background,
        surface: AppColors.surface,
        surfaceVariant: AppColors.surfaceVariant,
        border: AppColors.border,
        textPrimary: AppColors.textPrimary,
        textSecondary: AppColors.textSecondary,
        textTertiary: AppColors.textTertiary,
        accent: AppColors.ink,
        onAccent: AppColors.onInk,
      );

  static ThemeData get darkTheme => _build(
        brightness: Brightness.dark,
        background: AppColors.darkBackground,
        surface: AppColors.darkSurface,
        surfaceVariant: AppColors.darkSurfaceVariant,
        border: AppColors.darkBorder,
        textPrimary: AppColors.darkTextPrimary,
        textSecondary: AppColors.darkTextSecondary,
        textTertiary: AppColors.textSecondary,
        accent: AppColors.darkTextPrimary,
        onAccent: AppColors.ink,
      );

  static ThemeData _build({
    required Brightness brightness,
    required Color background,
    required Color surface,
    required Color surfaceVariant,
    required Color border,
    required Color textPrimary,
    required Color textSecondary,
    required Color textTertiary,
    required Color accent,
    required Color onAccent,
  }) {
    const buttonText = TextStyle(
      fontFamily: fontFamily,
      fontSize: 15,
      fontWeight: FontWeight.w600,
      letterSpacing: -0.1,
    );
    const pill = StadiumBorder();
    const buttonPadding = EdgeInsets.symmetric(horizontal: 28, vertical: 16);

    OutlineInputBorder inputBorder(Color color, [double width = 1]) =>
        OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusInner),
          borderSide: BorderSide(color: color, width: width),
        );

    return ThemeData(
      useMaterial3: true,
      fontFamily: fontFamily,
      brightness: brightness,
      colorScheme: ColorScheme(
        brightness: brightness,
        primary: accent,
        onPrimary: onAccent,
        secondary: textSecondary,
        onSecondary: onAccent,
        surface: surface,
        onSurface: textPrimary,
        surfaceContainerHighest: surfaceVariant,
        error: AppColors.error,
        onError: AppColors.onInk,
        outline: border,
        outlineVariant: border,
      ),
      scaffoldBackgroundColor: background,
      textTheme: _textTheme(textPrimary, textSecondary),
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
      appBarTheme: AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: textPrimary,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontFamily: fontFamily,
          fontSize: 17,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.3,
          color: textPrimary,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusCard),
        ),
        color: surface,
        margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: onAccent,
          disabledBackgroundColor: textTertiary.withValues(alpha: 0.4),
          disabledForegroundColor: onAccent.withValues(alpha: 0.8),
          elevation: 0,
          padding: buttonPadding,
          shape: pill,
          textStyle: buttonText,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: onAccent,
          padding: buttonPadding,
          shape: pill,
          textStyle: buttonText,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: textPrimary,
          padding: buttonPadding,
          shape: pill,
          side: BorderSide(color: border, width: 1.2),
          textStyle: buttonText,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: textPrimary,
          shape: pill,
          textStyle: buttonText,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        border: inputBorder(border),
        enabledBorder: inputBorder(border),
        focusedBorder: inputBorder(accent, 1.4),
        errorBorder: inputBorder(AppColors.error),
        focusedErrorBorder: inputBorder(AppColors.error, 1.4),
        hintStyle: TextStyle(color: textTertiary),
        errorStyle: const TextStyle(color: AppColors.error, fontSize: 12),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surface,
        selectedColor: accent,
        side: BorderSide(color: border),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        shape: pill,
        labelStyle: TextStyle(
          fontFamily: fontFamily,
          fontSize: 13,
          fontWeight: FontWeight.w500,
          color: textPrimary,
        ),
      ),
      sliderTheme: SliderThemeData(
        activeTrackColor: accent,
        inactiveTrackColor: surfaceVariant,
        thumbColor: accent,
        overlayColor: accent.withValues(alpha: 0.06),
        trackHeight: 4,
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: accent,
        linearTrackColor: surfaceVariant,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: background,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        dragHandleColor: textTertiary.withValues(alpha: 0.5),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(radiusCard)),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: border,
        thickness: 1,
        space: 1,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
        contentTextStyle: const TextStyle(
          fontFamily: fontFamily,
          fontSize: 14,
          color: AppColors.onInk,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusInner),
        ),
      ),
    );
  }
}
