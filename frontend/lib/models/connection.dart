import 'parse.dart';

/// Deprecated shim — kept only so `ConnectionRead` retains a stable set of
/// `final` fields across hot reloads. The backend `/connections` payload no
/// longer carries an `other_user` block; the frontend now hydrates
/// counterparty details on its own via `UserService.list()` +
/// `UserService.get(id)` (see `ConnectionsScreen._hydrateUsers`).
///
/// Do **not** add new call sites — read from the hydrated `UserRead` map
/// inside the screen instead. This class exists purely so the `const`
/// `ConnectionRead` constructor keeps the same shape (Dart will reject a
/// hot reload that removes a field from a `const`-constructible class).
class ConnectionOtherUser {
  final int id;
  final String name;
  final String? avatarUrl;
  final String? headline;
  final String? role;
  final String? company;

  const ConnectionOtherUser({
    required this.id,
    required this.name,
    this.avatarUrl,
    this.headline,
    this.role,
    this.company,
  });

  factory ConnectionOtherUser.fromJson(Map<String, dynamic> j) =>
      ConnectionOtherUser(
        id: parseIntOr(j['id'], 0),
        name: parseString(j['name']) ?? '',
        avatarUrl: parseString(j['avatar_url']),
        headline: parseString(j['headline']),
        role: parseString(j['role']),
        company: parseString(j['company']),
      );
}

/// Mirrors `ConnectionRead` from API_CONTRACT §20.5.
///
/// The counterparty's name/avatar is *not* on this row — the backend keeps
/// `/connections` cheap and returns only IDs. Consumers should hydrate the
/// user separately (e.g. via `UserService.list()` + a local map lookup) so
/// no per-row `GET /users/{id}` fan-out is needed for a large list.
class ConnectionRead {
  final int id;
  final int requesterId;
  final int receiverId;
  final int? hookInterestId;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// Legacy shim, always `null`. See [ConnectionOtherUser] docstring.
  /// Kept so this `const` class does not lose a field across hot reloads.
  final ConnectionOtherUser? otherUser;

  const ConnectionRead({
    required this.id,
    required this.requesterId,
    required this.receiverId,
    this.hookInterestId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.otherUser,
  });

  factory ConnectionRead.fromJson(Map<String, dynamic> j) => ConnectionRead(
        id: parseIntOr(j['id'], 0),
        requesterId: parseIntOr(j['requester_id'], 0),
        receiverId: parseIntOr(j['receiver_id'], 0),
        hookInterestId: parseInt(j['hook_interest_id']),
        status: parseString(j['status']) ?? 'pending',
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
        updatedAt: parseDate(j['updated_at']) ?? DateTime.now().toUtc(),
        // Backend may or may not send this depending on version — tolerate
        // both. Not read by any UI code today.
        otherUser: j['other_user'] is Map<String, dynamic>
            ? ConnectionOtherUser.fromJson(j['other_user'] as Map<String, dynamic>)
            : null,
      );

  int otherUserId(int selfId) =>
      requesterId == selfId ? receiverId : requesterId;

  /// True when *I* sent the request and it's still awaiting a response.
  bool isOutgoingPending(int selfId) =>
      status == 'pending' && requesterId == selfId;

  /// True when the other person sent it to me and I haven't acted yet.
  bool isIncomingPending(int selfId) =>
      status == 'pending' && receiverId == selfId;
}

const connectionStatuses = <String>[
  'pending',
  'accepted',
  'declined',
  'blocked',
];
