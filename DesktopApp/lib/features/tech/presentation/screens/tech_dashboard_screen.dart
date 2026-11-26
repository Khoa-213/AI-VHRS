import 'package:flutter/material.dart';

import '../../../../core/constants/app_colors.dart';
import 'agent_screen.dart';

/// Overview: only this workstation's Robot Agent (owner 2026-11-26). No page title, counts, queue or job groups (the job
/// list and QC tabs keep the jobs): the agent's state card, then its workstation screen down to the bottom of the window,
/// with no scroll bar of its own (the screen scrolls with the wheel and keeps its STOP bar pinned at the bottom).
class TechDashboardScreen extends StatelessWidget {
  const TechDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) => const ColoredBox(
        color: AppColors.background,
        child: SafeArea(
          bottom: false,
          child: Padding(padding: EdgeInsets.fromLTRB(16, 16, 16, 0), child: AgentPanel()),
        ),
      );
}
