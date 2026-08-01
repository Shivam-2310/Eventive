import 'parse.dart';

/// Mirrors backend `UserRead` — see API_CONTRACT §4.1.
class UserRead {
  final int id;
  final String email;
  final String name;
  final String? avatarUrl;
  final String? headline;
  final String? company;
  final String? role;
  final String? timezone;
  final String? blurb;
  final bool optInNetworking;
  final bool isAdmin;
  final DateTime createdAt;
  final DateTime? lastSeenAt;

  const UserRead({
    required this.id,
    required this.email,
    required this.name,
    this.avatarUrl,
    this.headline,
    this.company,
    this.role,
    this.timezone,
    this.blurb,
    required this.optInNetworking,
    required this.isAdmin,
    required this.createdAt,
    this.lastSeenAt,
  });

  factory UserRead.fromJson(Map<String, dynamic> j) => UserRead(
        id: parseIntOr(j['id'], 0),
        email: parseString(j['email']) ?? '',
        name: parseString(j['name']) ?? '',
        avatarUrl: parseString(j['avatar_url']),
        headline: parseString(j['headline']),
        company: parseString(j['company']),
        role: parseString(j['role']),
        timezone: parseString(j['timezone']),
        blurb: parseString(j['blurb']),
        optInNetworking: parseBool(j['opt_in_networking'], fallback: true),
        isAdmin: parseBool(j['is_admin']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
        lastSeenAt: parseDate(j['last_seen_at']),
      );
}

/// Body for `POST /users`.
class UserCreate {
  final String email;
  final String name;
  final String? avatarUrl;
  final String? headline;
  final String? company;
  final String? role;
  final String? timezone;
  final String? blurb;
  final bool optInNetworking;
  final bool isAdmin;

  const UserCreate({
    required this.email,
    required this.name,
    this.avatarUrl,
    this.headline,
    this.company,
    this.role,
    this.timezone,
    this.blurb,
    this.optInNetworking = true,
    this.isAdmin = false,
  });

  Map<String, dynamic> toJson() => {
        'email': email,
        'name': name,
        if (avatarUrl != null) 'avatar_url': avatarUrl,
        if (headline != null) 'headline': headline,
        if (company != null) 'company': company,
        if (role != null) 'role': role,
        if (timezone != null) 'timezone': timezone,
        if (blurb != null) 'blurb': blurb,
        'opt_in_networking': optInNetworking,
        'is_admin': isAdmin,
      };
}

/// Body for `PATCH /users/{id}` — every field optional.
class UserUpdate {
  final String? name;
  final String? avatarUrl;
  final String? headline;
  final String? company;
  final String? role;
  final String? timezone;
  final String? blurb;
  final bool? optInNetworking;

  const UserUpdate({
    this.name,
    this.avatarUrl,
    this.headline,
    this.company,
    this.role,
    this.timezone,
    this.blurb,
    this.optInNetworking,
  });

  Map<String, dynamic> toJson() {
    final m = <String, dynamic>{};
    if (name != null) m['name'] = name;
    if (avatarUrl != null) m['avatar_url'] = avatarUrl;
    if (headline != null) m['headline'] = headline;
    if (company != null) m['company'] = company;
    if (role != null) m['role'] = role;
    if (timezone != null) m['timezone'] = timezone;
    if (blurb != null) m['blurb'] = blurb;
    if (optInNetworking != null) m['opt_in_networking'] = optInNetworking;
    return m;
  }
}

/// Mirrors `GET /users/{id}/wrapped` response.
class UserWrapped {
  final DateTime generatedAt;
  final int sessionsAttended;
  final int connectionsMade;
  final int reelsPosted;
  final int totalWatchMs;
  final int uniqueRoomsVisited;
  final String? favoriteSpeaker;
  final List<String> topTopics;
  final int notificationsReceived;

  const UserWrapped({
    required this.generatedAt,
    required this.sessionsAttended,
    required this.connectionsMade,
    required this.reelsPosted,
    required this.totalWatchMs,
    required this.uniqueRoomsVisited,
    this.favoriteSpeaker,
    required this.topTopics,
    required this.notificationsReceived,
  });

  factory UserWrapped.fromJson(Map<String, dynamic> j) => UserWrapped(
        generatedAt: parseDate(j['generated_at']) ?? DateTime.now().toUtc(),
        sessionsAttended: parseIntOr(j['sessions_attended'], 0),
        connectionsMade: parseIntOr(j['connections_made'], 0),
        reelsPosted: parseIntOr(j['reels_posted'], 0),
        totalWatchMs: parseIntOr(j['total_watch_ms'], 0),
        uniqueRoomsVisited: parseIntOr(j['unique_rooms_visited'], 0),
        favoriteSpeaker: parseString(j['favorite_speaker']),
        topTopics: parseStringList(j['top_topics']),
        notificationsReceived: parseIntOr(j['notifications_received'], 0),
      );
}
