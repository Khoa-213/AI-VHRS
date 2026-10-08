import 'package:flutter/material.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../input_handwriting/presentation/widgets/new_request_sheet.dart';

class _Idea {
  final String occasion;
  final String sample;
  final String meta;

  const _Idea(this.occasion, this.sample, this.meta);
}

const _ideas = [
  _Idea(
    'thank-you notes.',
    'Cảm ơn cô đã dạy con biết yêu con chữ.',
    'Card 90 × 55 • Gel pen',
  ),
  _Idea(
    'letters home.',
    'Mẹ ơi, Sài Gòn mấy hôm nay mưa suốt, con vẫn khỏe.',
    'A5 ivory • Fountain pen',
  ),
  _Idea(
    'signatures.',
    'Nguyễn Thị Minh Thư',
    'Card • Brush pen',
  ),
  _Idea(
    'poetry.',
    'Trăm năm trong cõi người ta,\nchữ tài chữ mệnh khéo là ghét nhau.',
    'A4 • Fountain pen',
  ),
];

/// "Inspirations" — occasions people use the robot for, each with a sample
/// line. Tapping one starts a new request.
class GalleryScreen extends StatelessWidget {
  const GalleryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
          children: [
            Text('get inspired.', style: theme.textTheme.displayMedium),
            const SizedBox(height: 8),
            Text(
              'What people ask the robot to write, in their own words.',
              style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.textSecondary),
            ),
            const SizedBox(height: 28),
            _FeaturedCard(onTap: () => showNewRequestSheet(context)),
            const SizedBox(height: 14),
            for (final idea in _ideas) ...[
              _IdeaCard(idea: idea, onTap: () => showNewRequestSheet(context)),
              const SizedBox(height: 14),
            ],
          ],
        ),
      ),
    );
  }
}

class _FeaturedCard extends StatelessWidget {
  final VoidCallback onTap;
  const _FeaturedCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      pressedScale: 0.98,
      semanticLabel: 'Wedding invitations',
      child: Container(
        height: 200,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: AppColors.ink,
          borderRadius: BorderRadius.circular(28),
        ),
        child: Stack(
          children: [
            Positioned.fill(
              child: InkFlourish(color: AppColors.onInk.withValues(alpha: 0.07)),
            ),
            const Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'This season',
                    style: TextStyle(fontSize: 13, color: AppColors.onInkMuted),
                  ),
                  SizedBox(height: 6),
                  Text(
                    'wedding invitations,\nwritten one by one.',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -0.5,
                      height: 1.25,
                      color: AppColors.onInk,
                    ),
                  ),
                  Spacer(),
                  Text(
                    '120 cards take the robot about 3 hours.',
                    style: TextStyle(fontSize: 13, color: AppColors.onInkMuted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _IdeaCard extends StatelessWidget {
  final _Idea idea;
  final VoidCallback onTap;

  const _IdeaCard({required this.idea, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Pressable(
      onTap: onTap,
      pressedScale: 0.98,
      semanticLabel: idea.occasion,
      child: Container(
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 22),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(idea.occasion, style: theme.textTheme.headlineSmall)),
                const Icon(Icons.north_east_rounded, size: 18, color: AppColors.textTertiary),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              idea.sample,
              style: const TextStyle(
                fontSize: 17,
                fontStyle: FontStyle.italic,
                height: 1.55,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 14),
            Text(idea.meta, style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textTertiary)),
          ],
        ),
      ),
    );
  }
}
