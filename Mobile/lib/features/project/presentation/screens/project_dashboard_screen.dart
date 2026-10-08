import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../../input_handwriting/presentation/widgets/new_request_sheet.dart';
import '../project_notifier.dart';
import '../../domain/models/project.dart';

/// "Today" — the home tab. Greeting, week strip, a dark call-to-action card,
/// the request currently on the robot's desk, and the project list.
class ProjectDashboardScreen extends ConsumerStatefulWidget {
  const ProjectDashboardScreen({super.key});

  @override
  ConsumerState<ProjectDashboardScreen> createState() => _ProjectDashboardScreenState();
}

class _ProjectDashboardScreenState extends ConsumerState<ProjectDashboardScreen> {
  static const _activeStatuses = ['writing', 'approved', 'paid', 'awaiting_payment'];

  @override
  void initState() {
    super.initState();
    // Load projects on first build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(projectListProvider.notifier).loadProjects();
    });
  }

  bool _onScroll(ScrollNotification n) {
    if (n.metrics.extentAfter < 400) {
      ref.read(projectListProvider.notifier).loadMore();
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(projectListProvider);
    final auth = ref.watch(authNotifierProvider);
    final name = auth is AuthAuthenticated ? auth.fullName : '';

    Project? active;
    for (final status in _activeStatuses) {
      active = state.projects.where((p) => p.status == status).firstOrNull;
      if (active != null) break;
    }

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          color: AppColors.ink,
          backgroundColor: AppColors.surface,
          onRefresh: () => ref.read(projectListProvider.notifier).loadProjects(),
          child: NotificationListener<ScrollNotification>(
            onNotification: _onScroll,
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
              slivers: [
                SliverToBoxAdapter(
                  child: _Header(projectCount: state.projects.length, name: name),
                ),
                const SliverToBoxAdapter(child: _WeekStrip()),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                  sliver: SliverToBoxAdapter(
                    child: _HeroCard(onBegin: () => showNewRequestSheet(context)),
                  ),
                ),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(36, 24, 36, 0),
                  sliver: SliverToBoxAdapter(
                    child: state.isLoading && state.projects.isEmpty
                        ? const _SkeletonBox(height: 188, radius: 28)
                        : _ActiveRequestCard(project: active),
                  ),
                ),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(24, 40, 24, 14),
                  sliver: SliverToBoxAdapter(
                    child: Text(
                      'YOUR PROJECTS',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.6,
                      ),
                    ),
                  ),
                ),
                ..._buildProjects(state),
                const SliverToBoxAdapter(child: SizedBox(height: 32)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _buildProjects(ProjectListState state) {
    if (state.isLoading && state.projects.isEmpty) {
      return [
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          sliver: SliverList.separated(
            itemCount: 3,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder: (_, _) => const _SkeletonBox(height: 84, radius: 24),
          ),
        ),
      ];
    }

    if (state.error != null && state.projects.isEmpty) {
      return [
        SliverToBoxAdapter(
          child: ErrorView(
            message: state.error!,
            onRetry: () => ref.read(projectListProvider.notifier).loadProjects(),
          ),
        ),
      ];
    }

    if (state.projects.isEmpty) {
      return [
        SliverToBoxAdapter(
          child: EmptyStateView(
            icon: Icons.edit_note_rounded,
            title: 'nothing written yet.',
            description: 'Your first project will live here: a letter, a card, a signature.',
            actionLabel: 'Begin project',
            onAction: () => showNewRequestSheet(context),
          ),
        ),
      ];
    }

    return [
      SliverPadding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        sliver: SliverList.separated(
          itemCount: state.projects.length + (state.isLoadingMore ? 1 : 0),
          separatorBuilder: (_, _) => const SizedBox(height: 12),
          itemBuilder: (context, index) {
            if (index >= state.projects.length) {
              return const _SkeletonBox(height: 84, radius: 24);
            }
            final project = state.projects[index];
            return _ProjectRow(
              project: project,
              onTap: () => context.push(projectDestination(project)),
            );
          },
        ),
      ),
    ];
  }
}

/// Where tapping a project should lead, based on how far along it is.
String projectDestination(Project project) {
  switch (project.status) {
    case 'awaiting_payment':
      return '/projects/${project.id}/checkout';
    case 'paid':
    case 'approved':
    case 'writing':
    case 'done':
      return '/tracking/${project.id}';
    default:
      return '/projects/${project.id}/input';
  }
}

// ─── Header ──────────────────────────────────────────────────────────

class _Header extends StatelessWidget {
  final int projectCount;
  final String name;

  const _Header({required this.projectCount, required this.name});

  String get _greeting {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'good morning.';
    if (hour < 18) return 'good afternoon.';
    return 'good evening.';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final initial = name.trim().isEmpty ? '' : name.trim()[0].toUpperCase();

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
      child: Row(
        children: [
          Semantics(
            label: '$projectCount projects',
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: AppColors.border, width: 1.2),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.draw_outlined, size: 15, color: AppColors.textTertiary),
                  const SizedBox(width: 6),
                  Text(
                    '$projectCount',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: AppColors.textTertiary,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: Text(
              _greeting,
              textAlign: TextAlign.center,
              style: theme.textTheme.headlineLarge,
            ),
          ),
          Pressable(
            onTap: () => context.go('/profile'),
            semanticLabel: 'Profile',
            child: Container(
              width: 40,
              height: 40,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: AppColors.ink,
                borderRadius: BorderRadius.circular(14),
              ),
              child: initial.isEmpty
                  ? const Icon(Icons.person_rounded, color: AppColors.onInk, size: 22)
                  : Text(
                      initial,
                      style: const TextStyle(
                        color: AppColors.onInk,
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Week strip ──────────────────────────────────────────────────────

class _WeekStrip extends StatelessWidget {
  const _WeekStrip();

  static const _labels = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

  @override
  Widget build(BuildContext context) {
    final today = DateTime.now();
    final sunday = today.subtract(Duration(days: today.weekday % 7));

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 16, 14, 0),
      child: Row(
        children: List.generate(7, (i) {
          final day = sunday.add(Duration(days: i));
          final isToday = day.day == today.day && day.month == today.month;
          final color = isToday ? AppColors.textPrimary : AppColors.textTertiary;

          return Expanded(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              margin: const EdgeInsets.symmetric(horizontal: 3),
              padding: const EdgeInsets.symmetric(vertical: 9),
              decoration: BoxDecoration(
                color: isToday ? AppColors.surface : Colors.transparent,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: isToday ? AppColors.border : Colors.transparent,
                  width: 1.2,
                ),
              ),
              child: Column(
                children: [
                  Text(
                    _labels[i],
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: isToday ? FontWeight.w600 : FontWeight.w400,
                      color: color,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${day.day}',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
                      color: color,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),
          );
        }),
      ),
    );
  }
}

// ─── Hero card ───────────────────────────────────────────────────────

class _HeroCard extends StatelessWidget {
  final VoidCallback onBegin;

  const _HeroCard({required this.onBegin});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 300,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        gradient: const RadialGradient(
          center: Alignment(-0.7, -0.9),
          radius: 1.6,
          colors: [AppColors.ink, Color(0xFF1B1B1E), Color(0xFF2B2B2F)],
          stops: [0, 0.55, 1],
        ),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: InkFlourish(color: AppColors.onInk.withValues(alpha: 0.06)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(28, 40, 28, 36),
            child: Column(
              children: [
                const Text(
                  'Robotic scribe',
                  style: TextStyle(
                    fontSize: 14,
                    color: AppColors.onInkMuted,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Ready to turn handwriting\ninto real ink?',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.4,
                    height: 1.3,
                    color: AppColors.onInk,
                  ),
                ),
                const Spacer(),
                CustomButton(
                  label: 'Begin project',
                  style: CustomButtonStyle.inverted,
                  isExpanded: false,
                  height: 52,
                  onPressed: onBegin,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Active request ──────────────────────────────────────────────────

class _ActiveRequestCard extends StatelessWidget {
  final Project? project;

  const _ActiveRequestCard({required this.project});

  static const _headlines = {
    'awaiting_payment': 'waiting on payment.',
    'paid': 'payment received.',
    'approved': 'queued for the robot.',
    'writing': 'robot is writing.',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final p = project;

    final String title;
    final String? step;
    final String body;
    final String action;
    final String route;

    if (p == null) {
      title = 'nothing on the desk.';
      step = null;
      body = 'Start a request and you can follow the robot’s progress from here.';
      action = 'Browse styles';
      route = '/gallery';
    } else {
      final stepIndex = AppConstants.statusFlow.indexOf(p.status) + 1;
      final paper = AppConstants.paperSizes
          .where((s) => s.id == p.paperSizeId)
          .map((s) => s.name)
          .firstOrNull ?? p.paperSizeId.toUpperCase();
      final pen = AppConstants.penTypes
          .where((t) => t.id == p.penTypeId)
          .map((t) => Formatters.capitalize(t.name.toLowerCase()))
          .firstOrNull ?? p.penTypeId;
      final shortId = p.id.length > 6 ? p.id.substring(0, 6).toUpperCase() : p.id.toUpperCase();

      title = _headlines[p.status] ?? '${Formatters.statusLabel(p.status).toLowerCase()}.';
      step = 'Step $stepIndex of ${AppConstants.statusFlow.length}';
      body = '${p.name}\n#VHRS-$shortId · $paper · $pen';
      action = p.status == 'awaiting_payment' ? 'Pay now' : 'View progress';
      route = projectDestination(p);
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 28),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(28),
        boxShadow: const [
          BoxShadow(color: AppColors.shadow, blurRadius: 24, offset: Offset(0, 8)),
        ],
      ),
      child: Column(
        children: [
          Text(title, style: theme.textTheme.headlineMedium, textAlign: TextAlign.center),
          if (step != null) ...[
            const SizedBox(height: 2),
            Text(step, style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textTertiary)),
          ],
          const SizedBox(height: 14),
          Text(
            body,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(height: 1.6),
          ),
          const SizedBox(height: 20),
          CustomButton(
            label: action,
            style: CustomButtonStyle.outline,
            isExpanded: false,
            height: 46,
            onPressed: () => route.startsWith('/gallery') ? context.go(route) : context.push(route),
          ),
        ],
      ),
    );
  }
}

// ─── Project row ─────────────────────────────────────────────────────

class _ProjectRow extends StatelessWidget {
  final Project project;
  final VoidCallback onTap;

  const _ProjectRow({required this.project, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Pressable(
      onTap: onTap,
      pressedScale: 0.98,
      semanticLabel: project.name,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(16),
              ),
              child: project.thumbnailUrl != null
                  ? Image.network(
                      project.thumbnailUrl!,
                      fit: BoxFit.cover,
                      semanticLabel: 'Preview of ${project.name}',
                      errorBuilder: (_, _, _) => const _ThumbFallback(),
                    )
                  : const _ThumbFallback(),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    project.name,
                    style: theme.textTheme.titleLarge,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${project.paperSizeId.toUpperCase()} • ${Formatters.timeAgo(project.createdAt)}',
                    style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textTertiary),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            StatusLabel(status: project.status),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right_rounded, color: AppColors.textTertiary, size: 20),
          ],
        ),
      ),
    );
  }
}

class _ThumbFallback extends StatelessWidget {
  const _ThumbFallback();

  @override
  Widget build(BuildContext context) {
    return const Center(child: ModeGlyph(kind: ModeGlyphKind.canvas, size: 22));
  }
}

/// Status shown as a dot + lowercase text; the dot deepens toward ink as the
/// order progresses.
class StatusLabel extends StatelessWidget {
  final String status;

  const StatusLabel({super.key, required this.status});

  Color get _color {
    switch (status) {
      case 'awaiting_payment':
        return AppColors.statusAwaitingPayment;
      case 'paid':
        return AppColors.statusPaid;
      case 'approved':
        return AppColors.statusApproved;
      case 'writing':
        return AppColors.statusWriting;
      case 'done':
        return AppColors.statusDone;
      default:
        return AppColors.textTertiary;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: _color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(
          Formatters.statusLabel(status).toLowerCase(),
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w500,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

// ─── Skeleton ────────────────────────────────────────────────────────

class _SkeletonBox extends StatelessWidget {
  final double height;
  final double radius;

  const _SkeletonBox({required this.height, required this.radius});

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: AppColors.surfaceVariant,
      highlightColor: AppColors.surface,
      child: Container(
        height: height,
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    );
  }
}
