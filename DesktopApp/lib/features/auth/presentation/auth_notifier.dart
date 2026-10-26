import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/network_exceptions.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../data/auth_repository.dart';
import '../domain/models/auth_state.dart';
import '../domain/models/user.dart';

/// Manages the authentication lifecycle against the AI-VHRS backend:
/// restore the session on startup, sign in, sign out, and react when the
/// refresh token is rejected.
///
/// [AuthError.message] is a translation key (`dk.err.*`), shown with `t()`.
class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepository _repository;
  final SecureStorageService _storage;

  /// Roles allowed to use this app. The desk is for technical staff only.
  final Set<String> allowedRoles;

  AuthNotifier({
    required AuthRepository repository,
    required SecureStorageService storage,
    this.allowedRoles = const {UserRole.technicalStaff},
  })  : _repository = repository,
        _storage = storage,
        super(const AuthInitial());

  /// Restores a saved session. The interceptor refreshes an expired access token.
  Future<void> checkAuthStatus() async {
    state = const AuthLoading();
    if (!await _storage.hasToken()) {
      state = const AuthUnauthenticated();
      return;
    }
    try {
      final user = await _repository.getProfile();
      state = allowedRoles.contains(user.role) ? AuthAuthenticated.fromUser(user) : const AuthUnauthenticated();
    } on UnauthorizedException {
      await _storage.clearTokens();
      state = const AuthUnauthenticated();
    } on NetworkException {
      // Offline or the server is still waking up: keep the saved session.
      final email = await _storage.getUserEmail();
      final userId = await _storage.getUserId();
      state = email != null && userId != null
          ? AuthAuthenticated(
              userId: userId,
              email: email,
              fullName: email.split('@').first,
              role: UserRole.technicalStaff,
            )
          : const AuthUnauthenticated();
    }
  }

  Future<void> login({required String email, required String password}) async {
    state = const AuthLoading();
    try {
      final session = await _repository.login(email: email, password: password);
      if (!allowedRoles.contains(session.user.role)) {
        // Customers and office staff have their own apps: revoke this session.
        await _storage.saveTokens(accessToken: session.accessToken, refreshToken: session.refreshToken);
        await _revokeQuietly();
        state = const AuthError('dk.err.role');
        return;
      }
      await _storage.saveTokens(accessToken: session.accessToken, refreshToken: session.refreshToken);
      await _storage.saveUserId(session.user.id);
      await _storage.saveUserEmail(session.user.email);
      state = AuthAuthenticated.fromUser(session.user);
    } on NetworkException catch (e) {
      state = AuthError(authErrorKey(e));
    }
  }

  /// Sends the reset email. Throws a [NetworkException] if the request fails.
  Future<void> requestPasswordReset(String email) => _repository.requestPasswordReset(email);

  /// Revokes the session on the server (best effort), then clears local tokens.
  Future<void> logout() async {
    await _revokeQuietly();
    state = const AuthUnauthenticated();
  }

  /// Called when the refresh token is rejected: tokens are already cleared.
  void sessionExpired() {
    if (state is AuthAuthenticated) state = const AuthError('dk.err.expired');
  }

  /// Resets the error state back to unauthenticated so the user can try again.
  void clearError() {
    if (state is AuthError) state = const AuthUnauthenticated();
  }

  Future<void> _revokeQuietly() async {
    try {
      await _repository.logout();
    } on NetworkException {
      // Offline or already revoked: the local tokens go anyway.
    }
    await _storage.clearTokens();
  }
}

/// Translation key for an auth error, chosen by the backend error code.
String authErrorKey(NetworkException e) {
  switch (e.code) {
    case 'INVALID_CREDENTIALS':
      return 'dk.err.credentials';
    case 'ACCOUNT_DISABLED':
      return 'dk.err.disabled';
    case 'ACCOUNT_TEMP_LOCKED':
      return 'dk.err.locked';
    case 'RATE_LIMITED':
      return 'dk.err.rate';
    case 'VALIDATION_ERROR':
      return 'dk.err.validation';
  }
  return switch (e) {
    TooManyAttemptsException() => 'dk.err.rate',
    TimeoutException() => 'dk.err.timeout',
    NoInternetException() => 'dk.err.offline',
    ServerException() => 'dk.err.server',
    _ => 'dk.err.unknown',
  };
}

// ─── Riverpod Providers ──────────────────────────────────────────────

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final client = ref.watch(dioClientProvider);
  return AuthRepositoryImpl(client: client);
});

final authNotifierProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final notifier = AuthNotifier(
    repository: ref.watch(authRepositoryProvider),
    storage: ref.watch(secureStorageProvider),
  );
  ref.listen<int>(sessionExpiredProvider, (_, _) => notifier.sessionExpired());
  return notifier;
});
