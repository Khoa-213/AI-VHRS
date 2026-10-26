import 'package:equatable/equatable.dart';

import 'user.dart';

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

  /// Backend role code, see `UserRole`.
  final String role;

  /// Full account from the API. Null when restored offline from storage.
  final User? user;

  const AuthAuthenticated({
    required this.userId,
    required this.email,
    required this.fullName,
    this.avatarUrl,
    this.role = UserRole.customer,
    this.user,
  });

  factory AuthAuthenticated.fromUser(User u) => AuthAuthenticated(
        userId: u.id,
        email: u.email,
        fullName: u.fullName,
        avatarUrl: u.avatarUrl,
        role: u.role,
        user: u,
      );

  @override
  List<Object?> get props => [userId, email, fullName, avatarUrl, role, user];
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
