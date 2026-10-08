import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../constants/app_colors.dart';

/// A standardized screen wrapper that provides:
/// - SafeArea with configurable edges
/// - Custom app bar with consistent styling
/// - Status bar color management
/// - Optional floating action button
/// - Optional bottom navigation padding
class BaseScreen extends StatelessWidget {
  final String? title;
  final Widget body;
  final List<Widget>? actions;
  final Widget? floatingActionButton;
  final Widget? bottomNavigationBar;
  final Widget? drawer;
  final bool showBackButton;
  final bool useSafeArea;
  final bool extendBodyBehindAppBar;
  final bool resizeToAvoidBottomInset;
  final Color? backgroundColor;
  final PreferredSizeWidget? customAppBar;
  final VoidCallback? onBackPressed;
  final EdgeInsetsGeometry? padding;
  final Widget? leading;

  const BaseScreen({
    super.key,
    this.title,
    required this.body,
    this.actions,
    this.floatingActionButton,
    this.bottomNavigationBar,
    this.drawer,
    this.showBackButton = true,
    this.useSafeArea = true,
    this.extendBodyBehindAppBar = false,
    this.resizeToAvoidBottomInset = true,
    this.backgroundColor,
    this.customAppBar,
    this.onBackPressed,
    this.padding,
    this.leading,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    // Configure status bar style based on theme
    SystemChrome.setSystemUIOverlayStyle(
      isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
    );

    Widget content = body;

    if (padding != null) {
      content = Padding(padding: padding!, child: content);
    }

    if (useSafeArea) {
      content = SafeArea(
        top: customAppBar == null && title == null,
        child: content,
      );
    }

    return Scaffold(
      backgroundColor: backgroundColor ?? theme.scaffoldBackgroundColor,
      extendBodyBehindAppBar: extendBodyBehindAppBar,
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
      appBar: customAppBar ?? _buildAppBar(context),
      body: content,
      floatingActionButton: floatingActionButton,
      bottomNavigationBar: bottomNavigationBar,
      drawer: drawer,
    );
  }

  PreferredSizeWidget? _buildAppBar(BuildContext context) {
    if (title == null && !showBackButton && actions == null) return null;

    return AppBar(
      title: title != null ? Text(title!) : null,
      leading: leading ??
          (showBackButton && Navigator.of(context).canPop()
              ? IconButton(
                  icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
                  onPressed: onBackPressed ?? () => Navigator.of(context).pop(),
                )
              : null),
      actions: actions,
      automaticallyImplyLeading: showBackButton,
    );
  }
}
