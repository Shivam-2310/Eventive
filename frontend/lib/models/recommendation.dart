import 'parse.dart';

/// One row from `GET /recommendations/people/{user_id}`.
class PersonRecommendation {
  final int otherUserId;
  final String name;
  final String? headline;
  final double score;
  final List<String> reasons;

  const PersonRecommendation({
    required this.otherUserId,
    required this.name,
    this.headline,
    required this.score,
    required this.reasons,
  });

  factory PersonRecommendation.fromJson(Map<String, dynamic> j) =>
      PersonRecommendation(
        otherUserId: parseIntOr(j['other_user_id'], 0),
        name: parseString(j['name']) ?? '',
        headline: parseString(j['headline']),
        score: parseDouble(j['score']) ?? 0.0,
        reasons: parseStringList(j['reasons']),
      );
}

/// One row from `GET /recommendations/events/{user_id}`.
class EventRecommendation {
  final int eventId;
  final String title;
  final String? track;
  final DateTime? startTime;
  final double score;
  final String? reason;

  const EventRecommendation({
    required this.eventId,
    required this.title,
    this.track,
    this.startTime,
    required this.score,
    this.reason,
  });

  factory EventRecommendation.fromJson(Map<String, dynamic> j) =>
      EventRecommendation(
        eventId: parseIntOr(j['event_id'], 0),
        title: parseString(j['title']) ?? '',
        track: parseString(j['track']),
        startTime: parseDate(j['start_time']),
        score: parseDouble(j['score']) ?? 0.0,
        reason: parseString(j['reason']),
      );
}
