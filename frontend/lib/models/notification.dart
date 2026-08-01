import 'parse.dart';

/// Mirrors `NotificationRead` from API_CONTRACT §20.8.
class NotificationRead {
  final int id;
  final int userId;
  final String type;
  final String title;
  final String? body;
  final String? deepLink;
  final DateTime? readAt;
  final DateTime createdAt;

  const NotificationRead({
    required this.id,
    required this.userId,
    required this.type,
    required this.title,
    this.body,
    this.deepLink,
    this.readAt,
    required this.createdAt,
  });

  factory NotificationRead.fromJson(Map<String, dynamic> j) => NotificationRead(
        id: parseIntOr(j['id'], 0),
        userId: parseIntOr(j['user_id'], 0),
        type: parseString(j['type']) ?? 'info',
        title: parseString(j['title']) ?? '',
        body: parseString(j['body']),
        deepLink: parseString(j['deep_link']),
        readAt: parseDate(j['read_at']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
      );

  bool get isRead => readAt != null;
}

/// Types the backend emits (API_CONTRACT §19.5).
const notificationTypes = <String>[
  'connection_request',
  'connection_accepted',
  'dm_new',
  'mission_completed',
  'event_starting_soon',
];
