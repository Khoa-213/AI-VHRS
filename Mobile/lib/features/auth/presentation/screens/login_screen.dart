import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/utils/validators.dart';
import '../../../../core/widgets/widgets.dart';
import '../auth_notifier.dart';
import '../../domain/models/auth_state.dart';

/// Login screen with email/password form, validation, and loading state.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _handleLogin() {
    if (_formKey.currentState?.validate() ?? false) {
      ref.read(authNotifierProvider.notifier).login(
            email: _emailController.text.trim(),
            password: _passwordController.text,
          );
    }
  }

  void _handleDemoLogin() {
    ref.read(authNotifierProvider.notifier).loginMock();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authNotifierProvider);
    final isLoading = authState is AuthLoading;
    final theme = Theme.of(context);

    // Listen for auth errors to show snackbar
    ref.listen<AuthState>(authNotifierProvider, (prev, next) {
      if (next is AuthError) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.message),
            backgroundColor: AppColors.error,
          ),
        );
        ref.read(authNotifierProvider.notifier).clearError();
      }
    });

    return BaseScreen(
      showBackButton: false,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      body: Center(
        child: SingleChildScrollView(
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Logo & Branding
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    width: 64,
                    height: 64,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.ink,
                      borderRadius: BorderRadius.circular(22),
                    ),
                    child: const ModeGlyph(
                      kind: ModeGlyphKind.canvas,
                      size: 30,
                      color: AppColors.onInk,
                    ),
                  ),
                ),
                const SizedBox(height: 28),
                Text('welcome back.', style: theme.textTheme.displayMedium),
                const SizedBox(height: 8),
                Text(
                  'Sign in to send your words to the robot.',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 40),

                // Email Field
                CustomTextField(
                  label: 'Email',
                  hint: 'you@example.com',
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  prefixIcon: const Icon(Icons.email_outlined, size: 20, color: AppColors.textTertiary),
                  validator: Validators.email,
                  enabled: !isLoading,
                ),
                const SizedBox(height: 20),

                // Password Field
                CustomTextField(
                  label: 'Password',
                  hint: 'Enter your password',
                  controller: _passwordController,
                  obscureText: true,
                  textInputAction: TextInputAction.done,
                  prefixIcon: const Icon(Icons.lock_outlined, size: 20, color: AppColors.textTertiary),
                  validator: (value) => Validators.required(value, 'Password'),
                  onSubmitted: (_) => _handleLogin(),
                  enabled: !isLoading,
                ),
                const SizedBox(height: 12),

                // Forgot Password
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: isLoading
                        ? null
                        : () => ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Password reset isn\'t available in the app yet. Contact support.'),
                              ),
                            ),
                    child: Text(
                      'Forgot password?',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                // Login Button
                CustomButton(
                  label: 'Sign in',
                  onPressed: _handleLogin,
                  isLoading: isLoading,
                ),
                const SizedBox(height: 12),

                // Quick Demo Login Button
                CustomButton(
                  label: '⚡ Quick Demo Login (Dùng thử ngay)',
                  style: CustomButtonStyle.outline,
                  onPressed: _handleDemoLogin,
                  isLoading: isLoading,
                ),
                const SizedBox(height: 24),

                // Register Link
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      "Don't have an account? ",
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                    GestureDetector(
                      onTap: isLoading ? null : () => context.go('/register'),
                      child: Text(
                        'Create one',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AppColors.textPrimary,
                          fontWeight: FontWeight.w600,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
