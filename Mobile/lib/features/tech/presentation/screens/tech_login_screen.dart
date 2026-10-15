import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/widgets.dart';
import '../../data/tech_store.dart';
import '../../domain/roster.dart';
import '../../i18n/tech_strings.dart';
import '../widgets/tech_ui.dart';

/// Technician sign-in. Prototype accounts only, any password works (FE `/login`).
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
      _emailError = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email) ? null : t('login.errEmail');
      _passwordError = _password.text.isEmpty ? t('login.errPassword') : null;
    });
    if (_emailError != null || _passwordError != null) return;
    if (!ref.read(sessionProvider.notifier).login(email)) {
      setState(() => _emailError = t('dk.login.notTech'));
    }
  }

  void _fill(String email) {
    _email.text = email;
    _password.text = 'demo';
    setState(() {
      _emailError = null;
      _passwordError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(tProvider);
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
                              textInputAction: TextInputAction.next,
                            ),
                            const SizedBox(height: 16),
                            CustomTextField(
                              label: t('login.password'),
                              controller: _password,
                              obscureText: true,
                              errorText: _passwordError,
                              textInputAction: TextInputAction.done,
                              onSubmitted: (_) => _submit(),
                            ),
                            const SizedBox(height: 24),
                            TechButton(t('login.title'), onPressed: _submit, expand: true),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(t('login.demo'), textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                    const SizedBox(height: 12),
                    Wrap(
                      alignment: WrapAlignment.center,
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final e in techAccounts.entries)
                          ActionChip(
                            label: Text('${e.value.name} · ${e.value.techId}'),
                            onPressed: () => _fill(e.key),
                            tooltip: e.key,
                          ),
                      ],
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
