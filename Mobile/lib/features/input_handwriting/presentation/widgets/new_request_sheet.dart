import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../domain/input_mode.dart';

/// Opens the "new writing request" sheet. Picking a mode and continuing
/// starts project creation with that mode preselected.
Future<void> showNewRequestSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useRootNavigator: true,
    builder: (_) => const NewRequestSheet(),
  );
}

class NewRequestSheet extends StatefulWidget {
  const NewRequestSheet({super.key});

  @override
  State<NewRequestSheet> createState() => _NewRequestSheetState();
}

class _NewRequestSheetState extends State<NewRequestSheet> {
  InputMode _selected = InputMode.image;

  void _continue() {
    final router = GoRouter.of(context);
    Navigator.of(context).pop();
    router.push('/projects/create?mode=${_selected.name}');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Text('new writing request.', style: theme.textTheme.displaySmall),
            ),
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Text(
                'How will you give the robot your words?',
                style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.textSecondary),
              ),
            ),
            const SizedBox(height: 24),
            Container(
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                children: [
                  for (final mode in InputMode.values) ...[
                    _ModeRow(
                      mode: mode,
                      selected: mode == _selected,
                      onTap: () => setState(() => _selected = mode),
                    ),
                    if (mode != InputMode.values.last)
                      const Divider(indent: 76, endIndent: 20),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 24),
            CustomButton(label: 'Continue', onPressed: _continue),
          ],
        ),
      ),
    );
  }
}

class _ModeRow extends StatelessWidget {
  final InputMode mode;
  final bool selected;
  final VoidCallback onTap;

  const _ModeRow({required this.mode, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Pressable(
      onTap: onTap,
      pressedScale: 0.985,
      semanticLabel: mode.title,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 16, 18),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: ModeGlyph(kind: mode.glyph, size: 36),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Tag(mode.tag),
                  const SizedBox(height: 8),
                  Text(mode.title, style: theme.textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(
                    mode.description,
                    style: theme.textTheme.bodySmall?.copyWith(height: 1.5),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.only(top: 2),
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: selected ? AppColors.ink : Colors.transparent,
                border: Border.all(
                  color: selected ? AppColors.ink : AppColors.textTertiary,
                  width: 1.5,
                ),
              ),
              child: selected
                  ? const Icon(Icons.check_rounded, size: 14, color: AppColors.onInk)
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  final String label;
  const _Tag(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.secondaryDark,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 10.5,
          fontWeight: FontWeight.w600,
          color: AppColors.onInk,
          letterSpacing: 0.2,
        ),
      ),
    );
  }
}
