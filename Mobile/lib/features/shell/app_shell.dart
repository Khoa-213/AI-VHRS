import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/constants/app_colors.dart';
import '../../core/widgets/pressable.dart';
import '../input_handwriting/presentation/widgets/new_request_sheet.dart';

/// Root scaffold for the four top-level tabs, with a bottom bar that carries
/// a centered ink "+" button for starting a new writing request.
class AppShell extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const AppShell({super.key, required this.navigationShell});

  static const _tabs = [
    _TabSpec('Today', Icons.edit_note_outlined, Icons.edit_note_rounded),
    _TabSpec('Inspirations', Icons.lightbulb_outline_rounded, Icons.lightbulb_rounded),
    _TabSpec('Orders', Icons.explore_outlined, Icons.explore_rounded),
    _TabSpec('Profile', Icons.menu_book_outlined, Icons.menu_book_rounded),
  ];

  void _goBranch(int index) {
    navigationShell.goBranch(
      index,
      // Tapping the active tab returns it to its first screen.
      initialLocation: index == navigationShell.currentIndex,
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: AppColors.background,
          border: Border(top: BorderSide(color: AppColors.divider)),
        ),
        padding: EdgeInsets.fromLTRB(8, 10, 8, bottomInset > 0 ? bottomInset : 12),
        child: Row(
          children: [
            _item(0),
            _item(1),
            Expanded(
              child: Center(
                heightFactor: 1,
                child: Pressable(
                  onTap: () => showNewRequestSheet(context),
                  pressedScale: 0.92,
                  semanticLabel: 'New writing request',
                  child: Container(
                    width: 56,
                    height: 56,
                    decoration: const BoxDecoration(
                      color: AppColors.ink,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Color(0x1F121212),
                          blurRadius: 16,
                          offset: Offset(0, 6),
                        ),
                      ],
                    ),
                    child: const Icon(Icons.add_rounded, color: AppColors.onInk, size: 28),
                  ),
                ),
              ),
            ),
            _item(2),
            _item(3),
          ],
        ),
      ),
    );
  }

  Widget _item(int index) {
    final tab = _tabs[index];
    final selected = navigationShell.currentIndex == index;
    final color = selected ? AppColors.textPrimary : AppColors.textTertiary;

    return Expanded(
      child: Pressable(
        onTap: () => _goBranch(index),
        semanticLabel: tab.label,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 180),
              child: Icon(
                selected ? tab.activeIcon : tab.icon,
                key: ValueKey(selected),
                color: color,
                size: 24,
              ),
            ),
            const SizedBox(height: 4),
            AnimatedDefaultTextStyle(
              duration: const Duration(milliseconds: 180),
              style: TextStyle(
                fontFamily: 'BeVietnamPro',
                fontSize: 11,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                color: color,
              ),
              child: Text(tab.label, maxLines: 1, overflow: TextOverflow.fade, softWrap: false),
            ),
          ],
        ),
      ),
    );
  }
}

class _TabSpec {
  final String label;
  final IconData icon;
  final IconData activeIcon;
  const _TabSpec(this.label, this.icon, this.activeIcon);
}
