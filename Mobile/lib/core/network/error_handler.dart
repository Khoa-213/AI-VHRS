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
  static NetworkException _handleResponseError(Response? response) {
    final statusCode = response?.statusCode ?? 0;
    final data = response?.data;
    final serverMessage = _extractMessage(data);

    switch (statusCode) {
      case 400:
        return BadRequestException(
          serverMessage ?? 'Invalid request.',
          data is Map<String, dynamic> ? data['errors'] as Map<String, dynamic>? : null,
        );
      case 401:
        return UnauthorizedException(serverMessage ?? 'Session expired.');
      case 403:
        return ForbiddenException(serverMessage ?? 'Access denied.');
      case 404:
        return NotFoundException(serverMessage ?? 'Resource not found.');
      case 409:
        return ConflictException(serverMessage ?? 'Conflict.');
      case 422:
        return UnprocessableException(
          serverMessage ?? 'Validation failed.',
          data is Map<String, dynamic> ? data['errors'] as Map<String, dynamic>? : null,
        );
      case >= 500:
        return ServerException(serverMessage ?? 'Server error.', statusCode);
      default:
        return ServerException('Unexpected error ($statusCode).', statusCode);
    }
  }

  /// Attempts to extract a human-readable message from the response body.
  static String? _extractMessage(dynamic data) {
    if (data is Map<String, dynamic>) {
      return data['message'] as String? ?? data['error'] as String?;
    }
    if (data is String && data.isNotEmpty) {
      return data;
    }
    return null;
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
