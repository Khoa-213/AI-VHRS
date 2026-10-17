import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/network/network_exceptions.dart';
import '../../../../core/widgets/widgets.dart';
import '../../../auth/domain/models/auth_state.dart';
import '../../../auth/presentation/auth_notifier.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/tech_ui.dart';

final _emailRule = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Technician sign-in against `POST /auth/login`. Only `TECHNICAL_STAFF`
/// accounts get in; the router moves on once the session is set.
class TechLoginScreen extends ConsumerStatefulWidget {
  const TechLoginScreen({super.key});

  @override
  ConsumerState<TechLoginScreen> createState() => _TechLoginScreenState();
}

class _TechLoginScreenState extends ConsumerState<TechLoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _emailError;
  String? _passwordError;

  /// Translation key of the last sign-in error, shown above the button.
  String? _formError;

  @override
  void initState() {
    super.initState();
    // An error raised before this screen existed (session expired on another page).
    final auth = ref.read(authNotifierProvider);
    if (auth is AuthError) {
      _formError = auth.message;
      WidgetsBinding.instance.addPostFrameCallback((_) => ref.read(authNotifierProvider.notifier).clearError());
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _submit() {
    final t = ref.read(tProvider);
    final email = _email.text.trim();
    setState(() {
      _emailError = _emailRule.hasMatch(email) ? null : t('login.errEmail');
      _passwordError = _password.text.isEmpty ? t('login.errPassword') : null;
      _formError = null;
    });
    if (_emailError != null || _passwordError != null) return;
    ref.read(authNotifierProvider.notifier).login(email: email, password: _password.text);
  }

  Future<void> _forgot() async {
    final t = ref.read(tProvider);
    final email = await showDialog<String>(
      context: context,
      builder: (_) => _ResetDialog(initialEmail: _email.text.trim()),
    );
    if (email == null || !mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t('dk.reset.sent', {'email': email}))));
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    final auth = ref.watch(authNotifierProvider);
    final busy = auth is AuthLoading;

    ref.listen<AuthState>(authNotifierProvider, (_, next) {
      if (next is AuthError) {
        setState(() => _formError = next.message);
        ref.read(authNotifierProvider.notifier).clearError();
      }
    });

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          const Positioned(top: 24, right: 32, child: LanguageToggle()),
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: QuillPaperArt(size: 88)),
                    const SizedBox(height: 28),
                    Text(t('dk.techDesk'), textAlign: TextAlign.center, style: Theme.of(context).textTheme.displayMedium),
                    const SizedBox(height: 8),
                    Text(
                      t('dk.login.lede'),
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.5),
                    ),
                    const SizedBox(height: 32),
                    TechCard(
                      padding: const EdgeInsets.all(28),
                      child: AutofillGroup(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            CustomTextField(
                              label: t('login.email'),
                              controller: _email,
                              keyboardType: TextInputType.emailAddress,
                              errorText: _emailError,
                              enabled: !busy,
                              textInputAction: TextInputAction.next,
                            ),
                            const SizedBox(height: 16),
                            CustomTextField(
                              label: t('login.password'),
                              controller: _password,
                              obscureText: true,
                              errorText: _passwordError,
                              enabled: !busy,
                              textInputAction: TextInputAction.done,
                              onSubmitted: (_) => _submit(),
                            ),
                            Align(
                              alignment: Alignment.centerRight,
                              child: TextButton(
                                onPressed: busy ? null : _forgot,
                                child: Text(t('dk.login.forgot'),
                                    style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                              ),
                            ),
                            if (_formError != null) ...[
                              Semantics(
                                liveRegion: true,
                                child: Text(t(_formError!), style: const TextStyle(fontSize: 13, color: AppColors.error, height: 1.4)),
                              ),
                              const SizedBox(height: 12),
                            ],
                            const SizedBox(height: 4),
                            busy
                                ? const SizedBox(height: 50, child: Center(child: CircularProgressIndicator(strokeWidth: 2)))
                                : TechButton(t('login.title'), onPressed: _submit, expand: true),
                            if (busy) ...[
                              const SizedBox(height: 12),
                              Text(t('dk.login.waking'),
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, height: 1.4)),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Asks for an email and requests a reset link. Pops with the email on success.
class _ResetDialog extends ConsumerStatefulWidget {
  final String initialEmail;
  const _ResetDialog({required this.initialEmail});

  @override
  ConsumerState<_ResetDialog> createState() => _ResetDialogState();
}

class _ResetDialogState extends ConsumerState<_ResetDialog> {
  late final _email = TextEditingController(text: widget.initialEmail);
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final t = ref.read(tProvider);
    final email = _email.text.trim();
    if (!_emailRule.hasMatch(email)) {
      setState(() => _error = t('login.errEmail'));
      return;
    }
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await ref.read(authNotifierProvider.notifier).requestPasswordReset(email);
      if (mounted) Navigator.of(context).pop(email);
    } on NetworkException catch (e) {
      if (mounted) {
        setState(() {
          _sending = false;
          _error = t(authErrorKey(e));
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
    return Dialog(
      backgroundColor: AppColors.surface,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 440),
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(t('dk.reset.title'), style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 8),
              Text(t('dk.reset.body'), style: const TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.5)),
              const SizedBox(height: 20),
              CustomTextField(
                label: t('login.email'),
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                errorText: _error,
                enabled: !_sending,
                autofocus: widget.initialEmail.isEmpty,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _send(),
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  TechButton(t('dk.reset.send'), onPressed: _sending ? null : _send),
                  const SizedBox(width: 12),
                  TechButton(t('qc.cancel'),
                      style: CustomButtonStyle.text, small: true, onPressed: () => Navigator.of(context).pop()),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
