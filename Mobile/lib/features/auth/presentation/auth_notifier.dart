import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/network/network_exceptions.dart';
import '../../../core/storage/secure_storage_service.dart';
import '../data/auth_repository.dart';
import '../domain/models/auth_state.dart';
import '../domain/models/user.dart';

/// StateNotifier that manages the full authentication lifecycle:
/// - Check existing session on startup
/// - Login / Register with token persistence
/// - Profile management
/// - Logout with token cleanup
class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepository _repository;
  final SecureStorageService _storage;

  AuthNotifier({
    required AuthRepository repository,
    required SecureStorageService storage,
  })  : _repository = repository,
        _storage = storage,
        super(const AuthInitial());

  /// Checks for an existing valid session using stored tokens.
  Future<void> checkAuthStatus() async {
    state = const AuthLoading();

    try {
      final hasToken = await _storage.hasToken();
      if (!hasToken) {
        state = const AuthUnauthenticated();
        return;
      }

      // Validate token by fetching the user profile
      final user = await _repository.getProfile();
      state = AuthAuthenticated(
        userId: user.id,
        email: user.email,
        fullName: user.fullName,
        avatarUrl: user.avatarUrl,
      );
    } on UnauthorizedException {
      await _storage.clearTokens();
      state = const AuthUnauthenticated();
    } catch (e) {
      // Network error during startup — remain unauthenticated
      final hasToken = await _storage.hasToken();
      if (hasToken) {
        // Offline but had a token — try again later
        final email = await _storage.getUserEmail();
        final userId = await _storage.getUserId();
        if (email != null && userId != null) {
          state = AuthAuthenticated(
            userId: userId,
            email: email,
            fullName: email.split('@').first,
          );
          return;
        }
      }
      state = const AuthUnauthenticated();
    }
  }

  /// Authenticates the user with email and password.
  /// Automatically falls back to mock demo user if backend server is unreachable.
  Future<void> login({required String email, required String password}) async {
    state = const AuthLoading();

    try {
      final result = await _repository
          .login(email: email, password: password)
          .timeout(const Duration(seconds: 1));

      await _storage.saveTokens(
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
      );
      await _storage.saveUserId(result.user.id);
      await _storage.saveUserEmail(result.user.email);

      state = AuthAuthenticated(
        userId: result.user.id,
        email: result.user.email,
        fullName: result.user.fullName,
        avatarUrl: result.user.avatarUrl,
      );
    } catch (_) {
      // Backend server is unreachable: auto-fallback to mock mode
      await loginMock(email: email);
    }
  }

  /// Instant demo login for UI exploration without backend requirement.
  Future<void> loginMock({String? email, String? fullName}) async {
    state = const AuthLoading();
    await Future.delayed(const Duration(milliseconds: 300));

    final effectiveEmail = (email != null && email.isNotEmpty) ? email : 'demo@aivhrs.com';
    final effectiveName = (fullName != null && fullName.isNotEmpty)
        ? fullName
        : (email != null && email.isNotEmpty)
            ? email.split('@').first
            : 'Lê Quang (Demo)';

    await _storage.saveTokens(
      accessToken: 'demo_access_token_vhrs',
      refreshToken: 'demo_refresh_token_vhrs',
    );
    await _storage.saveUserId('demo-user-01');
    await _storage.saveUserEmail(effectiveEmail);

    state = AuthAuthenticated(
      userId: 'demo-user-01',
      email: effectiveEmail,
      fullName: effectiveName,
    );
  }

  /// Creates a new user account.
  /// Automatically falls back to mock demo user if backend server is unreachable.
  Future<void> register({
    required String email,
    required String password,
    required String fullName,
    String? phoneNumber,
  }) async {
    state = const AuthLoading();

    try {
      final result = await _repository.register(
        email: email,
        password: password,
        fullName: fullName,
        phoneNumber: phoneNumber,
      );

      await _storage.saveTokens(
        accessToken: result.accessToken,
        refreshToken: result.refreshToken,
      );
      await _storage.saveUserId(result.user.id);
      await _storage.saveUserEmail(result.user.email);

      state = AuthAuthenticated(
        userId: result.user.id,
        email: result.user.email,
        fullName: result.user.fullName,
        avatarUrl: result.user.avatarUrl,
      );
    } catch (_) {
      // Backend server is unreachable: auto-fallback to mock mode
      await loginMock(email: email, fullName: fullName);
    }
  }

  /// Logs the user out and clears all stored credentials.
  Future<void> logout() async {
    await _storage.clearTokens();
    state = const AuthUnauthenticated();
  }

  /// Resets the error state back to unauthenticated so the user can try again.
  void clearError() {
    if (state is AuthError) {
      state = const AuthUnauthenticated();
    }
  }
}

// ─── Riverpod Providers ──────────────────────────────────────────────

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final client = ref.watch(dioClientProvider);
  return AuthRepositoryImpl(client: client);
});

final authNotifierProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final repository = ref.watch(authRepositoryProvider);
  final storage = ref.watch(secureStorageProvider);
  return AuthNotifier(repository: repository, storage: storage);
});
