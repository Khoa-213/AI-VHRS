import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/agent_process.dart';
import '../../i18n/tech_strings.dart';
import 'job_widgets.dart';
import 'tech_ui.dart';

/// The REAL switch of a job, on its REAL step (owner 2026-11-26): a button in the app instead of the agent's web screen.
/// It calls the agent on THIS computer only (127.0.0.1), never the backend, so REAL still can only be switched on at the
/// workstation wired to the robot. The agent first checks the real robot read-only and refuses when it does not answer
/// (ROBOT_UNREACHABLE) or answers with another setup (ROBOT_CONFIG_MISMATCH). Elsewhere (no agent here, or the job's robot
/// is driven by another workstation) [fallback] shows the command to run there.
class RealSwitch extends ConsumerStatefulWidget {
  final int jobId;
  final int? robotId;
  final Widget fallback;
  const RealSwitch({super.key, required this.jobId, required this.robotId, required this.fallback});

  @override
  ConsumerState<RealSwitch> createState() => _RealSwitchState();
}

class _RealSwitchState extends ConsumerState<RealSwitch> {
  Map<String, dynamic>? _real;
  bool _busy = false;
  String? _msg;
  bool _msgBad = false;
  Timer? _timer;
  AgentLocalApi? _api;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _watch(AgentLocalApi? api) {
    if (identical(api, _api)) return;
    _api = api;
    _timer?.cancel();
    _real = null;
    if (api == null) return;
    unawaited(_refresh());
    _timer = Timer.periodic(const Duration(seconds: 20), (_) => _refresh()); // the switch expires on its own
  }

  Future<void> _refresh() async {
    final api = _api;
    if (api == null) return;
    try {
      final r = await api.realState();
      if (mounted && identical(api, _api)) setState(() => _real = r);
    } catch (_) {}
  }

  String _error(T t, AgentApiError e) => switch (e.code) {
    'ROBOT_UNREACHABLE' => '${t('dk.real.err.unreachable')} ${e.message}',
    'ROBOT_CONFIG_MISMATCH' => e.message,
    'JOB_NOT_LOADED' => t('dk.real.err.notLoaded'),
    'AGENT_BUSY' => t('dk.real.err.busy'),
    'MODE_DISABLED' => t('dk.real.err.mode'),
    'AGENT_UNREACHABLE' => t('dk.real.err.agent'),
    _ => '${e.code}: ${e.message}',
  };

  Future<void> _on(AgentLocalApi api) async {
    final t = ref.read(tProvider);
    var waive = false;
    // null = cancelled; otherwise whether the pen-up dry run is skipped (owner 2026-11-27: the dry run may be skipped here)
    final choice = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(t('dk.real.confirmTitle', {'id': widget.jobId})),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t('dk.real.confirmBody')),
              const SizedBox(height: 8),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                value: waive,
                onChanged: (v) => setLocal(() => waive = v ?? false),
                title: Text(t('dk.real.waive')),
              ),
              if (waive)
                Text(t('dk.real.waiveWarn'), style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.error)),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: Text(t('dk.real.cancel'))),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppColors.error),
              onPressed: () => Navigator.pop(ctx, waive),
              child: Text(t('dk.real.on')),
            ),
          ],
        ),
      ),
    );
    if (choice == null || !mounted) return;
    setState(() {
      _busy = true;
      _msg = t('dk.real.checking');
      _msgBad = false;
    });
    try {
      final r = await api.realEnable(widget.jobId, waiveDryRun: choice);
      final ctl = (r['robot_check'] as Map?)?['controller'];
      final version = ctl is Map ? '${ctl['controller'] ?? ctl['version'] ?? ''}' : '';
      if (!mounted) return;
      setState(() {
        _real = r['real_enabled'] as Map<String, dynamic>?;
        _msg = t('dk.real.ok', {'v': version.isEmpty ? '—' : version});
      });
    } on AgentApiError catch (e) {
      if (mounted)
        setState(() {
          _msg = _error(t, e);
          _msgBad = true;
        });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _off(AgentLocalApi api) async {
    final t = ref.read(tProvider);
    setState(() => _busy = true);
    try {
      await api.realDisable();
      if (mounted)
        setState(() {
          _real = null;
          _msg = t('dk.real.offDone');
          _msgBad = false;
        });
    } on AgentApiError catch (e) {
      if (mounted)
        setState(() {
          _msg = _error(t, e);
          _msgBad = true;
        });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final info = ref.watch(agentControllerProvider.select((a) => a.info));
    final api = ref.watch(agentLocalApiProvider);
    final here =
        api != null && info != null && info.modes.contains('real') && widget.robotId != null && info.robotId == widget.robotId;
    _watch(here ? api : null);
    if (!here) return widget.fallback;

    final real = _real;
    final mine = real != null && real['job_id'] == widget.jobId;
    final until = real == null
        ? ''
        : DateFormat(
            'HH:mm',
            t.locale,
          ).format(workshopTime(DateTime.fromMillisecondsSinceEpoch(((real['expires_at'] as num) * 1000).round())));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (real != null) ...[
          StatusPill(
            mine ? t('dk.real.onUntil', {'time': until}) : t('dk.real.onOther', {'id': real['job_id'], 'time': until}),
            AppColors.error,
          ),
          if (mine && real['waive_dry_run'] == true) ...[
            const SizedBox(height: 6),
            StatusPill(t('dk.real.waived'), AppColors.error),
          ],
          const SizedBox(height: 8),
        ],
        Wrap(
          spacing: 10,
          runSpacing: 8,
          children: [
            if (!mine)
              TechButton(t('dk.real.on'), icon: Icons.bolt_rounded, small: true, onPressed: _busy ? null : () => _on(api)),
            if (real != null)
              TechButton(
                t('dk.real.off'),
                icon: Icons.power_settings_new_rounded,
                small: true,
                style: CustomButtonStyle.outline,
                onPressed: _busy ? null : () => _off(api),
              ),
          ],
        ),
        if (_msg != null) ...[
          const SizedBox(height: 6),
          Text(_msg!, style: TextStyle(fontSize: 12, height: 1.4, color: _msgBad ? AppColors.error : AppColors.textSecondary)),
        ],
      ],
    );
  }
}
