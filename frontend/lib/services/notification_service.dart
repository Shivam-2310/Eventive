import '../models/notification.dart';
import 'api_client.dart';

class NotificationService {
  final ApiClient _api;
  NotificationService(this._api);

  Future<List<NotificationRead>> list({
    required int userId,
    bool unreadOnly = false,
  }) async {
    final j = await _api.get('/notifications', query: {
      'user_id': userId,
      'unread_only': unreadOnly,
    });
    return (j as List)
        .map((e) => NotificationRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> markRead(int notifId, {required int userId}) async {
    await _api.post('/notifications/$notifId/read', query: {'user_id': userId});
  }
}
