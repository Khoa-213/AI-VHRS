import 'package:flutter/material.dart';
import '../constants/app_colors.dart';
import 'custom_button.dart';

/// A standardized error display widget with retry capability.
class ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;
  final IconData icon;

  const ErrorView({
    super.key,
    required this.message,
    this.onRetry,
    this.icon = Icons.error_outline_rounded,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 88,
              height: 88,
              decoration: BoxDecoration(
                color: AppColors.surface,
                shape: BoxShape.circle,
                border: Border.all(color: AppColors.border),
              ),
              child: Icon(
                icon,
                size: 34,
                color: AppColors.error,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'couldn\'t load this.',
              style: theme.textTheme.headlineSmall?.copyWith(
                color: AppColors.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              message,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: AppColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              CustomButton(
                label: 'Try again',
                onPressed: onRetry,
                isExpanded: false,
                style: CustomButtonStyle.outline,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
