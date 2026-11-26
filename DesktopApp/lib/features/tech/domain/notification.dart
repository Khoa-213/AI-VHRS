/// In-app notifications (`GET /me/notifications`, FE `services/notifications.ts`). Titles and bodies are Vietnamese text
/// written by the backend and shown as data. For a technician: a job assigned (`JOB_ASSIGNED`) or cancelled (`JOB_CANCELLED`).
library;

class AppNotification {
  final int id;
  final int? orderId;
  final String type;
  final String? msgCode;
  final String title;
  final String body;
  final bool isRead;
  final DateTime createdAt;

  const AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.isRead,
    required this.createdAt,
    this.orderId,
    this.msgCode,
  });

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: j['id'] as int,
        orderId: j['order_id'] as int?,
        type: j['type'] as String? ?? 'SYSTEM',
        msgCode: j['msg_code'] as String?,
        title: j['title'] as String? ?? '',
        body: j['body'] as String? ?? '',
        isRead: j['is_read'] as bool? ?? false,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  AppNotification read() =>
      AppNotification(id: id, orderId: orderId, type: type, msgCode: msgCode, title: title, body: body, isRead: true, createdAt: createdAt);
}

class NotificationPage {
  final List<AppNotification> items;
  final int unreadCount;

  /// Pass as `beforeId` for the next page; null when there is no more.
  final int? nextBeforeId;
  const NotificationPage({required this.items, required this.unreadCount, this.nextBeforeId});

  factory NotificationPage.fromJson(Map<String, dynamic> j) => NotificationPage(
        items: [for (final n in (j['items'] as List<dynamic>? ?? const [])) AppNotification.fromJson(n as Map<String, dynamic>)],
        unreadCount: j['unread_count'] as int? ?? 0,
        nextBeforeId: j['next_before_id'] as int?,
      );
}
