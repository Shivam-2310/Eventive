import 'parse.dart';

/// Mirrors `ThreadRead` from API_CONTRACT §20.6.
class ThreadRead {
  final int id;
  final int? connectionId;
  final int? eventId;
  final String? title;
  final DateTime createdAt;
  final List<int> participantIds;

  const ThreadRead({
    required this.id,
    this.connectionId,
    this.eventId,
    this.title,
    required this.createdAt,
    required this.participantIds,
  });

  factory ThreadRead.fromJson(Map<String, dynamic> j) => ThreadRead(
        id: parseIntOr(j['id'], 0),
        connectionId: parseInt(j['connection_id']),
        eventId: parseInt(j['event_id']),
        title: parseString(j['title']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
        participantIds: (j['participant_ids'] is List)
            ? (j['participant_ids'] as List)
                .map((e) => parseIntOr(e, 0))
                .where((e) => e != 0)
                .toList()
            : const [],
      );

  int? otherParticipantId(int selfId) {
    for (final id in participantIds) {
      if (id != selfId) return id;
    }
    return null;
  }
}
