import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/utils/validators.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../input_handwriting/domain/input_mode.dart';
import '../project_notifier.dart';

/// First step of a request: name it, choose paper and pen.
class CreateProjectScreen extends ConsumerStatefulWidget {
  /// Input mode chosen in the new-request sheet, carried to the input step.
  final InputMode? mode;

  const CreateProjectScreen({super.key, this.mode});

  @override
  ConsumerState<CreateProjectScreen> createState() => _CreateProjectScreenState();
}

class _CreateProjectScreenState extends ConsumerState<CreateProjectScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  String _selectedPaperSize = AppConstants.paperSizes[1].id;
  String _selectedPenType = AppConstants.penTypes[2].id;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _handleCreate() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _isSubmitting = true);

    final project = await ref.read(projectListProvider.notifier).createProject(
          name: _nameController.text.trim(),
          paperSizeId: _selectedPaperSize,
          penTypeId: _selectedPenType,
        );

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    if (project != null) {
      final mode = widget.mode == null ? '' : '?mode=${widget.mode!.name}';
      context.pushReplacement('/projects/${project.id}/input$mode');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ref.read(projectListProvider).error ?? 'We couldn\'t create the project. Try again.',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
              child: Row(
                children: [
                  IconButton(
                    tooltip: 'Back',
                    onPressed: () => context.pop(),
                    icon: const Icon(Icons.chevron_left_rounded, size: 28),
                  ),
                  const Expanded(child: Center(child: StepDashes(total: 4, current: 0))),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 32),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('set the page.', style: theme.textTheme.displayMedium),
                      const SizedBox(height: 8),
                      Text(
                        widget.mode == null
                            ? 'Name the project, then pick paper and pen.'
                            : 'Next: ${widget.mode!.title.toLowerCase()}. First, paper and pen.',
                        style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.textSecondary),
                      ),
                      const SizedBox(height: 32),

                      CustomTextField(
                        label: 'Project name',
                        hint: 'e.g., Thiệp cưới Minh & An',
                        controller: _nameController,
                        textCapitalization: TextCapitalization.sentences,
                        validator: (value) => Validators.required(value, 'Project name'),
                        enabled: !_isSubmitting,
                      ),
                      const SizedBox(height: 32),

                      _SectionLabel('Paper'),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: AppConstants.paperSizes.map((size) {
                          final isSelected = _selectedPaperSize == size.id;
                          return Pressable(
                            onTap: _isSubmitting ? null : () => setState(() => _selectedPaperSize = size.id),
                            semanticLabel: size.name,
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                              decoration: BoxDecoration(
                                color: isSelected ? AppColors.ink : AppColors.surface,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: isSelected ? AppColors.ink : AppColors.border,
                                  width: 1.2,
                                ),
                              ),
                              child: Column(
                                children: [
                                  Text(
                                    size.name,
                                    style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 14,
                                      color: isSelected ? AppColors.onInk : AppColors.textPrimary,
                                    ),
                                  ),
                                  if (size.width > 0) ...[
                                    const SizedBox(height: 2),
                                    Text(
                                      '${size.width.round()} × ${size.height.round()}',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: isSelected ? AppColors.onInkMuted : AppColors.textTertiary,
                                        fontFeatures: const [FontFeature.tabularFigures()],
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                      const SizedBox(height: 32),

                      _SectionLabel('Pen'),
                      const SizedBox(height: 12),
                      Container(
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: Column(
                          children: [
                            for (final pen in AppConstants.penTypes) ...[
                              _PenRow(
                                name: pen.name,
                                strokeWidth: pen.strokeWidth,
                                selected: _selectedPenType == pen.id,
                                onTap: _isSubmitting
                                    ? null
                                    : () => setState(() => _selectedPenType = pen.id),
                              ),
                              if (pen != AppConstants.penTypes.last)
                                const Divider(indent: 20, endIndent: 20),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(height: 40),

                      CustomButton(
                        label: 'Continue',
                        onPressed: _handleCreate,
                        isLoading: _isSubmitting,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(color: AppColors.textSecondary),
    );
  }
}

class _PenRow extends StatelessWidget {
  final String name;
  final double strokeWidth;
  final bool selected;
  final VoidCallback? onTap;

  const _PenRow({
    required this.name,
    required this.strokeWidth,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      pressedScale: 0.985,
      semanticLabel: name,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        child: Row(
          children: [
            // Stroke sample at the pen's relative weight.
            SizedBox(
              width: 36,
              child: Container(
                height: (strokeWidth * 2).clamp(1.0, 6.0),
                decoration: BoxDecoration(
                  color: AppColors.ink,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
            const SizedBox(width: 18),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    Formatters.capitalize(name.toLowerCase()),
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
                  ),
                  Text(
                    '$strokeWidth mm line',
                    style: const TextStyle(fontSize: 12, color: AppColors.textTertiary),
                  ),
                ],
              ),
            ),
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
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
