/// Form field validators for the AI-VHRS application.
/// All validators return null on success or an error message string on failure.
class Validators {
  Validators._();

  /// Validates that a field is not empty.
  static String? required(String? value, [String fieldName = 'This field']) {
    if (value == null || value.trim().isEmpty) {
      return '$fieldName is required.';
    }
    return null;
  }

  /// Validates email format.
  static String? email(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Email is required.';
    }
    final regex = RegExp(
      r'^[a-zA-Z0-9.!#$%&*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}'
      r'[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$',
    );
    if (!regex.hasMatch(value.trim())) {
      return 'Please enter a valid email address.';
    }
    return null;
  }

  /// Validates password strength. Same rule as the backend: 8 to 72
  /// characters with at least one letter and one digit.
  static String? password(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required.';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (value.length > 72) {
      return 'Password must be at most 72 characters.';
    }
    if (!RegExp(r'[A-Za-z]').hasMatch(value)) {
      return 'Password must contain at least one letter.';
    }
    if (!RegExp(r'[0-9]').hasMatch(value)) {
      return 'Password must contain at least one number.';
    }
    return null;
  }

  /// Validates that the confirmation password matches.
  static String? confirmPassword(String? value, String password) {
    final requiredError = required(value, 'Confirm password');
    if (requiredError != null) return requiredError;
    if (value != password) {
      return 'Passwords do not match.';
    }
    return null;
  }

  /// Strips spaces, dashes and brackets: "090 123-4567" → "0901234567".
  static String cleanPhone(String value) => value.replaceAll(RegExp(r'[\s\-()]'), '');

  /// Validates phone number (Vietnamese format, same rule as the backend:
  /// 0 or +84 followed by 9 digits).
  static String? phoneNumber(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Phone number is required.';
    }
    if (!RegExp(r'^(0|\+84)\d{9}$').hasMatch(cleanPhone(value))) {
      return 'Please enter a valid Vietnamese phone number.';
    }
    return null;
  }

  /// Like [phoneNumber], but an empty field is allowed.
  static String? optionalPhoneNumber(String? value) =>
      value == null || value.trim().isEmpty ? null : phoneNumber(value);

  /// Validates string length within bounds.
  static String? length(String? value, {int? min, int? max, String fieldName = 'This field'}) {
    if (value == null) return null;
    if (min != null && value.length < min) {
      return '$fieldName must be at least $min characters.';
    }
    if (max != null && value.length > max) {
      return '$fieldName must not exceed $max characters.';
    }
    return null;
  }

  /// Validates a numeric value.
  static String? numeric(String? value, [String fieldName = 'This field']) {
    if (value == null || value.trim().isEmpty) return null;
    if (double.tryParse(value) == null) {
      return '$fieldName must be a valid number.';
    }
    return null;
  }

  /// Composes multiple validators; returns the first error encountered.
  static String? compose(String? value, List<String? Function(String?)> validators) {
    for (final validator in validators) {
      final error = validator(value);
      if (error != null) return error;
    }
    return null;
  }
}
