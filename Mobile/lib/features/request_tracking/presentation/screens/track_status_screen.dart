import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/widgets.dart';

/// Status step data model.
class _StatusStep {
  final String id;
  final String label;
  final String description;
  final IconData icon;
  final Color color;

  const _StatusStep({
    required this.id,
    required this.label,
    required this.description,
    required this.icon,
    required this.color,
  });
}

const _statusSteps = [
  _StatusStep(
    id: 'awaiting_payment',
    label: 'Awaiting payment',
    description: 'Waiting for payment confirmation',
    icon: Icons.hourglass_empty_rounded,
    color: AppColors.statusAwaitingPayment,
  ),
  _StatusStep(
    id: 'paid',
    label: 'Paid',
    description: 'Payment received and verified',
    icon: Icons.payment_rounded,
    color: AppColors.statusPaid,
  ),
  _StatusStep(
    id: 'approved',
    label: 'Approved',
    description: 'Order approved and queued for writing',
    icon: Icons.check_circle_outline_rounded,
    color: AppColors.statusApproved,
  ),
  _StatusStep(
    id: 'writing',
    label: 'Writing',
    description: 'Robot is writing your content',
    icon: Icons.edit_rounded,
    color: AppColors.statusWriting,
  ),
  _StatusStep(
    id: 'done',
    label: 'Done',
    description: 'Writing complete. Your result is below.',
    icon: Icons.done_all_rounded,
    color: AppColors.statusDone,
  ),
];

/// Request tracking screen with a vertical timeline showing status progress.
class TrackStatusScreen extends ConsumerStatefulWidget {
  final String? requestId;

  const TrackStatusScreen({super.key, this.requestId});

  @override
  ConsumerState<TrackStatusScreen> createState() => _TrackStatusScreenState();
}

class _TrackStatusScreenState extends ConsumerState<TrackStatusScreen> {
  // Simulated current status — replace with actual API data
  final String _currentStatus = 'writing';
  final DateTime _lastUpdated = DateTime.now().subtract(const Duration(minutes: 15));
  final String _projectName = 'Wedding Invitation';
  final String _requestCode = 'REQ-20260927-001';

  int get _currentStepIndex =>
      _statusSteps.indexWhere((s) => s.id == _currentStatus);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // As the Orders tab root there is no back button; as a detail page
    // (opened from a project) there is.
    final isTabRoot = widget.requestId == null;

    return BaseScreen(
      title: isTabRoot ? null : '',
      showBackButton: !isTabRoot,
      body: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('track request.', style: theme.textTheme.displayMedium),
            const SizedBox(height: 24),

            // Request Info Card
            Container(
              padding: const EdgeInsets.all(22),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _projectName,
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppColors.ink,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          _statusSteps[_currentStepIndex].label,
                          style: const TextStyle(
                            color: AppColors.onInk,
                            fontWeight: FontWeight.w600,
                            fontSize: 11.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Request: $_requestCode',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                  Text(
                    'Updated ${Formatters.timeAgo(_lastUpdated)}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),

            // Timeline
            Text('timeline.', style: theme.textTheme.headlineMedium),
            const SizedBox(height: 20),

            ...List.generate(_statusSteps.length, (index) {
              final step = _statusSteps[index];
              final isCompleted = index <= _currentStepIndex;
              final isCurrent = index == _currentStepIndex;
              final isLast = index == _statusSteps.length - 1;

              return _TimelineStep(
                step: step,
                isCompleted: isCompleted,
                isCurrent: isCurrent,
                isLast: isLast,
              );
            }),
            const SizedBox(height: 32),

            // Result Section (visible when done)
            if (_currentStatus == 'done') ...[
              Text('your result.', style: theme.textTheme.headlineMedium),
              const SizedBox(height: 12),
              Container(
                height: 200,
                width: double.infinity,
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(24),
                ),
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.image_outlined,
                        size: 48,
                        color: AppColors.textTertiary,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Result image/video will appear here',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: CustomButton(
                      label: 'Download',
                      onPressed: () {},
                      icon: Icons.download_rounded,
                      style: CustomButtonStyle.outline,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: CustomButton(
                      label: 'Share',
                      onPressed: () {},
                      icon: Icons.share_rounded,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A single step in the vertical timeline.
class _TimelineStep extends StatelessWidget {
  final _StatusStep step;
  final bool isCompleted;
  final bool isCurrent;
  final bool isLast;

  const _TimelineStep({
    required this.step,
    required this.isCompleted,
    required this.isCurrent,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timeline dot & line
          SizedBox(
            width: 40,
            child: Column(
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  width: isCurrent ? 34 : 28,
                  height: isCurrent ? 34 : 28,
                  decoration: BoxDecoration(
                    color: isCompleted ? AppColors.ink : AppColors.surface,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: isCurrent
                          ? AppColors.border
                          : (isCompleted ? AppColors.ink : AppColors.border),
                      width: isCurrent ? 4 : 1.2,
                      strokeAlign: BorderSide.strokeAlignOutside,
                    ),
                  ),
                  child: isCompleted
                      ? Icon(step.icon, size: isCurrent ? 16 : 14, color: AppColors.onInk)
                      : null,
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 1.5,
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      color: isCompleted && !isCurrent ? AppColors.ink : AppColors.border,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 14),
          // Step content
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    step.label,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: isCurrent ? FontWeight.w600 : FontWeight.w500,
                      color: isCompleted ? AppColors.textPrimary : AppColors.textTertiary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    step.description,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: isCompleted ? AppColors.textSecondary : AppColors.textTertiary,
                    ),
                  ),
                  if (isCurrent) ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 7,
                            height: 7,
                            decoration: const BoxDecoration(
                              color: AppColors.ink,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            'in progress',
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
