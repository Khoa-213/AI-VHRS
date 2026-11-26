import '../../../core/network/dio_client.dart';
import '../domain/notification.dart';

/// `/me/notifications`, one to one with FE `services/notifications.ts` (contract in `BE/docs/FE_API_GUIDE.md` 7j).
class NotificationApi {
  final DioClient _client;
  NotificationApi({required DioClient client}) : _client = client;

  Future<NotificationPage> list({int? beforeId, int limit = 20}) async => NotificationPage.fromJson(await _client.get<Map<String, dynamic>>(
        '/me/notifications',
        queryParameters: {'limit': limit, if (beforeId != null) 'before_id': beforeId},
      ));

  Future<void> markRead(int id) => _client.post<Map<String, dynamic>>('/me/notifications/$id/read');

  Future<void> markAllRead() => _client.post<Map<String, dynamic>>('/me/notifications/read-all');
}
