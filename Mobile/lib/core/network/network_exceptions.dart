import 'package:flutter/foundation.dart';

/// Sealed class representing all possible network exception types.
/// Provides exhaustive pattern matching for error handling across the app.
@immutable
sealed class NetworkException implements Exception {
  const NetworkException();

  String get message;

  /// Backend error code from `{"error": {"code", "message", "details"}}`,
  /// e.g. `INVALID_CREDENTIALS`. Null when the error did not come from the API.
  String? get code => null;
}

class UnauthorizedException extends NetworkException {
  @override
  final String message;
  @override
  final String? code;
  const UnauthorizedException([this.message = 'Session expired. Please log in again.', this.code]);
}

class ForbiddenException extends NetworkException {
  @override
  final String message;
  @override
  final String? code;
  const ForbiddenException([this.message = 'You do not have permission to perform this action.', this.code]);
}

class NotFoundException extends NetworkException {
  @override
  final String message;
  @override
  final String? code;
  const NotFoundException([this.message = 'The requested resource was not found.', this.code]);
}

class ServerException extends NetworkException {
  @override
  final String message;
  final int? statusCode;
  @override
  final String? code;
  const ServerException([this.message = 'A server error occurred. Please try again later.', this.statusCode, this.code]);
}

class TimeoutException extends NetworkException {
  @override
  final String message;
  const TimeoutException([this.message = 'Connection timed out. Please check your internet connection.']);
}

class NoInternetException extends NetworkException {
  @override
  final String message;
  const NoInternetException([this.message = 'No internet connection. Please check your network settings.']);
}

class BadRequestException extends NetworkException {
  @override
  final String message;
  final Map<String, dynamic>? errors;
  @override
  final String? code;
  const BadRequestException([this.message = 'Invalid request. Please check your input.', this.errors, this.code]);
}

class ConflictException extends NetworkException {
  @override
  final String message;
  @override
  final String? code;
  const ConflictException([this.message = 'A conflict occurred with the current state.', this.code]);
}

class UnprocessableException extends NetworkException {
  @override
  final String message;
  /// Field name → message, from the backend's `details: [{field, message}]`.
  final Map<String, dynamic>? validationErrors;
  @override
  final String? code;
  const UnprocessableException([this.message = 'Validation failed.', this.validationErrors, this.code]);
}

class UnknownException extends NetworkException {
  @override
  final String message;
  final Object? originalError;
  const UnknownException([this.message = 'An unexpected error occurred.', this.originalError]);
}

class CancelException extends NetworkException {
  @override
  final String message;
  const CancelException([this.message = 'Request was cancelled.']);
}

/// 423 (account temporarily locked) and 429 (too many requests).
class TooManyAttemptsException extends NetworkException {
  @override
  final String message;
  @override
  final String? code;

  /// Seconds until the client may try again, when the server says so.
  final int? retryAfterSeconds;
  const TooManyAttemptsException([this.message = 'Too many attempts. Please try again later.', this.code, this.retryAfterSeconds]);
}
