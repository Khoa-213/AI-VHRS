import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/constants/app_colors.dart';
import '../../../../core/utils/validators.dart';
import '../../../../core/widgets/widgets.dart';
import '../auth_notifier.dart';
import '../../domain/models/auth_state.dart';

/// Registration screen with full name, email, phone, and password fields.
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _fullNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  @override
  void dispose() {
    _fullNameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  void _handleRegister() {
    if (_formKey.currentState?.validate() ?? false) {
      ref.read(authNotifierProvider.notifier).register(
            email: _emailController.text.trim(),
            password: _passwordController.text,
            fullName: _fullNameController.text.trim(),
            phoneNumber: _phoneController.text.trim().isNotEmpty
                ? _phoneController.text.trim()
                : null,
          );
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authNotifierProvider);
    final isLoading = authState is AuthLoading;
    final theme = Theme.of(context);

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
      title: '',
      padding: const EdgeInsets.symmetric(horizontal: 24),
      body: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 24),
              Text('start writing.', style: theme.textTheme.displayMedium),
              const SizedBox(height: 8),
              Text(
                'One account for every letter, card and signature you send to the robot.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 32),

              // Full Name
              CustomTextField(
                label: 'Full name',
                hint: 'Enter your full name',
                controller: _fullNameController,
                textInputAction: TextInputAction.next,
                textCapitalization: TextCapitalization.words,
                prefixIcon: const Icon(Icons.person_outlined, size: 20, color: AppColors.textTertiary),
                validator: (value) => Validators.required(value, 'Full name'),
                enabled: !isLoading,
              ),
              const SizedBox(height: 20),

              // Email
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

              // Phone (optional)
              CustomTextField(
                label: 'Phone (optional)',
                hint: '0912 345 678',
                controller: _phoneController,
                keyboardType: TextInputType.phone,
                textInputAction: TextInputAction.next,
                prefixIcon: const Icon(Icons.phone_outlined, size: 20, color: AppColors.textTertiary),
                enabled: !isLoading,
              ),
              const SizedBox(height: 20),

              // Password
              CustomTextField(
                label: 'Password',
                hint: 'At least 8 characters',
                controller: _passwordController,
                obscureText: true,
                textInputAction: TextInputAction.next,
                prefixIcon: const Icon(Icons.lock_outlined, size: 20, color: AppColors.textTertiary),
                validator: Validators.password,
                enabled: !isLoading,
              ),
              const SizedBox(height: 20),

              // Confirm Password
              CustomTextField(
                label: 'Confirm password',
                hint: 'Re-enter your password',
                controller: _confirmPasswordController,
                obscureText: true,
                textInputAction: TextInputAction.done,
                prefixIcon: const Icon(Icons.lock_outlined, size: 20, color: AppColors.textTertiary),
                validator: (value) =>
                    Validators.confirmPassword(value, _passwordController.text),
                onSubmitted: (_) => _handleRegister(),
                enabled: !isLoading,
              ),
              const SizedBox(height: 32),

              // Register Button
              CustomButton(
                label: 'Create account',
                onPressed: _handleRegister,
                isLoading: isLoading,
              ),
              const SizedBox(height: 24),

              // Login Link
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    'Already have an account? ',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                  GestureDetector(
                    onTap: isLoading ? null : () => context.go('/login'),
                    child: Text(
                      'Sign in',
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
    );
  }
}
