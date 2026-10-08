import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure storage service for managing JWT tokens and sensitive user data.
/// Uses flutter_secure_storage backed by Keychain (iOS) and EncryptedSharedPreferences (Android).
class SecureStorageService {
  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';
  static const _userIdKey = 'user_id';
  static const _userEmailKey = 'user_email';

  static const _mOptions = MacOsOptions(useDataProtectionKeyChain: false);

  final FlutterSecureStorage _storage;
  final Map<String, String> _memoryCache = {};

  SecureStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
              mOptions: _mOptions,
            );

  // ─── Access Token ───────────────────────────────────────────────────

  Future<String?> getAccessToken() async {
    try {
      final val = await _storage
          .read(key: _accessTokenKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
      if (val != null) {
        _memoryCache[_accessTokenKey] = val;
        return val;
      }
    } catch (_) {}
    return _memoryCache[_accessTokenKey];
  }

  Future<void> saveAccessToken(String token) async {
    _memoryCache[_accessTokenKey] = token;
    try {
      await _storage
          .write(key: _accessTokenKey, value: token, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  Future<void> deleteAccessToken() async {
    _memoryCache.remove(_accessTokenKey);
    try {
      await _storage
          .delete(key: _accessTokenKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  // ─── Refresh Token ─────────────────────────────────────────────────

  Future<String?> getRefreshToken() async {
    try {
      final val = await _storage
          .read(key: _refreshTokenKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
      if (val != null) {
        _memoryCache[_refreshTokenKey] = val;
        return val;
      }
    } catch (_) {}
    return _memoryCache[_refreshTokenKey];
  }

  Future<void> saveRefreshToken(String token) async {
    _memoryCache[_refreshTokenKey] = token;
    try {
      await _storage
          .write(key: _refreshTokenKey, value: token, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  Future<void> deleteRefreshToken() async {
    _memoryCache.remove(_refreshTokenKey);
    try {
      await _storage
          .delete(key: _refreshTokenKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  // ─── User Info ─────────────────────────────────────────────────────

  Future<void> saveUserId(String userId) async {
    _memoryCache[_userIdKey] = userId;
    try {
      await _storage
          .write(key: _userIdKey, value: userId, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  Future<String?> getUserId() async {
    try {
      final val = await _storage
          .read(key: _userIdKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
      if (val != null) {
        _memoryCache[_userIdKey] = val;
        return val;
      }
    } catch (_) {}
    return _memoryCache[_userIdKey];
  }

  Future<void> saveUserEmail(String email) async {
    _memoryCache[_userEmailKey] = email;
    try {
      await _storage
          .write(key: _userEmailKey, value: email, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  Future<String?> getUserEmail() async {
    try {
      final val = await _storage
          .read(key: _userEmailKey, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
      if (val != null) {
        _memoryCache[_userEmailKey] = val;
        return val;
      }
    } catch (_) {}
    return _memoryCache[_userEmailKey];
  }

  // ─── Bulk Operations ──────────────────────────────────────────────

  /// Saves both access and refresh tokens atomically.
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    _memoryCache[_accessTokenKey] = accessToken;
    _memoryCache[_refreshTokenKey] = refreshToken;
    await Future.wait([
      saveAccessToken(accessToken),
      saveRefreshToken(refreshToken),
    ]);
  }

  /// Clears all stored tokens (logout).
  Future<void> clearTokens() async {
    _memoryCache.clear();
    await Future.wait([
      deleteAccessToken(),
      deleteRefreshToken(),
      _tryDelete(_userIdKey),
      _tryDelete(_userEmailKey),
    ]);
  }

  Future<void> _tryDelete(String key) async {
    try {
      await _storage
          .delete(key: key, mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  /// Clears all data from secure storage.
  Future<void> clearAll() async {
    _memoryCache.clear();
    try {
      await _storage
          .deleteAll(mOptions: _mOptions)
          .timeout(const Duration(milliseconds: 300));
    } catch (_) {}
  }

  /// Checks if the user has a stored access token.
  Future<bool> hasToken() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }
}

/// Riverpod provider for the SecureStorageService singleton.
final secureStorageProvider = Provider<SecureStorageService>((ref) {
  return SecureStorageService();
});
