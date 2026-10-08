import 'package:flutter/material.dart';
import '../constants/app_colors.dart';

/// A reusable loading indicator widget with optional message.
/// Supports full-screen overlay and inline modes.
class LoadingView extends StatelessWidget {
  final String? message;
  final bool isOverlay;
  final Color? color;

  const LoadingView({
    super.key,
    this.message,
    this.isOverlay = false,
    this.color,
  });

  /// Shows a full-screen loading overlay on top of existing content.
  static Widget overlay({String? message}) {
    return LoadingView(message: message, isOverlay: true);
  }

  /// Shows an inline loading indicator for use within scrollable areas.
  static Widget inline({String? message}) {
    return LoadingView(message: message, isOverlay: false);
  }

  @override
  Widget build(BuildContext context) {
    final indicator = Column(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        SizedBox(
          width: 48,
          height: 48,
          child: CircularProgressIndicator(
            strokeWidth: 3,
            valueColor: AlwaysStoppedAnimation<Color>(
              color ?? AppColors.primary,
            ),
          ),
        ),
        if (message != null) ...[
          const SizedBox(height: 16),
          Text(
            message!,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ],
    );

    if (isOverlay) {
      return Container(
        color: Colors.black.withOpacity(0.3),
        child: Center(
          child: Container(
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.1),
                  blurRadius: 20,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: indicator,
          ),
        ),
      );
    }

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: indicator,
      ),
    );
  }
}
