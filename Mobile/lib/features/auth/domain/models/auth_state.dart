import 'package:equatable/equatable.dart';

/// Represents the full authentication state in the application.
sealed class AuthState extends Equatable {
  const AuthState();

  @override
  List<Object?> get props => [];
}

/// Initial state before any authentication check has been performed.
class AuthInitial extends AuthState {
  const AuthInitial();
}

/// Authentication check is in progress (e.g., verifying stored token).
class AuthLoading extends AuthState {
  const AuthLoading();
}

/// User is authenticated and the session is valid.
class AuthAuthenticated extends AuthState {
  final String userId;
  final String email;
  final String fullName;
  final String? avatarUrl;

  const AuthAuthenticated({
    required this.userId,
    required this.email,
    required this.fullName,
    this.avatarUrl,
  });

  @override
  List<Object?> get props => [userId, email, fullName, avatarUrl];
}

/// User is not authenticated (no valid token found).
class AuthUnauthenticated extends AuthState {
  const AuthUnauthenticated();
}

/// An authentication error occurred.
class AuthError extends AuthState {
  final String message;

  const AuthError(this.message);

  @override
  List<Object?> get props => [message];
}
