import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/connection.dart';
import '../../models/event.dart';
import '../../models/notification.dart';
import '../../models/thread.dart';
import '../../models/user.dart';
import '../../services/services.dart';
import '../../services/ws_service.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';
import '../connections/chat_screen.dart';
import '../connections/threads_screen.dart';
import '../eventiveconnect/detail/event_sheet.dart';
import '../missions/missions_screen.dart';

/// Inbox for `GET /notifications` + live pushes over `WS /ws/notifications`.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool _loading = true;
  bool _unreadOnly = false;
  List<NotificationRead> _items = const [];
  ReconnectingWebSocket? _ws;
  StreamSubscription<Map<String, dynamic>>? _wsSub;
  bool _hydrated = false;

  // ── Context caches used to enrich the tile subtitle ("Alice accepted your
  // request", "Alice: hey") and to upgrade `connection_accepted` taps into a
  // direct-chat navigation. All three are loaded in parallel with the
  // notifications on hydrate + on pull-to-refresh; live WS pushes trigger a
  // best-effort refresh so newly-arriving rows can be enriched too.
  final Map<int, UserRead> _usersById = {};
  final Map<int, ConnectionRead> _connectionsById = {};
  List<ThreadRead> _threads = const [];
  bool _refreshingContext = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
      _openWs();
    }
  }

  @override
  void dispose() {
    _wsSub?.cancel();
    _ws?.close();
    super.dispose();
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        services.notifications
            .list(userId: userId, unreadOnly: _unreadOnly),
        services.users.list(limit: 500),
        services.chat.listConnections(userId),
        services.chat.listThreads(userId),
      ]);
      if (!mounted) return;
      setState(() {
        _items = results[0] as List<NotificationRead>;
        _usersById
          ..clear()
          ..addEntries(
            (results[1] as List<UserRead>).map((u) => MapEntry(u.id, u)),
          );
        _connectionsById
          ..clear()
          ..addEntries(
            (results[2] as List<ConnectionRead>).map((c) => MapEntry(c.id, c)),
          );
        _threads = results[3] as List<ThreadRead>;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  /// Best-effort refresh of the context caches only — used after a live WS
  /// push so a brand-new "connection_accepted" or "dm_new" tile can be
  /// enriched without waiting for a pull-to-refresh. Silent on failure.
  Future<void> _refreshContext() async {
    if (_refreshingContext) return;
    _refreshingContext = true;
    try {
      final services = ServiceScope.of(context);
      final userId = services.session.userId;
      if (userId == null) return;
      final results = await Future.wait([
        services.users.list(limit: 500),
        services.chat.listConnections(userId),
        services.chat.listThreads(userId),
      ]);
      if (!mounted) return;
      setState(() {
        _usersById
          ..clear()
          ..addEntries(
            (results[0] as List<UserRead>).map((u) => MapEntry(u.id, u)),
          );
        _connectionsById
          ..clear()
          ..addEntries(
            (results[1] as List<ConnectionRead>).map((c) => MapEntry(c.id, c)),
          );
        _threads = results[2] as List<ThreadRead>;
      });
    } catch (_) {
      // Tiles fall back to the raw backend body — still functional.
    } finally {
      _refreshingContext = false;
    }
  }

  void _openWs() {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    final ws = services.ws.notificationsSocket(userId);
    _ws = ws;
    _wsSub = ws.frames.listen(_onWsFrame);
    ws.connect();
  }

  void _onWsFrame(Map<String, dynamic> frame) {
    if (frame['channel'] != 'notification') return;
    final data = frame['data'];
    if (data is! Map) return;
    final n = NotificationRead.fromJson(Map<String, dynamic>.from(data));
    if (!mounted) return;
    setState(() {
      _items = [n, ..._items.where((e) => e.id != n.id)];
    });
    // The just-arrived notification likely references a brand-new thread /
    // connection that isn't in our caches yet — pull them in the background
    // so the tile subtitle and tap-navigation resolve properly.
    if (n.type == 'connection_accepted' ||
        n.type == 'connection_request' ||
        n.type == 'dm_new') {
      unawaited(_refreshContext());
    }
  }

  Future<void> _markRead(NotificationRead n) async {
    if (n.isRead) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _items = _items
          .map((e) => e.id == n.id
              ? NotificationRead(
                  id: e.id,
                  userId: e.userId,
                  type: e.type,
                  title: e.title,
                  body: e.body,
                  deepLink: e.deepLink,
                  readAt: DateTime.now().toUtc(),
                  createdAt: e.createdAt,
                )
              : e)
          .toList();
    });
    try {
      await services.notifications.markRead(n.id, userId: userId);
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    }
  }

  /// Tapping a notification should: (1) optimistically mark it as read and
  /// (2) navigate to the surface the notification is about so the user can
  /// act on it. We parse `n.deepLink` first (structured, current backend
  /// contract) and fall back to `n.type` when a link is missing or unknown
  /// so every notification remains actionable even if the payload is thin.
  ///
  /// Special-case: `connection_accepted` ships with `/threads` (no id) so
  /// we upgrade the route to a specific `chatThread` when we can resolve
  /// the newly-created thread from our context caches — that way tapping
  /// "Alice accepted" lands you in Alice's chat, not the whole list.
  Future<void> _handleTap(NotificationRead n) async {
    // Fire-and-forget the mark-read so navigation isn't blocked on it.
    unawaited(_markRead(n));
    var route = _NotificationRoute.parse(n.deepLink, n.type);
    if (route == null) return;

    if (n.type == 'connection_accepted') {
      final tid = _threadIdForAcceptance(n);
      if (tid != null) {
        route = _NotificationRoute.chatThread(tid);
      }
    }

    final services = ServiceScope.of(context);
    switch (route.kind) {
      case _RouteKind.chatThread:
        await _openChatById(services, route.id!);
      case _RouteKind.threadsList:
        await _pushScreen(const ThreadsScreen(initialTab: 0));
      case _RouteKind.connectionsList:
        await _pushScreen(const ThreadsScreen(initialTab: 1));
      case _RouteKind.missions:
        await _pushScreen(const MissionsScreen());
      case _RouteKind.eventDetail:
        await _openEventSheet(services, route.id!);
      case _RouteKind.home:
        // Anything home-shaped (welcome, recommendation) — the user just
        // wants to get back to the main deck. Popping this screen puts
        // them on the AppShell where those surfaces already live.
        if (mounted && Navigator.of(context).canPop()) {
          Navigator.of(context).pop();
        }
    }
  }

  // ─────────────────────── Context-driven enrichment ───────────────────────

  int? _selfId() => ServiceScope.of(context).session.userId;

  int? _extractIdFromLink(String? link, String head) {
    final raw = (link ?? '').trim();
    if (raw.isEmpty) return null;
    final segs =
        raw.split('/').where((s) => s.isNotEmpty).toList(growable: false);
    if (segs.length < 2 || segs[0] != head) return null;
    return int.tryParse(segs[1]);
  }

  /// The `connection_accepted` notification only carries `/threads` in its
  /// deep link — no ids — because it's emitted from the acceptor's PATCH
  /// handler. Match it back to a specific row by looking for the most
  /// recently-accepted connection where *I* was the requester and its
  /// `updatedAt` sits nearest the notification's `createdAt`. Falls back to
  /// `null` if nothing is within a five-minute tolerance — better to skip
  /// enrichment than mislabel the row.
  ConnectionRead? _acceptedConnectionFor(NotificationRead n) {
    final selfId = _selfId();
    if (selfId == null) return null;
    ConnectionRead? best;
    Duration bestDelta = const Duration(hours: 1);
    for (final c in _connectionsById.values) {
      if (c.status != 'accepted') continue;
      if (c.requesterId != selfId) continue;
      final delta = c.updatedAt.difference(n.createdAt).abs();
      if (delta < bestDelta) {
        bestDelta = delta;
        best = c;
      }
    }
    if (best == null || bestDelta > const Duration(minutes: 5)) return null;
    return best;
  }

  int? _threadIdForAcceptance(NotificationRead n) {
    final c = _acceptedConnectionFor(n);
    if (c == null) return null;
    for (final t in _threads) {
      if (t.connectionId == c.id) return t.id;
    }
    return null;
  }

  UserRead? _counterpartyForThread(int threadId) {
    final selfId = _selfId();
    if (selfId == null) return null;
    ThreadRead? thread;
    for (final t in _threads) {
      if (t.id == threadId) {
        thread = t;
        break;
      }
    }
    if (thread == null) return null;
    for (final pid in thread.participantIds) {
      if (pid != selfId) return _usersById[pid];
    }
    return null;
  }

  /// Produces the two-line subtitle displayed under the notification title.
  /// Enriches with the counterparty's name for the two "who was it" cases
  /// (`connection_accepted`, `dm_new`); everything else keeps the backend
  /// body as-is.
  String _displayBody(NotificationRead n) {
    final raw = n.body ?? '';
    switch (n.type) {
      case 'connection_accepted':
        final c = _acceptedConnectionFor(n);
        if (c == null) return raw;
        final u = _usersById[c.receiverId];
        final name = (u?.name ?? '').trim();
        return name.isEmpty
            ? raw
            : '$name accepted your connection request';
      case 'dm_new':
        final tid = _extractIdFromLink(n.deepLink, 'threads');
        if (tid == null) return raw;
        final u = _counterpartyForThread(tid);
        final name = (u?.name ?? '').trim();
        if (name.isEmpty) return raw;
        return raw.isEmpty ? name : '$name: $raw';
    }
    return raw;
  }

  Future<void> _pushScreen(Widget screen) async {
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => screen),
    );
  }

  /// The backend only exposes `GET /threads` (list) — no `/threads/{id}`.
  /// Prefer the already-hydrated `_threads` cache (populated in [_load]) so
  /// the tap is instant; only fall through to a network fetch if the cache
  /// misses (fresh dm_new WS push that arrived before context refresh
  /// completed). Last-resort: hand [ChatScreen] a minimal stub — degraded
  /// but never blocked.
  Future<void> _openChatById(Services services, int threadId) async {
    final userId = services.session.userId;
    if (userId == null) return;
    ThreadRead? thread;
    for (final t in _threads) {
      if (t.id == threadId) {
        thread = t;
        break;
      }
    }
    if (thread == null) {
      try {
        final threads = await services.chat.listThreads(userId);
        for (final t in threads) {
          if (t.id == threadId) {
            thread = t;
            break;
          }
        }
      } catch (_) {
        // Swallow — fall through to the stub below so the tap still works.
      }
    }
    thread ??= ThreadRead(
      id: threadId,
      createdAt: DateTime.now().toUtc(),
      participantIds: const [],
    );
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ChatScreen(thread: thread!)),
    );
  }

  /// Fetches the event by id then opens the same bottom sheet the EventiveConnect
  /// deck uses. We pass an empty `prompts` list because notifications don't
  /// carry them — the sheet's own refresh path repopulates on demand.
  Future<void> _openEventSheet(Services services, int eventId) async {
    try {
      final event = await services.events.get(eventId);
      if (!mounted) return;
      await showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => EventDetailSheet(
          card: EventCard(
            event: event,
            prompts: const [],
            alreadyLikedSpeaker: false,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          'Notifications',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 18,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
          ),
        ),
        backgroundColor: AppColors.background,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Row(
              children: [
                Text('Unread',
                    style: TextStyle(
                        color: AppColors.textSecondary, fontSize: 12)),
                Switch(
                  value: _unreadOnly,
                  activeThumbColor: AppColors.accent,
                  onChanged: (v) {
                    setState(() => _unreadOnly = v);
                    _load();
                  },
                ),
              ],
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: _load,
        child: _loading && _items.isEmpty
            ? const Center(child: CircularProgressIndicator(color: AppColors.accent))
            : _items.isEmpty
                ? _empty()
                : ListView.builder(
                    padding:
                        const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                    itemCount: _items.length,
                    itemBuilder: (_, i) => _tile(_items[i]),
                  ),
      ),
    );
  }

  Widget _empty() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.notifications_none_rounded,
                size: 42, color: AppColors.textTertiary),
            const SizedBox(height: 12),
            Text(
              _unreadOnly ? 'No unread notifications' : 'No notifications yet',
              style: TextStyle(color: AppColors.textSecondary, fontSize: 15),
            ),
          ],
        ),
      ),
    );
  }

  Widget _tile(NotificationRead n) {
    final subtitle = _displayBody(n);
    final ago = DateFormat('MMM d · h:mm a').format(n.createdAt.toLocal());
    return Container(
      margin: const EdgeInsets.only(top: 8),
      decoration: BoxDecoration(
        color: n.isRead ? AppColors.surface : AppColors.accentLight,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: _colorFor(n.type).withValues(alpha: 0.15),
            borderRadius: AppRadius.borderMd,
          ),
          alignment: Alignment.center,
          child: Icon(_iconFor(n.type), color: _colorFor(n.type), size: 18),
        ),
        title: Text(
          n.title,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        subtitle: subtitle.isEmpty
            ? Text(ago,
                style: TextStyle(
                    fontSize: 12, color: AppColors.textTertiary))
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(subtitle,
                      style: TextStyle(
                          fontSize: 13, color: AppColors.textSecondary),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 3),
                  Text(ago,
                      style: TextStyle(
                          fontSize: 11, color: AppColors.textTertiary)),
                ],
              ),
        trailing: n.isRead
            ? null
            : Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.accent,
                ),
              ),
        onTap: () => _handleTap(n),
      ),
    );
  }

  IconData _iconFor(String type) {
    switch (type) {
      case 'connection_request':
        return Icons.person_add_alt_rounded;
      case 'connection_accepted':
        return Icons.people_alt_rounded;
      case 'dm_new':
        return Icons.chat_bubble_rounded;
      case 'mission_completed':
        return Icons.emoji_events_rounded;
      case 'event_starting_soon':
        return Icons.event_available_rounded;
      case 'event_saved_reminder':
        // Bookmark keeps the visual identity of "you saved this" —
        // softer than the RSVP alarm icon on purpose.
        return Icons.bookmark_rounded;
      default:
        return Icons.notifications_active_rounded;
    }
  }

  Color _colorFor(String type) {
    switch (type) {
      case 'connection_request':
      case 'connection_accepted':
        return AppColors.accent;
      case 'dm_new':
        return const Color(0xFF2563EB);
      case 'mission_completed':
        return const Color(0xFFF59E0B);
      case 'event_starting_soon':
        return const Color(0xFFEC4899);
      case 'event_saved_reminder':
        // Sky-blue matches the "Saved" tab accent on My Activity so the
        // same intent has the same colour across the app.
        return const Color(0xFF0EA5E9);
      default:
        return AppColors.textSecondary;
    }
  }
}

// ═════════════════════════════ Deep-link routing ════════════════════════════

enum _RouteKind {
  chatThread,
  threadsList,
  connectionsList,
  missions,
  eventDetail,
  home,
}

/// Parses backend deep links like `/threads/17` or `/events/42` into a
/// small typed record the screen can switch on. Falls back to the
/// notification `type` when the link is missing / malformed so no tap is
/// ever a dead-end.
///
/// Contract (backend, `notification_service.push` call sites):
///   * `/connections/{id}` — connection_request
///   * `/threads`          — connection_accepted
///   * `/threads/{id}`     — dm_new
///   * `/missions/{id}`    — mission_completed
///   * `/events/{id}`      — event_starting_soon, event_saved_reminder
///   * `/events/discover`  — welcome (seed)
///   * `/network/recommendations` — recommendation (bulk seed)
class _NotificationRoute {
  final _RouteKind kind;
  final int? id;

  const _NotificationRoute._(this.kind, [this.id]);

  /// Used by the screen to upgrade an id-less `connection_accepted` route
  /// into a direct-chat navigation once the thread id has been resolved.
  const _NotificationRoute.chatThread(int threadId)
      : this._(_RouteKind.chatThread, threadId);

  static _NotificationRoute? parse(String? deepLink, String type) {
    final byLink = _fromDeepLink(deepLink);
    if (byLink != null) return byLink;
    return _fromType(type);
  }

  static _NotificationRoute? _fromDeepLink(String? link) {
    final raw = (link ?? '').trim();
    if (raw.isEmpty) return null;
    final segs =
        raw.split('/').where((s) => s.isNotEmpty).toList(growable: false);
    if (segs.isEmpty) return null;
    switch (segs[0]) {
      case 'threads':
        if (segs.length >= 2) {
          final id = int.tryParse(segs[1]);
          if (id != null) return _NotificationRoute._(_RouteKind.chatThread, id);
        }
        return const _NotificationRoute._(_RouteKind.threadsList);
      case 'connections':
        // Backend uses `/connections/{id}` but the receiver just needs to
        // land on the Connections tab — the pending row is right there
        // with its Accept/Decline buttons already wired.
        return const _NotificationRoute._(_RouteKind.connectionsList);
      case 'missions':
        return const _NotificationRoute._(_RouteKind.missions);
      case 'events':
        // `/events/discover` (no numeric id) → home; `/events/42` → sheet.
        if (segs.length >= 2) {
          final id = int.tryParse(segs[1]);
          if (id != null) {
            return _NotificationRoute._(_RouteKind.eventDetail, id);
          }
        }
        return const _NotificationRoute._(_RouteKind.home);
      case 'network':
        return const _NotificationRoute._(_RouteKind.home);
    }
    return null;
  }

  static _NotificationRoute? _fromType(String type) {
    switch (type) {
      case 'connection_request':
        return const _NotificationRoute._(_RouteKind.connectionsList);
      case 'connection_accepted':
      case 'dm_new':
        // dm_new without an id can't open a specific chat — the threads
        // list is the safest fallback.
        return const _NotificationRoute._(_RouteKind.threadsList);
      case 'mission_completed':
        return const _NotificationRoute._(_RouteKind.missions);
      case 'event_starting_soon':
      case 'event_saved_reminder':
        return const _NotificationRoute._(_RouteKind.home);
      case 'welcome':
      case 'recommendation':
        return const _NotificationRoute._(_RouteKind.home);
    }
    return null;
  }
}
