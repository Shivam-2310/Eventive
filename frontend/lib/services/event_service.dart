import '../models/event.dart';
import 'api_client.dart';

class EventService {
  final ApiClient _api;
  EventService(this._api);

  Future<EventRead> create(EventCreate body) async {
    final j = await _api.post('/events', body: body.toJson());
    return EventRead.fromJson(j as Map<String, dynamic>);
  }

  Future<List<EventRead>> list({
    String? status,
    String? track,
    String? day,
    int? speakerId,
    int? interestId,
    int limit = 50,
    int offset = 0,
  }) async {
    final j = await _api.get('/events', query: {
      'status': status,
      'track': track,
      'day': day,
      'speaker_id': speakerId,
      'interest_id': interestId,
      'limit': limit,
      'offset': offset,
    });
    return (j as List)
        .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<EventDiscoverPage> discover({
    required int userId,
    int? cursor,
    int limit = 10,
  }) async {
    final j = await _api.get('/events/discover', query: {
      'user_id': userId,
      'cursor': cursor,
      'limit': limit,
    });
    return EventDiscoverPage.fromJson(j as Map<String, dynamic>);
  }

  /// Interest-first discovery deck (§7.3).
  ///
  /// Same card shape as [discover] — only the ordering differs. Backend uses
  /// the user's interests + vec similarity to rank events; the response omits
  /// `next_cursor` because there is no natural pagination cursor for a scored
  /// list.
  Future<EventDiscoverPage> discoverForYou({
    required int userId,
    int limit = 10,
  }) async {
    final j = await _api.get('/events/discover/for-you', query: {
      'user_id': userId,
      'limit': limit,
    });
    return EventDiscoverPage.fromJson(j as Map<String, dynamic>);
  }

  Future<EventRead> get(int id) async {
    final j = await _api.get('/events/$id');
    return EventRead.fromJson(j as Map<String, dynamic>);
  }

  Future<EventRead> update(int id, Map<String, dynamic> body) async {
    final j = await _api.patch('/events/$id', body: body);
    return EventRead.fromJson(j as Map<String, dynamic>);
  }

  Future<void> delete(int id) async {
    await _api.delete('/events/$id');
  }

  Future<Map<String, dynamic>> assignSpeaker(
    int eventId, {
    required int speakerId,
    String role = 'panelist',
  }) async {
    final j = await _api.post(
      '/events/$eventId/speakers',
      body: {'speaker_id': speakerId, 'role': role},
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> setInterests(int eventId, List<int> interestIds) async {
    final j = await _api.post(
      '/events/$eventId/interests',
      body: {'interest_ids': interestIds},
    );
    return Map<String, dynamic>.from(j as Map);
  }

  /// Record a like/pass/comment against a specific prompt slot of an event card.
  ///
  /// [promptType] must be one of [eventPromptTypes] (§7.9).
  Future<Map<String, dynamic>> react(
    int eventId, {
    required int userId,
    required String promptType,
    int? promptRefId,
    required String reaction,
    String? commentText,
  }) async {
    final j = await _api.post(
      '/events/$eventId/react',
      query: {'user_id': userId},
      body: {
        'prompt_type': promptType,
        'prompt_ref_id': promptRefId,
        'reaction': reaction,
        'comment_text': commentText,
      },
    );
    return Map<String, dynamic>.from(j as Map);
  }

  /// Coarser interaction — like/save/rsvp/etc. (§7.10).
  ///
  /// Idempotent: the backend enforces uniqueness on `(user_id, event_id, type)`
  /// so repeated calls return the same row.
  Future<Map<String, dynamic>> interaction(
    int eventId, {
    required int userId,
    required String type,
  }) async {
    final j = await _api.post(
      '/events/$eventId/interactions',
      query: {'user_id': userId},
      body: {'type': type},
    );
    return Map<String, dynamic>.from(j as Map);
  }

  /// Toggle-off the coarser interaction — pair with [interaction] to power
  /// Save / Un-save style buttons. Safe to call when the row does not exist;
  /// the response always reports `active: false`.
  Future<Map<String, dynamic>> removeInteraction(
    int eventId, {
    required int userId,
    required String type,
  }) async {
    final j = await _api.delete(
      '/events/$eventId/interactions',
      query: {'user_id': userId, 'type': type},
    );
    return Map<String, dynamic>.from(j as Map);
  }

  /// Compact `{event_id: [type, ...]}` map for the given user. Used to seed
  /// the app-wide `UserInteractionsStore` on login / hard refresh.
  Future<Map<int, Set<String>>> userInteractionMap(int userId) async {
    final j = await _api.get('/users/$userId/event-interactions');
    final events = (j as Map<String, dynamic>)['events'] as Map<String, dynamic>? ?? const {};
    final out = <int, Set<String>>{};
    events.forEach((k, v) {
      final id = int.tryParse(k);
      if (id == null) return;
      out[id] = ((v as List).map((e) => e.toString())).toSet();
    });
    return out;
  }

  /// Hydrated events grouped by interaction bucket (§profile activity).
  Future<Map<String, List<EventRead>>> userEventBuckets(int userId) async {
    final j = await _api.get('/users/$userId/events');
    final buckets = (j as Map<String, dynamic>)['buckets'] as Map<String, dynamic>? ?? const {};
    final out = <String, List<EventRead>>{};
    buckets.forEach((k, v) {
      out[k] = (v as List)
          .map((e) => EventRead.fromJson(e as Map<String, dynamic>))
          .toList();
    });
    return out;
  }

  Future<Map<String, dynamic>> refreshVibe(int eventId) async {
    final j = await _api.post('/events/$eventId/vibe/refresh');
    return Map<String, dynamic>.from(j as Map);
  }
}
