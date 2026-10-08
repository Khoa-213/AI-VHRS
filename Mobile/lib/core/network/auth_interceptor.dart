import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';

import '../storage/secure_storage_service.dart';
import '../constants/api_constants.dart';

/// Dio interceptor that attaches JWT Bearer tokens to outgoing requests
/// and handles automatic token refresh on 401 responses.
class AuthInterceptor extends QueuedInterceptor {
  final SecureStorageService _storage;
  final Dio _dio;
  final Logger _logger = Logger(printer: PrettyPrinter(methodCount: 0));

  bool _isRefreshing = false;

  AuthInterceptor({
    required SecureStorageService storage,
    required Dio dio,
  })  : _storage = storage,
        _dio = dio;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    // Skip auth header for login/register endpoints
    final noAuthPaths = [ApiConstants.login, ApiConstants.register];
    if (noAuthPaths.any((path) => options.path.contains(path))) {
      return handler.next(options);
    }

    final token = await _storage.getAccessToken();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }

    _logger.d('→ ${options.method} ${options.uri}');
    handler.next(options);
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    _logger.d('← ${response.statusCode} ${response.requestOptions.uri}');
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401 && !_isRefreshing) {
      _isRefreshing = true;

      try {
        final refreshed = await _attemptTokenRefresh();
        if (refreshed) {
          // Retry the original request with the new token
          final newToken = await _storage.getAccessToken();
          final options = err.requestOptions;
          options.headers['Authorization'] = 'Bearer $newToken';

          final response = await _dio.fetch(options);
          _isRefreshing = false;
          return handler.resolve(response);
        }
      } catch (e) {
        _logger.e('Token refresh failed', error: e);
      }

      _isRefreshing = false;
      // Clear stored tokens — user must re-authenticate
      await _storage.clearTokens();
    }

    handler.next(err);
  }

  /// Attempts to refresh the access token using the stored refresh token.
  Future<bool> _attemptTokenRefresh() async {
    final refreshToken = await _storage.getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      return false;
    }

    try {
      // Use a separate Dio instance to avoid interceptor loop
      final refreshDio = Dio(BaseOptions(baseUrl: ApiConstants.baseUrl));
      final response = await refreshDio.post(
        ApiConstants.refreshToken,
        data: {'refresh_token': refreshToken},
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final newAccessToken = data['access_token'] as String;
        final newRefreshToken = data['refresh_token'] as String?;

        await _storage.saveAccessToken(newAccessToken);
        if (newRefreshToken != null) {
          await _storage.saveRefreshToken(newRefreshToken);
        }

        _logger.i('Token refreshed successfully');
        return true;
      }
    } catch (e) {
      _logger.e('Token refresh request failed', error: e);
    }

    return false;
  }
}
