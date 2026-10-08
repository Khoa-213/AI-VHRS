import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';

/// Available font styles for text-based handwriting.
class FontStyleOption {
  final String id;
  final String name;
  final String fontFamily;
  final FontWeight weight;
  final FontStyle style;

  const FontStyleOption({
    required this.id,
    required this.name,
    required this.fontFamily,
    this.weight = FontWeight.w400,
    this.style = FontStyle.normal,
  });
}

const _fontStyles = [
  FontStyleOption(id: 'regular', name: 'Regular', fontFamily: 'BeVietnamPro'),
  FontStyleOption(id: 'italic', name: 'Italic', fontFamily: 'BeVietnamPro', style: FontStyle.italic),
  FontStyleOption(id: 'bold', name: 'Bold', fontFamily: 'BeVietnamPro', weight: FontWeight.w700),
  FontStyleOption(id: 'cursive', name: 'Cursive', fontFamily: 'cursive'),
  FontStyleOption(id: 'serif', name: 'Serif', fontFamily: 'serif'),
  FontStyleOption(id: 'monospace', name: 'Monospace', fontFamily: 'monospace'),
];

/// Text + Font tab: enter text content and select a handwriting font style.
class TextFontTab extends ConsumerStatefulWidget {
  final String projectId;

  const TextFontTab({super.key, required this.projectId});

  @override
  ConsumerState<TextFontTab> createState() => _TextFontTabState();
}

class _TextFontTabState extends ConsumerState<TextFontTab>
    with AutomaticKeepAliveClientMixin {
  final _textController = TextEditingController();
  String _selectedFontId = _fontStyles.first.id;
  bool _isSubmitting = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  FontStyleOption get _selectedFont =>
      _fontStyles.firstWhere((f) => f.id == _selectedFontId);

  Future<void> _handleSubmit() async {
    if (_textController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter some text.'),
          backgroundColor: AppColors.warning,
        ),
      );
      return;
    }

    setState(() => _isSubmitting = true);
    await Future.delayed(const Duration(seconds: 2));
    setState(() => _isSubmitting = false);

    if (mounted) {
      context.push('/projects/${widget.projectId}/trajectory');
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Text Input Area
          Text(
            'Enter Your Text',
            style: theme.textTheme.titleSmall?.copyWith(
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border),
            ),
            child: TextField(
              controller: _textController,
              maxLines: 8,
              enabled: !_isSubmitting,
              style: TextStyle(
                fontFamily: _selectedFont.fontFamily,
                fontWeight: _selectedFont.weight,
                fontStyle: _selectedFont.style,
                fontSize: 16,
                height: 1.6,
              ),
              decoration: InputDecoration(
                hintText: 'Type the text you want written by the robot...',
                border: InputBorder.none,
                contentPadding: const EdgeInsets.all(16),
                hintStyle: theme.textTheme.bodyLarge?.copyWith(
                  color: AppColors.textTertiary,
                ),
              ),
              onChanged: (_) => setState(() {}),
            ),
          ),
          if (_textController.text.isNotEmpty) ...[
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerRight,
              child: Text(
                '${_textController.text.length} characters',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: AppColors.textTertiary,
                ),
              ),
            ),
          ],
          const SizedBox(height: 24),

          // Font Style Selector
          Text(
            'Font Style',
            style: theme.textTheme.titleSmall?.copyWith(
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 80,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: _fontStyles.length,
              separatorBuilder: (_, _) => const SizedBox(width: 10),
              itemBuilder: (context, index) {
                final font = _fontStyles[index];
                final isSelected = _selectedFontId == font.id;
                return GestureDetector(
                  onTap: _isSubmitting ? null : () => setState(() => _selectedFontId = font.id),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: 100,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? AppColors.primary.withOpacity(0.08)
                          : AppColors.surface,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: isSelected ? AppColors.primary : AppColors.border,
                        width: isSelected ? 2 : 1,
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          'Aa',
                          style: TextStyle(
                            fontFamily: font.fontFamily,
                            fontWeight: font.weight,
                            fontStyle: font.style,
                            fontSize: 22,
                            color: isSelected ? AppColors.primary : AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          font.name,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: isSelected ? AppColors.primary : AppColors.textTertiary,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 32),

          // Live Preview
          if (_textController.text.isNotEmpty) ...[
            Text(
              'Preview',
              style: theme.textTheme.titleSmall?.copyWith(
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.04),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Text(
                _textController.text,
                style: TextStyle(
                  fontFamily: _selectedFont.fontFamily,
                  fontWeight: _selectedFont.weight,
                  fontStyle: _selectedFont.style,
                  fontSize: 18,
                  height: 1.8,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(height: 32),
          ],

          // Submit Button
          CustomButton(
            label: 'Generate trajectory',
            onPressed: _handleSubmit,
            isLoading: _isSubmitting,
            icon: Icons.auto_fix_high_rounded,
          ),
        ],
      ),
    );
  }
}
