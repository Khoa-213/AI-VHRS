import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/network/network_exceptions.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/tech_shell.dart';
import '../widgets/tech_ui.dart';

/// Language, the signed-in account, change password and sign out.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(tProvider);
    final lang = ref.watch(langProvider);
    final auth = ref.watch(authNotifierProvider);

    Future<void> changePassword() async {
      final done = await showDialog<bool>(context: context, builder: (_) => const _ChangePasswordDialog());
      if (done == true && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('dk.settings.changed'))));
      }
    }

    return TechPage(
      title: t('dk.settings.title'),
      body: Align(
        alignment: Alignment.topLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TechCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    CardHead(t('lang.label')),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final l in Lang.values)
                          TechButton(
                            l.label,
                            small: true,
                            style: l == lang ? CustomButtonStyle.primary : CustomButtonStyle.outline,
                            onPressed: () => ref.read(langProvider.notifier).set(l),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              TechCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    CardHead(t('dk.settings.account')),
                    if (auth is AuthAuthenticated) ...[
                      FactList([
                        (t('dk.settings.name'), valueText(auth.fullName)),
                        (t('login.email'), valueText(auth.email)),
                      ]),
                      const SizedBox(height: 16),
                    ],
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        TechButton(
                          t('dk.settings.changePassword'),
                          small: true,
                          style: CustomButtonStyle.outline,
                          onPressed: changePassword,
                        ),
                        TechButton(
                          t('rail.signOut'),
                          small: true,
                          icon: Icons.logout_rounded,
                          onPressed: () => ref.read(authNotifierProvider.notifier).logout(),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// `POST /me/change-password`. Pops with true once the password has changed.
class _ChangePasswordDialog extends ConsumerStatefulWidget {
  const _ChangePasswordDialog();

  @override
  ConsumerState<_ChangePasswordDialog> createState() => _ChangePasswordDialogState();
}

class _ChangePasswordDialogState extends ConsumerState<_ChangePasswordDialog> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  String? _currentError, _nextError, _confirmError;
  bool _saving = false;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final t = ref.read(tProvider);
    final length = _next.text.length;
    setState(() {
      _currentError = _current.text.isEmpty ? t('dk.settings.errCurrent') : null;
      _nextError = length < 8 || length > 72 ? t('dk.settings.errLength') : null;
      _confirmError = _confirm.text != _next.text ? t('dk.settings.errMatch') : null;
    });
    if (_currentError != null || _nextError != null || _confirmError != null) return;
    setState(() => _saving = true);
    try {
      await ref.read(authRepositoryProvider).changePassword(currentPassword: _current.text, newPassword: _next.text);
      if (mounted) Navigator.of(context).pop(true);
    } on NetworkException catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        if (e.code == 'WRONG_PASSWORD') {
          _currentError = t('dk.settings.errWrong');
        } else {
          _confirmError = t(authErrorKey(e));
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    return Dialog(
      backgroundColor: AppColors.surface,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(t('dk.settings.changePassword'), style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 20),
              CustomTextField(
                label: t('dk.settings.current'),
                controller: _current,
                obscureText: true,
                errorText: _currentError,
                enabled: !_saving,
                autofocus: true,
              ),
              const SizedBox(height: 16),
              CustomTextField(
                label: t('dk.settings.new'),
                controller: _next,
                obscureText: true,
                errorText: _nextError,
                enabled: !_saving,
              ),
              const SizedBox(height: 16),
              CustomTextField(
                label: t('dk.settings.confirm'),
                controller: _confirm,
                obscureText: true,
                errorText: _confirmError,
                enabled: !_saving,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 20),
              Wrap(
                spacing: 12,
                runSpacing: 8,
                children: [
                  TechButton(t('dk.settings.save'), onPressed: _saving ? null : _save),
                  TechButton(
                    t('dk.settings.cancel'),
                    style: CustomButtonStyle.text,
                    small: true,
                    onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
