import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:webview_flutter/webview_flutter.dart' as wv;
import 'package:webview_windows/webview_windows.dart' as win;

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/providers.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// Builds the view of a backend page. A native web view on a device; replaced in widget tests,
/// where no platform view exists.
final robotWebViewProvider = Provider<Widget Function(String url)>(
  (ref) => (url) => Platform.isWindows ? _WindowsView(url: url) : _NativeView(url: url),
);

class _NativeView extends StatefulWidget {
  final String url;
  const _NativeView({required this.url});

  @override
  State<_NativeView> createState() => _NativeViewState();
}

class _NativeViewState extends State<_NativeView> {
  late final _controller = wv.WebViewController()
    ..setJavaScriptMode(wv.JavaScriptMode.unrestricted)
    ..loadRequest(Uri.parse(widget.url));

  @override
  void didUpdateWidget(_NativeView old) {
    super.didUpdateWidget(old);
    if (old.url != widget.url) _controller.loadRequest(Uri.parse(widget.url));
  }

  @override
  Widget build(BuildContext context) => wv.WebViewWidget(controller: _controller);
}

class _WindowsView extends StatefulWidget {
  final String url;
  const _WindowsView({required this.url});

  @override
  State<_WindowsView> createState() => _WindowsViewState();
}

class _WindowsViewState extends State<_WindowsView> {
  final _controller = win.WebviewController();
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    await _controller.initialize();
    await _controller.loadUrl(widget.url);
    if (mounted) setState(() => _ready = true);
  }

  @override
  void didUpdateWidget(_WindowsView old) {
    super.didUpdateWidget(old);
    if (_ready && old.url != widget.url) _controller.loadUrl(widget.url);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      _ready ? win.Webview(_controller) : const Center(child: CircularProgressIndicator(strokeWidth: 2));
}

/// The robot's live 3D view: the backend's read-only page, opened with a view ticket. A new ticket
/// is asked for a minute before the old one ends, so the frame never goes blank (FE `RobotView3D`).
class RobotView3D extends ConsumerStatefulWidget {
  final int robotId;
  final String robotCode;
  final double height;

  /// The strip under the view: progress of the run.
  final Widget footer;
  const RobotView3D({super.key, required this.robotId, required this.robotCode, required this.height, required this.footer});

  @override
  ConsumerState<RobotView3D> createState() => _RobotView3DState();
}

class _RobotView3DState extends ConsumerState<RobotView3D> {
  ViewTicket? _view;
  Object? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _open();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _open() async {
    _timer?.cancel();
    try {
      final v = await ref.read(robotApiProvider).viewTicket(widget.robotId);
      if (!mounted) return;
      setState(() {
        _view = v;
        _error = null;
      });
      final seconds = v.expiresIn - 60;
      _timer = Timer(Duration(seconds: seconds < 60 ? 60 : seconds), _open);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final view = _view;
    final err = _error;
    final Widget content;
    if (view != null) {
      content = ref.watch(robotWebViewProvider)(view.url);
    } else if (err != null) {
      content = Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(techErrorText(t, err), textAlign: TextAlign.center, style: const TextStyle(fontSize: 14, color: AppColors.onInk)),
              const SizedBox(height: 12),
              TechButton(t('td.api.reload'), small: true, style: CustomButtonStyle.inverted, onPressed: _open),
            ],
          ),
        ),
      );
    } else {
      content = Center(child: Text(t('co.loading'), style: const TextStyle(fontSize: 14, color: AppColors.onInkMuted)));
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(TechRadius.card),
      child: ColoredBox(
        color: const Color(0xFF0E0E10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: widget.height,
              child: Semantics(label: '${t('rb.view3d')}, ${widget.robotCode}', child: content),
            ),
            widget.footer,
          ],
        ),
      ),
    );
  }
}
