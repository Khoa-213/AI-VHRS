import '../../../core/constants/api_constants.dart';
import '../../../core/network/dio_client.dart';
import '../domain/models/user.dart';

/// Repository interface for authentication operations.
abstract class AuthRepository {
  Future<({String accessToken, String refreshToken, User user})> login({
    required String email,
    required String password,
  });

  Future<({String accessToken, String refreshToken, User user})> register({
    required String email,
    required String password,
    required String fullName,
    String? phoneNumber,
  });

  Future<User> getProfile();
  Future<User> updateProfile({String? fullName, String? phoneNumber});
  Future<void> changePassword({required String currentPassword, required String newPassword});
}

/// Concrete implementation of [AuthRepository] using Dio.
class AuthRepositoryImpl implements AuthRepository {
  final DioClient _client;

  AuthRepositoryImpl({required DioClient client}) : _client = client;

  @override
  Future<({String accessToken, String refreshToken, User user})> login({
    required String email,
    required String password,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConstants.login,
      data: {'email': email, 'password': password},
    );

    return (
      accessToken: response['access_token'] as String,
      refreshToken: response['refresh_token'] as String,
      user: User.fromJson(response['user'] as Map<String, dynamic>),
    );
  }

  @override
  Future<({String accessToken, String refreshToken, User user})> register({
    required String email,
    required String password,
    required String fullName,
    String? phoneNumber,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConstants.register,
      data: {
        'email': email,
        'password': password,
        'full_name': fullName,
        if (phoneNumber != null) 'phone_number': phoneNumber,
      },
    );

    return (
      accessToken: response['access_token'] as String,
      refreshToken: response['refresh_token'] as String,
      user: User.fromJson(response['user'] as Map<String, dynamic>),
    );
  }

  @override
  Future<User> getProfile() async {
    final response = await _client.get<Map<String, dynamic>>(ApiConstants.profile);
    return User.fromJson(response);
  }

  @override
  Future<User> updateProfile({String? fullName, String? phoneNumber}) async {
    final response = await _client.put<Map<String, dynamic>>(
      ApiConstants.profile,
      data: {
        if (fullName != null) 'full_name': fullName,
        if (phoneNumber != null) 'phone_number': phoneNumber,
      },
    );
    return User.fromJson(response);
  }

  @override
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _client.post(
      ApiConstants.changePassword,
      data: {
        'current_password': currentPassword,
        'new_password': newPassword,
      },
    );
  }
}
