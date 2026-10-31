import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../i18n/tech_strings.dart';

/// Desktop building blocks in the mobile app's ink-on-paper language:
/// white 28px cards on paper, pill chips and buttons, ink for emphasis.

const _tabular = [FontFeature.tabularFigures()];

/// Corner radii for the desktop. Tighter than the mobile tokens (28/16/pill):
/// on a large screen soft pills read as toy-like.
class TechRadius {
  TechRadius._();
  static const double card = 12;
  static const double inner = 8;
  static const double control = 8;
}

/// Below this window width the app uses its phone layout: one column, tabs at the bottom.
const double compactWidth = 700;

bool isCompact(BuildContext context) => MediaQuery.sizeOf(context).width < compactWidth;

class TechCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;
  const TechCard({super.key, required this.child, this.padding = const EdgeInsets.all(24), this.color});

  @override
  Widget build(BuildContext context) => Container(
    padding: padding,
    decoration: BoxDecoration(
      color: color ?? AppColors.surface,
      borderRadius: BorderRadius.circular(TechRadius.card),
      border: color == null ? Border.all(color: AppColors.border) : null,
    ),
    child: child,
  );
}

/// Card title with an optional quiet tag on the right.
class CardHead extends StatelessWidget {
  final String title;
  final String? tag;
  const CardHead(this.title, {super.key, this.tag});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: Row(
      children: [
        Expanded(child: Text(title, style: Theme.of(context).textTheme.headlineSmall)),
        if (tag != null) TagText(tag!),
      ],
    ),
  );
}

class TagText extends StatelessWidget {
  final String text;
  const TagText(this.text, {super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(color: AppColors.surfaceVariant, borderRadius: BorderRadius.circular(TechRadius.control)),
    child: Text(
      text,
      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
    ),
  );
}

/// Pill with a coloured dot and text, used for phases and statuses.
class StatusPill extends StatelessWidget {
  final String label;
  final Color color;
  const StatusPill(this.label, this.color, {super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(TechRadius.control)),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color),
          ),
        ),
      ],
    ),
  );
}

/// Small grey label above a number or value.
class Label extends StatelessWidget {
  final String text;
  const Label(this.text, {super.key});

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
  );
}

class MonoText extends StatelessWidget {
  final String text;
  final double size;
  final FontWeight weight;
  final Color color;
  const MonoText(this.text, {super.key, this.size = 14, this.weight = FontWeight.w600, this.color = AppColors.textPrimary});

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: TextStyle(fontSize: size, fontWeight: weight, color: color, fontFeatures: _tabular, letterSpacing: -0.2),
  );
}

/// KPI tile. The accent tile is ink with white text, like the mobile hero card.
class KpiTile extends StatelessWidget {
  final String label;
  final String value;
  final String hint;
  final bool accent;

  /// Phone width: smaller, and the hint is left out.
  final bool dense;
  final VoidCallback? onTap;
  const KpiTile({super.key, required this.label, required this.value, required this.hint, this.accent = false, this.dense = false, this.onTap});

  @override
  Widget build(BuildContext context) {
    final fg = accent ? AppColors.onInk : AppColors.textPrimary;
    final sub = accent ? AppColors.onInkMuted : AppColors.textSecondary;
    final tile = TechCard(
      color: accent ? AppColors.ink : null,
      padding: dense ? const EdgeInsets.all(14) : const EdgeInsets.fromLTRB(20, 18, 20, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(fontSize: dense ? 12 : 13, fontWeight: FontWeight.w500, color: sub),
            maxLines: dense ? 3 : 2,
          ),
          SizedBox(height: dense ? 4 : 8),
          MonoText(value, size: dense ? 26 : 32, color: fg),
          if (!dense) ...[
            const SizedBox(height: 4),
            Text(
              hint,
              style: TextStyle(fontSize: 12, color: sub),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
    if (onTap == null) return tile;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: Pressable(onTap: onTap, semanticLabel: '$label: $value', child: tile),
    );
  }
}

/// Thin pill progress bar.
class Meter extends StatelessWidget {
  final double value;
  final Color color;
  final double height;
  final String? semanticLabel;
  const Meter(this.value, {super.key, this.color = AppColors.ink, this.height = 6, this.semanticLabel});

  @override
  Widget build(BuildContext context) => Semantics(
    label: semanticLabel,
    value: '${(value * 100).round()}%',
    child: ClipRRect(
      borderRadius: BorderRadius.circular(height),
      child: SizedBox(
        height: height,
        child: Stack(
          children: [
            Container(color: AppColors.surfaceVariant),
            FractionallySizedBox(
              widthFactor: value.clamp(0.0, 1.0),
              child: Container(color: color),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Pill button in the mobile `CustomButton` styles, with a disabled look, a
/// pointer cursor, and a label that wraps instead of overflowing (Vietnamese
/// and Japanese labels run longer than English).
class TechButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final CustomButtonStyle style;
  final IconData? icon;
  final bool small;
  final bool expand;
  const TechButton(
    this.label, {
    super.key,
    this.onPressed,
    this.style = CustomButtonStyle.primary,
    this.icon,
    this.small = false,
    this.expand = false,
  });

  @override
  Widget build(BuildContext context) {
    final (bg, fg, border) = switch (style) {
      CustomButtonStyle.primary => (AppColors.ink, AppColors.onInk, null),
      CustomButtonStyle.secondary => (AppColors.secondary, AppColors.onInk, null),
      CustomButtonStyle.outline => (AppColors.surface, AppColors.textPrimary, AppColors.border),
      CustomButtonStyle.text => (Colors.transparent, AppColors.textPrimary, null),
      CustomButtonStyle.inverted => (AppColors.onInk, AppColors.ink, null),
    };
    final text = Text(
      label,
      textAlign: TextAlign.center,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: small ? 13 : 15, fontWeight: FontWeight.w600, letterSpacing: -0.1, color: fg, height: 1.25),
    );
    return MouseRegion(
      cursor: onPressed == null ? SystemMouseCursors.forbidden : SystemMouseCursors.click,
      // Pressable fades itself when disabled.
      child: Pressable(
        onTap: onPressed,
        semanticLabel: label,
        child: Container(
          constraints: BoxConstraints(minHeight: small ? 40 : 50),
          width: expand ? double.infinity : null,
          padding: EdgeInsets.symmetric(horizontal: small ? 18 : 26, vertical: 8),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(TechRadius.control),
            border: border == null ? null : Border.all(color: border, width: 1.2),
          ),
          child: Row(
            mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (icon != null) ...[Icon(icon, size: 18, color: fg), const SizedBox(width: 8)],
              Flexible(child: text),
            ],
          ),
        ),
      ),
    );
  }
}

/// Language switch, the desktop twin of the FE `LanguageToggle`.
class LanguageToggle extends ConsumerWidget {
  const LanguageToggle({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(langProvider);
    final t = ref.watch(tProvider);
    return PopupMenuButton<Lang>(
      tooltip: t('lang.label'),
      initialValue: lang,
      onSelected: (l) => ref.read(langProvider.notifier).set(l),
      color: AppColors.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.inner)),
      itemBuilder: (_) => [
        for (final l in Lang.values)
          PopupMenuItem(
            value: l,
            child: Row(
              children: [
                SizedBox(width: 28, child: MonoText(l.code, size: 12, color: AppColors.textSecondary)),
                Text(l.label, style: TextStyle(fontWeight: l == lang ? FontWeight.w600 : FontWeight.w400)),
              ],
            ),
          ),
      ],
      child: Container(
        height: 40,
        padding: const EdgeInsets.symmetric(horizontal: 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(TechRadius.control),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.translate_rounded, size: 16, color: AppColors.textSecondary),
            const SizedBox(width: 8),
            MonoText(lang.code, size: 13),
          ],
        ),
      ),
    );
  }
}

/// Centred confirm dialog: ink mark, title, body, facts and two actions.
Future<bool> showConfirm(
  BuildContext context, {
  required String title,
  required String body,
  required String confirm,
  required String cancel,
  List<(String, String)> facts = const [],
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(TechRadius.card)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(4)),
              ),
              const SizedBox(height: 20),
              Text(title, style: Theme.of(ctx).textTheme.headlineMedium),
              const SizedBox(height: 10),
              Text(body, style: const TextStyle(fontSize: 14, height: 1.5, color: AppColors.textSecondary)),
              if (facts.isNotEmpty) ...[
                const SizedBox(height: 20),
                for (final (k, v) in facts)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      children: [
                        Expanded(child: Label(k)),
                        MonoText(v),
                      ],
                    ),
                  ),
              ],
              const SizedBox(height: 28),
              Row(
                children: [
                  TechButton(confirm, onPressed: () => Navigator.of(ctx).pop(true)),
                  const SizedBox(width: 12),
                  TechButton(cancel, style: CustomButtonStyle.text, small: true, onPressed: () => Navigator.of(ctx).pop(false)),
                ],
              ),
            ],
          ),
        ),
      ),
    ),
  );
  return ok ?? false;
}

/// Empty or blocked state inside a card.
class EmptyCard extends StatelessWidget {
  final String title;
  final String body;
  final List<Widget> actions;
  const EmptyCard({super.key, required this.title, required this.body, this.actions = const []});

  @override
  Widget build(BuildContext context) => TechCard(
    padding: const EdgeInsets.all(32),
    child: Row(
      children: [
        const QuillPaperArt(size: 72),
        const SizedBox(width: 28),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 6),
              Text(body, style: const TextStyle(fontSize: 14, height: 1.5, color: AppColors.textSecondary)),
              if (actions.isNotEmpty) ...[const SizedBox(height: 18), Wrap(spacing: 12, runSpacing: 12, children: actions)],
            ],
          ),
        ),
      ],
    ),
  );
}

/// Key/value rows, used for order options and the QC reference.
class FactList extends StatelessWidget {
  final List<(String, Widget)> rows;
  const FactList(this.rows, {super.key});

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final (k, v) in rows)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: AppColors.divider)),
          ),
          child: Row(
            children: [
              Expanded(child: Label(k)),
              Flexible(
                child: Align(alignment: Alignment.centerRight, child: v),
              ),
            ],
          ),
        ),
    ],
  );
}

Text valueText(String s) => Text(
  s,
  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
  textAlign: TextAlign.right,
  overflow: TextOverflow.ellipsis,
);
