import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../data/agent_process.dart';
import '../../data/providers.dart';
import '../../domain/robot.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/job_widgets.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// The Robot Agent of this workstation, a card on Overview under My robots (owner 2026-11-26): its state, stop / start, the
/// read-only robot connection check and its log. The agent's own web screen is no longer embedded: the app's Jobs, job page
/// and robot control do the work, and the REAL switch is a button on the job's REAL step (`RealSwitch`).
class AgentPanel extends ConsumerStatefulWidget {
  const AgentPanel({super.key});

  @override
  ConsumerState<AgentPanel> createState() => _AgentPanelState();
}

class _AgentPanelState extends ConsumerState<AgentPanel> {
  List<CheckStep>? _checks;
  bool _checking = false;
  bool _showLog = false;

  Future<void> _start() async {
    await startAgentAsSignedIn(context, ref);
    if (mounted) setState(() => _checks = null);
  }

  Future<void> _stop() async {
    final t = ref.read(tProvider);
    if (!await showConfirm(context, title: t('dk.agent.stop'), body: t('dk.agent.stopConfirm'), confirm: t('dk.agent.stop'), cancel: t('dk.confirm.cancel'))) {
      return;
    }
    await ref.read(agentControllerProvider.notifier).stop();
  }

  /// Four read-only steps; a step that cannot run because an earlier one failed is shown as skipped.
  Future<void> _check() async {
    final agent = ref.read(agentControllerProvider);
    final info = agent.info;
    final api = ref.read(robotApiProvider);
    final keys = ['dk.agent.chk.process', 'dk.agent.chk.network', 'dk.agent.chk.online', 'dk.agent.chk.identify'];
    final steps = [for (final k in keys) CheckStep(k, CheckState.waiting)];
    void put(int i, CheckState s, [String? d]) {
      steps[i] = CheckStep(keys[i], s, d);
      if (mounted) setState(() => _checks = [...steps]);
    }

    setState(() {
      _checking = true;
      _checks = [...steps];
    });
    try {
      // 1. The agent runs here and holds the robot session.
      put(0, CheckState.running);
      final running = agent.phase == AgentPhase.running && agent.linked;
      put(0, running ? CheckState.ok : CheckState.failed, running ? 'robot ${info?.robotId ?? '?'}' : null);

      // 2. The controller answers on the network (TCP to its XML-RPC port, then closed).
      put(1, CheckState.running);
      final ip = info?.robotIp;
      if (ip == null) {
        put(1, CheckState.failed, ref.read(tProvider)('dk.agent.err.noIp'));
      } else {
        final err = await probeController(ip);
        put(1, err == null ? CheckState.ok : CheckState.failed, err == null ? '$ip:20003' : '$ip: $err');
      }

      // 3. The backend sees the agent ONLINE.
      put(2, CheckState.running);
      final robotId = info?.robotId;
      RobotStatus? me;
      try {
        final mine = await api.myRobots();
        for (final r in mine.robots) {
          if (r.robotId == robotId) me = r;
        }
        put(2, me != null && me.online ? CheckState.ok : CheckState.failed,
            me == null ? ref.read(tProvider)('dk.agent.err.notMine') : '${me.robotCode} · ${me.connection}');
      } catch (e) {
        put(2, CheckState.failed, techErrorText(ref.read(tProvider), e));
      }

      // 4. IDENTIFY on the real robot through the backend: the whole path, read-only.
      if (!running || me == null || !me.online) {
        put(3, CheckState.skipped);
      } else {
        put(3, CheckState.running);
        try {
          var cmd = await api.sendCommand(CommandKind.identify, robotId: robotId, params: const {'mode': 'REAL'});
          cmd = await api.waitCommand(cmd);
          if (cmd.status == CommandStatus.done) {
            final info = (cmd.result?['info'] as Map?) ?? const {};
            final tcp = cmd.result?['tcp_mm'];
            put(3, CheckState.ok, [
              if (info['model'] != null) '${info['model']}',
              if (info['controller_version'] != null) 'controller ${info['controller_version']}',
              if (info['sdk_version'] != null) '${info['sdk_version']}',
              if (tcp != null) 'TCP $tcp mm',
            ].join(' · '));
          } else if (cmd.errorCode == 'ROBOT_CONFIG_MISMATCH') {
            // The robot answered: the network is fine, the setup on the robot or in agent.json differs (tool slot, work object...).
            put(3, CheckState.failed, '${ref.read(tProvider)('dk.agent.chk.config')} ${cmd.errorMessage ?? ''}');
          } else {
            put(3, CheckState.failed, '${cmd.errorCode ?? cmd.status.name}: ${cmd.errorMessage ?? ''}');
          }
        } catch (e) {
          put(3, CheckState.failed, techErrorText(ref.read(tProvider), e));
        }
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final agent = ref.watch(agentControllerProvider);
    final info = agent.info;
    final (label, color) = switch (agent.phase) {
      AgentPhase.notFound => (t('dk.agent.phase.notFound'), AppColors.error),
      AgentPhase.stopped => (t('dk.agent.phase.stopped'), AppColors.info),
      AgentPhase.starting => (t('dk.agent.phase.starting'), AppColors.warning),
      AgentPhase.running => (t('dk.agent.phase.running'), AppColors.success),
      AgentPhase.stopping => (t('dk.agent.phase.stopping'), AppColors.warning),
      AgentPhase.failed => (t('dk.agent.phase.failed'), AppColors.error),
    };
    final err = agent.error;
    final canStart = agent.phase == AgentPhase.stopped || agent.phase == AgentPhase.failed;
    final live = agent.phase == AgentPhase.starting || agent.phase == AgentPhase.running;

    final head = TechCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CardHead(t('dk.agent.title')),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              StatusPill(label, color),
              if (info != null)
                Text('robot ${info.robotId ?? '?'} · ${info.robotIp ?? '—'} · ${info.modes.map((m) => m.toUpperCase()).join(' / ')}',
                    style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          if (err != null) ...[
            const SizedBox(height: 10),
            Text(err.startsWith('dk.') ? t(err) : err, style: const TextStyle(color: AppColors.error, fontSize: 13)),
          ],
          if (info != null && info.backendMismatch) ...[
            const SizedBox(height: 10),
            Text(t('dk.agent.err.backend').replaceAll('{url}', info.backendUrl ?? ''), style: const TextStyle(color: AppColors.warning, fontSize: 13)),
          ],
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              if (canStart) TechButton(t('dk.agent.start'), icon: Icons.play_arrow_rounded, onPressed: _start),
              if (live) TechButton(t('dk.agent.stop'), icon: Icons.stop_rounded, style: CustomButtonStyle.outline, onPressed: _stop),
              TechButton(t('dk.agent.check'), icon: Icons.fact_check_outlined, style: CustomButtonStyle.outline,
                  onPressed: _checking || info == null ? null : _check),
              TechButton(_showLog ? t('dk.agent.hideLog') : t('dk.agent.showLog'), small: true, style: CustomButtonStyle.text,
                  onPressed: () => setState(() => _showLog = !_showLog)),
            ],
          ),
          if (_checks != null) ...[const SizedBox(height: 14), _CheckList(steps: _checks!, t: t)],
          if (_showLog) ...[const SizedBox(height: 14), _Log(lines: agent.log)],
        ],
      ),
    );

    return head;
  }
}

class _CheckList extends StatelessWidget {
  final List<CheckStep> steps;
  final T t;
  const _CheckList({required this.steps, required this.t});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final s in steps)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 22,
                    child: switch (s.state) {
                      CheckState.running => const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                      CheckState.ok => const Icon(Icons.check_circle, size: 18, color: AppColors.success),
                      CheckState.failed => const Icon(Icons.cancel, size: 18, color: AppColors.error),
                      CheckState.skipped => const Icon(Icons.remove_circle_outline, size: 18, color: AppColors.info),
                      CheckState.waiting => const Icon(Icons.radio_button_unchecked, size: 18, color: AppColors.info),
                    },
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text.rich(TextSpan(children: [
                      TextSpan(text: t(s.key), style: const TextStyle(fontWeight: FontWeight.w600)),
                      if (s.detail != null && s.detail!.isNotEmpty) TextSpan(text: '  ${s.detail}'),
                      if (s.state == CheckState.skipped) TextSpan(text: '  ${t('dk.agent.chk.skipped')}'),
                    ])),
                  ),
                ],
              ),
            ),
          if (steps.every((s) => s.state == CheckState.ok))
            Padding(padding: const EdgeInsets.only(top: 6), child: Text(t('dk.agent.chk.allOk'), style: const TextStyle(color: AppColors.success))),
        ],
      );
}

class _Log extends StatelessWidget {
  final List<String> lines;
  const _Log({required this.lines});

  @override
  Widget build(BuildContext context) => Container(
        height: 180,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(TechRadius.control)),
        child: SingleChildScrollView(
          reverse: true,
          child: SelectableText(lines.join('\n'),
              style: const TextStyle(fontFamily: 'Consolas', fontSize: 12, color: AppColors.onInk, height: 1.35)),
        ),
      );
}

/// Starts this workstation's agent as the signed-in technician. The password typed at sign-in is used; after a restored
/// session (no password in memory) it is asked once. Returns false when there is nothing to start or the user cancels.
Future<bool> startAgentAsSignedIn(BuildContext context, WidgetRef ref) async {
  final auth = ref.read(authNotifierProvider);
  final agent = ref.read(agentControllerProvider.notifier);
  if (auth is! AuthAuthenticated || agent.busy || ref.read(agentControllerProvider).phase == AgentPhase.notFound) return false;
  var password = ref.read(authNotifierProvider.notifier).sessionPassword;
  if (password == null) {
    password = await showDialog<String>(context: context, builder: (_) => AgentPasswordDialog(email: auth.email));
    if (password == null || password.isEmpty) return false;
    ref.read(authNotifierProvider.notifier).rememberPassword(password);
  }
  if (!context.mounted || agent.busy) return false;
  await agent.start(email: auth.email, password: password);
  return true;
}

/// Set once the agent was started (or offered) after this sign-in, so it is not started again on every page.
final agentAutoStartedProvider = StateProvider<bool>((ref) => false);

/// Wraps the technician pages: right after a technical staff sign-in on the robot workstation, starts the Robot Agent
/// (owner 2026-11-26). On a computer without `robot_agent` nothing happens.
class AgentAutoStart extends ConsumerStatefulWidget {
  final Widget child;
  const AgentAutoStart({super.key, required this.child});

  @override
  ConsumerState<AgentAutoStart> createState() => _AgentAutoStartState();
}

class _AgentAutoStartState extends ConsumerState<AgentAutoStart> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeStart());
  }

  Future<void> _maybeStart() async {
    if (!mounted || ref.read(agentAutoStartedProvider)) return;
    if (ref.read(authNotifierProvider) is! AuthAuthenticated) return;
    final phase = ref.read(agentControllerProvider).phase;
    if (phase != AgentPhase.stopped) return;                          // not a workstation, already running, or a failure to read first
    ref.read(agentAutoStartedProvider.notifier).state = true;
    await startAgentAsSignedIn(context, ref);
  }

  @override
  Widget build(BuildContext context) {
    // Signing out stops the agent (agentControllerProvider); the next sign-in starts it again.
    ref.listen(authNotifierProvider, (prev, next) {
      if (next is! AuthAuthenticated) ref.read(agentAutoStartedProvider.notifier).state = false;
    });
    return widget.child;
  }
}

/// Asked once after a restored session: the agent signs in with the technician's own password.
class AgentPasswordDialog extends ConsumerStatefulWidget {
  final String email;
  const AgentPasswordDialog({super.key, required this.email});

  @override
  ConsumerState<AgentPasswordDialog> createState() => AgentPasswordDialogState();
}

class AgentPasswordDialogState extends ConsumerState<AgentPasswordDialog> {
  final _c = TextEditingController();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    return AlertDialog(
      title: Text(t('dk.agent.pw.title')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(t('dk.agent.pw.body').replaceAll('{email}', widget.email)),
          const SizedBox(height: 12),
          TextField(
            controller: _c,
            obscureText: true,
            autofocus: true,
            onSubmitted: (v) => Navigator.of(context).pop(v),
          ),
        ],
      ),
      actions: [
        TechButton(t('dk.confirm.cancel'), style: CustomButtonStyle.text, small: true, onPressed: () => Navigator.of(context).pop()),
        TechButton(t('dk.agent.start'), onPressed: () => Navigator.of(context).pop(_c.text)),
      ],
    );
  }
}
