import 'dart:io';

import 'package:dio/dio.dart';
import 'package:logger/logger.dart';

import 'network_exceptions.dart';

/// Converts Dio errors and HTTP status codes into typed [NetworkException]s.
class ErrorHandler {
  ErrorHandler._();

  static final Logger _logger = Logger(
    printer: PrettyPrinter(methodCount: 0),
  );

  /// Converts a [DioException] into a typed [NetworkException].
  static NetworkException handleDioError(DioException error) {
    _logger.e(
      'DioError: ${error.type} — ${error.message}',
      error: error.error,
      stackTrace: error.stackTrace,
    );

    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const TimeoutException();

      case DioExceptionType.badResponse:
        return _handleResponseError(error.response);

      case DioExceptionType.cancel:
        return const CancelException();

      case DioExceptionType.connectionError:
        return const NoInternetException();

      case DioExceptionType.badCertificate:
        return const UnknownException('SSL certificate error.');

      case DioExceptionType.unknown:
        if (error.error is SocketException) {
          return const NoInternetException();
        }
        return UnknownException(
          error.message ?? 'An unexpected error occurred.',
          error.error,
        );
    }
  }

  /// Maps HTTP status code to specific [NetworkException].
  ///
  /// The backend always answers errors as
  /// `{"error": {"code": "INVALID_CREDENTIALS", "message": "...", "details": ...}}`.
  static NetworkException _handleResponseError(Response? response) {
    final statusCode = response?.statusCode ?? 0;
    final err = _envelope(response?.data);
    final serverMessage = err.message;
    final code = err.code;

    switch (statusCode) {
      case 400:
        return BadRequestException(serverMessage ?? 'Invalid request.', err.fields, code);
      case 401:
        return UnauthorizedException(serverMessage ?? 'Session expired.', code);
      case 403:
        return ForbiddenException(serverMessage ?? 'Access denied.', code);
      case 404:
        return NotFoundException(serverMessage ?? 'Resource not found.', code);
      case 409:
        return ConflictException(serverMessage ?? 'Conflict.', code);
      case 422:
        return UnprocessableException(serverMessage ?? 'Validation failed.', err.fields, code);
      case 423 || 429:
        final retry = int.tryParse(response?.headers.value('retry-after') ?? '') ??
            (err.details is Map ? (err.details as Map)['retry_after_seconds'] as int? : null);
        return TooManyAttemptsException(serverMessage ?? 'Too many attempts. Please try again later.', code, retry);
      case >= 500:
        return ServerException(serverMessage ?? 'Server error.', statusCode, code);
      default:
        return ServerException('Unexpected error ($statusCode).', statusCode, code);
    }
  }

  /// Reads the backend error envelope. Also accepts a plain `{"message"}` or `{"detail"}` body.
  static ({String? code, String? message, Object? details, Map<String, dynamic>? fields}) _envelope(dynamic data) {
    if (data is Map<String, dynamic>) {
      final e = data['error'];
      if (e is Map<String, dynamic>) {
        final details = e['details'];
        Map<String, dynamic>? fields;
        if (details is List) {
          fields = {
            for (final d in details.whereType<Map>())
              if (d['field'] != null) '${d['field']}': d['message'],
          };
        }
        return (code: e['code'] as String?, message: e['message'] as String?, details: details, fields: fields);
      }
      final msg = data['message'] ?? data['detail'];
      return (code: null, message: msg is String ? msg : null, details: null, fields: null);
    }
    if (data is String && data.isNotEmpty) return (code: null, message: data, details: null, fields: null);
    return (code: null, message: null, details: null, fields: null);
  }

  /// Convenience: handle any error, routing Dio vs generic exceptions.
  static NetworkException handle(Object error) {
    if (error is DioException) {
      return handleDioError(error);
    }
    if (error is NetworkException) {
      return error;
    }
    return UnknownException(error.toString(), error);
  }
}
