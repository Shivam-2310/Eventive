import '../models/ai.dart';
import 'api_client.dart';

class AiService {
  final ApiClient _api;
  AiService(this._api);

  Future<List<AiSuggestion>> suggestions(int userId) async {
    final j = await _api.get('/ai/suggestions', query: {'user_id': userId});
    return (j as List)
        .map((e) => AiSuggestion.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Consume `POST /ai/chat` as an SSE stream, yielding one [AiChatFrame] per
  /// server frame (§14.2). Ordering is `intent → …citations/tool/sql… →
  /// chunk(s) → done`.
  Stream<AiChatFrame> chat({
    required int userId,
    required String message,
    int? sessionId,
  }) async* {
    final raw = _api.sseStreamPost(
      '/ai/chat',
      query: {'user_id': userId},
      body: {
        'message': message,
        'session_id': sessionId,
      },
    );
    await for (final frame in raw) {
      yield AiChatFrame.fromRaw(frame);
    }
  }

  Future<Map<String, dynamic>> rebuildRagChunks() async {
    final j = await _api.post('/ai/rag/backfill');
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> backfillAllEmbeddings() async {
    final j = await _api.post('/ai/embed/backfill-all');
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> backfillUser(int userId) async {
    final j = await _api.post('/ai/embed/user/$userId');
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> backfillEvent(int eventId) async {
    final j = await _api.post('/ai/embed/event/$eventId');
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> backfillInterest(int interestId) async {
    final j = await _api.post('/ai/embed/interest/$interestId');
    return Map<String, dynamic>.from(j as Map);
  }

  Future<List<Map<String, dynamic>>> nearestUser(int userId, {int k = 5}) async {
    final j = await _api.get('/ai/embed/nearest/user/$userId', query: {'k': k});
    return (j as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> nearestEvent(int eventId, {int k = 5}) async {
    final j = await _api.get('/ai/embed/nearest/event/$eventId', query: {'k': k});
    return (j as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }
}
