import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../domain/input_mode.dart';
import 'image_upload_tab.dart';
import 'text_font_tab.dart';
import 'canvas_draw_tab.dart';

/// Tabbed input selection screen offering three handwriting input methods:
/// 1. Image Upload — photo + crop + contrast slider
/// 2. Text + Font — text input with font style selection
/// 3. Canvas Draw — interactive drawing canvas
class InputSelectionScreen extends ConsumerStatefulWidget {
  final String projectId;
  final InputMode? initialMode;

  const InputSelectionScreen({super.key, required this.projectId, this.initialMode});

  @override
  ConsumerState<InputSelectionScreen> createState() => _InputSelectionScreenState();
}

class _InputSelectionScreenState extends ConsumerState<InputSelectionScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(
      length: InputMode.values.length,
      vsync: this,
      initialIndex: widget.initialMode?.index ?? 0,
    );
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
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
                    onPressed: () => context.canPop() ? context.pop() : context.go('/projects'),
                    icon: const Icon(Icons.chevron_left_rounded, size: 28),
                  ),
                  const Expanded(child: Center(child: StepDashes(total: 4, current: 1))),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => context.go('/projects'),
                    icon: const Icon(Icons.close_rounded, size: 22),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 12, 24, 20),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('give the robot\nyour words.', style: theme.textTheme.displayMedium),
              ),
            ),
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 20),
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: AppColors.border),
              ),
              child: TabBar(
                controller: _tabController,
                labelColor: AppColors.onInk,
                unselectedLabelColor: AppColors.textSecondary,
                indicatorSize: TabBarIndicatorSize.tab,
                dividerColor: Colors.transparent,
                splashFactory: NoSplash.splashFactory,
                overlayColor: WidgetStateProperty.all(Colors.transparent),
                indicator: BoxDecoration(
                  color: AppColors.ink,
                  borderRadius: BorderRadius.circular(999),
                ),
                labelStyle: const TextStyle(
                  fontFamily: 'BeVietnamPro',
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
                unselectedLabelStyle: const TextStyle(
                  fontFamily: 'BeVietnamPro',
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
                tabs: const [
                  Tab(height: 40, text: 'Photo'),
                  Tab(height: 40, text: 'Text'),
                  Tab(height: 40, text: 'Draw'),
                ],
              ),
            ),
            const SizedBox(height: 8),
            // Tab Content
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  ImageUploadTab(projectId: widget.projectId),
                  TextFontTab(projectId: widget.projectId),
                  CanvasDrawTab(projectId: widget.projectId),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
