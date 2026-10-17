/// API endpoint constants and base configuration for the AI-VHRS backend
/// (https://ai-vhrs.onrender.com/docs).
class ApiConstants {
  ApiConstants._();

  // Base URL — override per environment via --dart-define
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://ai-vhrs.onrender.com/api/v1',
  );

  // Timeouts. The Render free plan sleeps when idle and takes up to about a
  // minute to wake, so the first request after a pause needs the long wait.
  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 75);
  static const Duration sendTimeout = Duration(seconds: 60);

  // Auth
  static const String login = '/auth/login';
  static const String refreshToken = '/auth/refresh';
  static const String logout = '/auth/logout';
  static const String passwordResetRequest = '/auth/password-reset/request';
  static const String profile = '/me';
  static const String changePassword = '/me/change-password';

  // Technician orders, robots and QC: no backend endpoints yet. The desk
  // uses its local mock store (features/tech/data/tech_store.dart) until then.
}
