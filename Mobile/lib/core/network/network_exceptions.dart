import 'package:freezed_annotation/freezed_annotation.dart';

/// Sealed class representing all possible network exception types.
/// Provides exhaustive pattern matching for error handling across the app.
@immutable
sealed class NetworkException implements Exception {
  const NetworkException();

  String get message;
}

class UnauthorizedException extends NetworkException {
  @override
  final String message;
  const UnauthorizedException([this.message = 'Session expired. Please log in again.']);
}

class ForbiddenException extends NetworkException {
  @override
  final String message;
  const ForbiddenException([this.message = 'You do not have permission to perform this action.']);
}

class NotFoundException extends NetworkException {
  @override
  final String message;
  const NotFoundException([this.message = 'The requested resource was not found.']);
}

class ServerException extends NetworkException {
  @override
  final String message;
  final int? statusCode;
  const ServerException([this.message = 'A server error occurred. Please try again later.', this.statusCode]);
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
  const BadRequestException([this.message = 'Invalid request. Please check your input.', this.errors]);
}

class ConflictException extends NetworkException {
  @override
  final String message;
  const ConflictException([this.message = 'A conflict occurred with the current state.']);
}

class UnprocessableException extends NetworkException {
  @override
  final String message;
  final Map<String, dynamic>? validationErrors;
  const UnprocessableException([this.message = 'Validation failed.', this.validationErrors]);
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
