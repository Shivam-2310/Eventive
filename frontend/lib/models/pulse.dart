import 'parse.dart';

class TrendingEvent {
  final int eventId;
  final String title;
  final int interactions;

  const TrendingEvent({
    required this.eventId,
    required this.title,
    required this.interactions,
  });

  factory TrendingEvent.fromJson(Map<String, dynamic> j) => TrendingEvent(
        eventId: parseIntOr(j['event_id'], 0),
        title: parseString(j['title']) ?? '',
        interactions: parseIntOr(j['interactions'], 0),
      );
}

/// Mirrors `GET /admin/pulse/snapshot` — see API_CONTRACT §16.1.
class PulseSnapshot {
  final DateTime generatedAt;
  final int likesToday;
  final int reelLikesToday;
  final int totalUsers;
  final int totalAcceptedConnections;
  final int activeDmThreadsLast24h;
  final List<TrendingEvent> trendingEvents;
  final double avgInteractionsPerEvent;

  const PulseSnapshot({
    required this.generatedAt,
    required this.likesToday,
    required this.reelLikesToday,
    required this.totalUsers,
    required this.totalAcceptedConnections,
    required this.activeDmThreadsLast24h,
    required this.trendingEvents,
    required this.avgInteractionsPerEvent,
  });

  factory PulseSnapshot.fromJson(Map<String, dynamic> j) => PulseSnapshot(
        generatedAt: parseDate(j['generated_at']) ?? DateTime.now().toUtc(),
        likesToday: parseIntOr(j['likes_today'], 0),
        reelLikesToday: parseIntOr(j['reel_likes_today'], 0),
        totalUsers: parseIntOr(j['total_users'], 0),
        totalAcceptedConnections:
            parseIntOr(j['total_accepted_connections'], 0),
        activeDmThreadsLast24h: parseIntOr(j['active_dm_threads_last_24h'], 0),
        trendingEvents: parseList(j['trending_events'],
            (e) => TrendingEvent.fromJson(e as Map<String, dynamic>)),
        avgInteractionsPerEvent:
            parseDouble(j['avg_interactions_per_event']) ?? 0.0,
      );
}

class AuditLogEntry {
  final int id;
  final int? actorUserId;
  final String action;
  final String? targetType;
  final String? targetId;
  final String? payload;
  final DateTime createdAt;

  const AuditLogEntry({
    required this.id,
    this.actorUserId,
    required this.action,
    this.targetType,
    this.targetId,
    this.payload,
    required this.createdAt,
  });

  factory AuditLogEntry.fromJson(Map<String, dynamic> j) => AuditLogEntry(
        id: parseIntOr(j['id'], 0),
        actorUserId: parseInt(j['actor_user_id']),
        action: parseString(j['action']) ?? '',
        targetType: parseString(j['target_type']),
        targetId: parseString(j['target_id']),
        payload: parseString(j['payload']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
      );
}
