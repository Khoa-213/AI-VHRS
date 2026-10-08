/// API endpoint constants and base configuration for AI-VHRS backend.
class ApiConstants {
  ApiConstants._();

  // Base URL — override per environment via --dart-define
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.aivhrs.com/v1',
  );

  // Timeouts
  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 30);
  static const Duration sendTimeout = Duration(seconds: 60);

  // Auth
  static const String login = '/auth/login';
  static const String register = '/auth/register';
  static const String refreshToken = '/auth/refresh';
  static const String profile = '/auth/profile';
  static const String changePassword = '/auth/change-password';

  // Projects
  static const String projects = '/projects';
  static String projectById(String id) => '/projects/$id';

  // Handwriting Input
  static const String uploadImage = '/input/image-upload';
  static const String submitText = '/input/text';
  static const String submitCanvas = '/input/canvas';

  // Trajectory
  static String trajectory(String projectId) => '/projects/$projectId/trajectory';
  static String priceEstimate(String projectId) => '/projects/$projectId/price';

  // Payment
  static const String createPayment = '/payments/create';
  static const String paymentHistory = '/payments/history';
  static String paymentStatus(String paymentId) => '/payments/$paymentId/status';

  // Request Tracking
  static const String requests = '/requests';
  static String requestById(String id) => '/requests/$id';
  static String requestResult(String id) => '/requests/$id/result';
}
