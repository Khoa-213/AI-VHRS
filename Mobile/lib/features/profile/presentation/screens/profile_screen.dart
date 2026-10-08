import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';

/// Profile tab: who is signed in, account links, and sign out.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final auth = ref.watch(authNotifierProvider);
    final name = auth is AuthAuthenticated ? auth.fullName : '';
    final email = auth is AuthAuthenticated ? auth.email : '';
    final initial = name.trim().isEmpty ? '·' : name.trim()[0].toUpperCase();

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
          children: [
            Text('profile.', style: theme.textTheme.displayMedium),
            const SizedBox(height: 28),
            Row(
              children: [
                Container(
                  width: 64,
                  height: 64,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppColors.ink,
                    borderRadius: BorderRadius.circular(22),
                  ),
                  child: Text(
                    initial,
                    style: const TextStyle(
                      color: AppColors.onInk,
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name, style: theme.textTheme.headlineSmall),
                      const SizedBox(height: 2),
                      Text(email, style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            _Group(
              children: [
                _Row(
                  icon: Icons.receipt_long_outlined,
                  label: 'Order history',
                  onTap: () => context.go('/tracking'),
                ),
                const _Row(icon: Icons.local_shipping_outlined, label: 'Delivery addresses', trailing: 'Soon'),
                const _Row(icon: Icons.translate_rounded, label: 'Language', trailing: 'English'),
              ],
            ),
            const SizedBox(height: 14),
            const _Group(
              children: [
                _Row(icon: Icons.help_outline_rounded, label: 'Help & support', trailing: 'Soon'),
                _Row(icon: Icons.description_outlined, label: 'Terms & privacy', trailing: 'Soon'),
              ],
            ),
            const SizedBox(height: 32),
            Center(
              child: CustomButton(
                label: 'Sign out',
                style: CustomButtonStyle.outline,
                isExpanded: false,
                height: 46,
                onPressed: () => ref.read(authNotifierProvider.notifier).logout(),
              ),
            ),
            const SizedBox(height: 20),
            Center(
              child: Text(
                '${AppConstants.appName} ${AppConstants.appVersion}',
                style: theme.textTheme.bodySmall?.copyWith(color: AppColors.textTertiary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Group extends StatelessWidget {
  final List<Widget> children;
  const _Group({required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          for (var i = 0; i < children.length; i++) ...[
            children[i],
            if (i < children.length - 1) const Divider(indent: 56, endIndent: 20),
          ],
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? trailing;
  final VoidCallback? onTap;

  const _Row({required this.icon, required this.label, this.trailing, this.onTap});

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 17),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppColors.textPrimary),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
            ),
          ),
          if (trailing != null)
            Text(trailing!, style: const TextStyle(fontSize: 13, color: AppColors.textTertiary)),
          if (onTap != null)
            const Icon(Icons.chevron_right_rounded, size: 20, color: AppColors.textTertiary),
        ],
      ),
    );

    // Rows without a destination yet are shown but not tappable.
    return onTap == null ? content : Pressable(onTap: onTap, pressedScale: 0.985, child: content);
  }
}
