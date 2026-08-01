import '../models/connection.dart';
import '../models/message.dart';
import '../models/thread.dart';
import 'api_client.dart';

class ChatService {
  final ApiClient _api;
  ChatService(this._api);

  // --- Connections ---

  Future<ConnectionRead> requestConnection({
    required int requesterId,
    required int receiverId,
    int? hookInterestId,
  }) async {
    final j = await _api.post(
      '/connections',
      query: {'requester_id': requesterId},
      body: {
        'receiver_id': receiverId,
        'hook_interest_id': ?hookInterestId,
      },
    );
    return ConnectionRead.fromJson(j as Map<String, dynamic>);
  }

  Future<ConnectionRead> updateConnection({
    required int connectionId,
    required int userId,
    required String status,
  }) async {
    final j = await _api.patch(
      '/connections/$connectionId',
      query: {'user_id': userId},
      body: {'status': status},
    );
    return ConnectionRead.fromJson(j as Map<String, dynamic>);
  }

  Future<List<ConnectionRead>> listConnections(int userId) async {
    final j = await _api.get('/connections', query: {'user_id': userId});
    return (j as List)
        .map((e) => ConnectionRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // --- Threads ---

  Future<List<ThreadRead>> listThreads(int userId) async {
    final j = await _api.get('/threads', query: {'user_id': userId});
    return (j as List)
        .map((e) => ThreadRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<MessageRead>> listMessages(int threadId, {required int userId}) async {
    final j = await _api.get(
      '/threads/$threadId/messages',
      query: {'user_id': userId},
    );
    return (j as List)
        .map((e) => MessageRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<MessageRead> sendMessage(
    int threadId, {
    required int userId,
    required String body,
    String kind = 'text',
    Map<String, dynamic>? payload,
  }) async {
    final j = await _api.post(
      '/threads/$threadId/messages',
      query: {'user_id': userId},
      body: {
        'body': body,
        'kind': kind,
        'payload': ?payload,
      },
    );
    return MessageRead.fromJson(j as Map<String, dynamic>);
  }

  Future<MessageRead> proposeAttendTogether(
    int threadId, {
    required int userId,
    required int eventId,
  }) async {
    final j = await _api.post(
      '/threads/$threadId/attend-together',
      query: {'user_id': userId},
      body: {'event_id': eventId},
    );
    return MessageRead.fromJson(j as Map<String, dynamic>);
  }

  Future<MessageRead> acceptAttendTogether(
    int threadId, {
    required int userId,
    required int messageId,
  }) async {
    final j = await _api.post(
      '/threads/$threadId/attend-together/$messageId/accept',
      query: {'user_id': userId},
    );
    return MessageRead.fromJson(j as Map<String, dynamic>);
  }
}
