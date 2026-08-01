import 'parse.dart';

/// Mirrors `MissionRead` from API_CONTRACT §20.9.
class MissionRead {
  final int id;
  final String title;
  final String? description;
  final Map<String, dynamic> rule;
  final int points;
  final String? badgeIconUrl;
  final bool active;
  final DateTime createdAt;

  const MissionRead({
    required this.id,
    required this.title,
    this.description,
    required this.rule,
    required this.points,
    this.badgeIconUrl,
    required this.active,
    required this.createdAt,
  });

  factory MissionRead.fromJson(Map<String, dynamic> j) => MissionRead(
        id: parseIntOr(j['id'], 0),
        title: parseString(j['title']) ?? '',
        description: parseString(j['description']),
        rule: j['rule'] is Map
            ? Map<String, dynamic>.from(j['rule'] as Map)
            : const {},
        points: parseIntOr(j['points'], 0),
        badgeIconUrl: parseString(j['badge_icon_url']),
        active: parseBool(j['active'], fallback: true),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
      );
}

/// Mirrors `MissionProgress` from `GET /missions/me`.
class MissionProgress {
  final MissionRead mission;
  final int? count;
  final int? target;
  final DateTime? completedAt;
  final int pointsAwarded;

  const MissionProgress({
    required this.mission,
    this.count,
    this.target,
    this.completedAt,
    required this.pointsAwarded,
  });

  factory MissionProgress.fromJson(Map<String, dynamic> j) {
    final progress = j['progress'];
    int? count;
    int? target;
    if (progress is Map) {
      count = parseInt(progress['count']);
      target = parseInt(progress['target']);
    }
    return MissionProgress(
      mission: MissionRead.fromJson(j['mission'] as Map<String, dynamic>),
      count: count,
      target: target,
      completedAt: parseDate(j['completed_at']),
      pointsAwarded: parseIntOr(j['points_awarded'], 0),
    );
  }

  bool get isCompleted => completedAt != null;
  double get ratio {
    if (count == null || target == null || target == 0) return 0;
    return (count! / target!).clamp(0.0, 1.0);
  }
}

const missionRuleTypes = <String>[
  'attend_track',
  'like_reels',
  'make_connections',
  'like_events',
];
