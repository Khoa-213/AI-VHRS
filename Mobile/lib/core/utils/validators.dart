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

  /// Validates password strength.
  static String? password(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required.';
    }
    if (value.length < 8) {
      return 'Password must be at least 8 characters.';
    }
    if (!RegExp(r'[A-Z]').hasMatch(value)) {
      return 'Password must contain at least one uppercase letter.';
    }
    if (!RegExp(r'[a-z]').hasMatch(value)) {
      return 'Password must contain at least one lowercase letter.';
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

  /// Validates phone number (Vietnamese format).
  static String? phoneNumber(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Phone number is required.';
    }
    final cleaned = value.replaceAll(RegExp(r'[\s\-()]'), '');
    final regex = RegExp(r'^(\+84|84|0)(3|5|7|8|9)\d{8}$');
    if (!regex.hasMatch(cleaned)) {
      return 'Please enter a valid Vietnamese phone number.';
    }
    return null;
  }

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
