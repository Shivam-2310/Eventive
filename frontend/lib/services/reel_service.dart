import '../models/reel.dart';
import 'api_client.dart';

class ReelService {
  final ApiClient _api;
  ReelService(this._api);

  Future<Map<String, dynamic>> upload({
    required int userId,
    required List<int> bytes,
    required String filename,
    int? eventId,
    int? speakerId,
    String? caption,
  }) async {
    final fields = <String, String>{};
    if (eventId != null) fields['event_id'] = eventId.toString();
    if (speakerId != null) fields['speaker_id'] = speakerId.toString();
    if (caption != null && caption.isNotEmpty) fields['caption'] = caption;
    final j = await _api.uploadMultipart(
      '/reels',
      query: {'user_id': userId},
      fileField: 'file',
      bytes: bytes,
      filename: filename,
      fields: fields,
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<List<ReelFeedItem>> feed({
    required int userId,
    int? cursor,
    int limit = 20,
  }) async {
    final j = await _api.get('/reels/feed', query: {
      'user_id': userId,
      'cursor': cursor,
      'limit': limit,
    });
    return (j as List)
        .map((e) => ReelFeedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ReelRead> get(int reelId) async {
    final j = await _api.get('/reels/$reelId');
    return ReelRead.fromJson(j as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> interaction(
    int reelId, {
    required int userId,
    required String type,
    int? watchMs,
  }) async {
    final j = await _api.post(
      '/reels/$reelId/interactions',
      query: {'user_id': userId},
      body: {
        'type': type,
        'watch_ms': ?watchMs,
      },
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<void> delete(int reelId, {required int userId}) async {
    await _api.delete('/reels/$reelId', query: {'user_id': userId});
  }

  /// Convenience: absolute URL for `video_url`/`thumbnail_url` (they are
  /// returned as relative signed paths beginning with `/media/blob?...`).
  String absoluteMediaUrl(String pathOrUrl) {
    if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
      return pathOrUrl;
    }
    return '${_api.baseUrl}$pathOrUrl';
  }
}
