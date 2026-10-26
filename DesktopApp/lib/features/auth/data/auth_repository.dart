import '../../../core/constants/api_constants.dart';
import '../../../core/network/dio_client.dart';
import '../domain/models/user.dart';

typedef AuthSession = ({String accessToken, String refreshToken, User user});

/// Authentication and profile calls (backend `/auth/*` and `/me`).
abstract class AuthRepository {
  /// `POST /auth/login`
  Future<AuthSession> login({required String email, required String password});

  /// `POST /auth/logout`. Revokes this session's access and refresh tokens.
  Future<void> logout();

  /// `POST /auth/password-reset/request`. Always succeeds, whether or not the email exists.
  Future<void> requestPasswordReset(String email);

  /// `GET /me`
  Future<User> getProfile();

  /// `PATCH /me`. Only the fields given are changed.
  Future<User> updateProfile({String? fullName, String? phoneNumber});

  /// `POST /me/change-password`. Signs out the other devices.
  Future<void> changePassword({required String currentPassword, required String newPassword});
}

class AuthRepositoryImpl implements AuthRepository {
  final DioClient _client;

  AuthRepositoryImpl({required DioClient client}) : _client = client;

  @override
  Future<AuthSession> login({required String email, required String password}) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConstants.login,
      data: {'email': email, 'password': password},
    );
    return (
      accessToken: response['access_token'] as String,
      refreshToken: response['refresh_token'] as String,
      user: User.fromJson(response['account'] as Map<String, dynamic>),
    );
  }

  @override
  Future<void> logout() => _client.post<void>(ApiConstants.logout);

  @override
  Future<void> requestPasswordReset(String email) =>
      _client.post<void>(ApiConstants.passwordResetRequest, data: {'email': email});

  @override
  Future<User> getProfile() async {
    final response = await _client.get<Map<String, dynamic>>(ApiConstants.profile);
    return User.fromJson(response);
  }

  @override
  Future<User> updateProfile({String? fullName, String? phoneNumber}) async {
    final response = await _client.patch<Map<String, dynamic>>(
      ApiConstants.profile,
      data: {
        if (fullName != null) 'full_name': fullName,
        if (phoneNumber != null) 'phone': phoneNumber,
      },
    );
    return User.fromJson(response);
  }

  @override
  Future<void> changePassword({required String currentPassword, required String newPassword}) async {
    await _client.post<void>(
      ApiConstants.changePassword,
      data: {'current_password': currentPassword, 'new_password': newPassword},
    );
  }
}
