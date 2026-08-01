import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/connection.dart';
import '../../models/user.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

class ConnectionsScreen extends StatefulWidget {
  final List<ConnectionRead> connections;
  final bool loading;
  final VoidCallback onChanged;

  const ConnectionsScreen({
    super.key,
    required this.connections,
    required this.loading,
    required this.onChanged,
  });

  @override
  State<ConnectionsScreen> createState() => _ConnectionsScreenState();
}

class _ConnectionsScreenState extends State<ConnectionsScreen> {
  bool _busy = false;
  // Local id→user cache so each tile can show a real name/avatar without
  // triggering a `GET /users/{id}` per row. Loaded once via `users.list()`
  // and refreshed lazily if a connection references a user we haven't seen.
  final Map<int, UserRead> _usersById = {};
  bool _hydrating = false;
  bool _initialHydrateStarted = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialHydrateStarted) {
      _initialHydrateStarted = true;
      _hydrateUsers();
    } else {
      _hydrateMissing();
    }
  }

  @override
  void didUpdateWidget(covariant ConnectionsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.connections != widget.connections) {
      _hydrateMissing();
    }
  }

  /// Bulk-load the workspace directory once. 500 rows is plenty for the
  /// hackathon dataset; anything past that will fall through to `_hydrateMissing`.
  Future<void> _hydrateUsers() async {
    if (_hydrating) return;
    _hydrating = true;
    try {
      final services = ServiceScope.of(context);
      final users = await services.users.list(limit: 500);
      if (!mounted) return;
      setState(() {
        for (final u in users) {
          _usersById[u.id] = u;
        }
      });
      // Anyone still missing (edge case: >500 users) — fetch individually.
      await _hydrateMissing();
    } catch (_) {
      // Names/avatars just won't show; connection functionality still works.
    } finally {
      _hydrating = false;
    }
  }

  /// Fetch users referenced by connections that we haven't cached yet.
  Future<void> _hydrateMissing() async {
    final selfId = ServiceScope.of(context).session.userId ?? -1;
    final missing = <int>{};
    for (final c in widget.connections) {
      final oid = c.otherUserId(selfId);
      if (oid > 0 && !_usersById.containsKey(oid)) missing.add(oid);
    }
    if (missing.isEmpty) return;
    final services = ServiceScope.of(context);
    final fetched = <int, UserRead>{};
    await Future.wait(missing.map((id) async {
      try {
        fetched[id] = await services.users.get(id);
      } catch (_) {
        // Skip — tile will render "Unknown user" gracefully.
      }
    }));
    if (!mounted || fetched.isEmpty) return;
    setState(() => _usersById.addAll(fetched));
  }

  Future<void> _accept(ConnectionRead c) async {
    if (_busy) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _busy = true);
    try {
      await services.chat.updateConnection(
        connectionId: c.id,
        userId: userId,
        status: 'accepted',
      );
      widget.onChanged();
      if (!mounted) return;
      showInfoSnack(context, 'Connection accepted');
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _decline(ConnectionRead c) async {
    if (_busy) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _busy = true);
    try {
      await services.chat.updateConnection(
        connectionId: c.id,
        userId: userId,
        status: 'declined',
      );
      widget.onChanged();
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.loading && widget.connections.isEmpty) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.accent),
      );
    }
    if (widget.connections.isEmpty) {
      return _EmptyState();
    }
    final userId = ServiceScope.of(context).session.userId ?? -1;
    return ListView.separated(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: 12,
      ),
      itemCount: widget.connections.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (_, i) {
        final c = widget.connections[i];
        return _ConnectionTile(
          connection: c,
          selfId: userId,
          other: _usersById[c.otherUserId(userId)],
          busy: _busy,
          onAccept: () => _accept(c),
          onDecline: () => _decline(c),
        );
      },
    );
  }
}

// ═════════════════════════════  Tile  ═══════════════════════════════════════

class _ConnectionTile extends StatelessWidget {
  final ConnectionRead connection;
  final int selfId;
  final UserRead? other;
  final bool busy;
  final VoidCallback onAccept;
  final VoidCallback onDecline;

  const _ConnectionTile({
    required this.connection,
    required this.selfId,
    required this.other,
    required this.busy,
    required this.onAccept,
    required this.onDecline,
  });

  @override
  Widget build(BuildContext context) {
    final incomingPending = connection.isIncomingPending(selfId);
    final outgoingPending = connection.isOutgoingPending(selfId);

    final rawName = (other?.name ?? '').trim();
    final displayName = rawName.isEmpty ? 'Unknown user' : rawName;
    final subtitle = _roleCompany(other) ?? other?.headline;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(14, 14, 12, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Avatar(user: other, fallbackId: connection.otherUserId(selfId)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: GoogleFonts.plusJakartaSans(
                              fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: AppColors.textPrimary,
                              letterSpacing: -0.2,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        _StatusPill(status: connection.status),
                      ],
                    ),
                    if (subtitle != null && subtitle.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12.5,
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w500,
                          height: 1.3,
                        ),
                      ),
                    ],
                    const SizedBox(height: 6),
                    Text(
                      _directionLine(displayName),
                      style: TextStyle(
                        fontSize: 11.5,
                        color: AppColors.textTertiary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (incomingPending) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: busy ? null : onDecline,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.textSecondary,
                      side: BorderSide(color: AppColors.border),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    icon: const Icon(Icons.close_rounded, size: 16),
                    label: const Text(
                      'Decline',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: busy ? null : onAccept,
                    style: ElevatedButton.styleFrom(
                      foregroundColor: Colors.white,
                      backgroundColor: AppColors.accent,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      elevation: 0,
                    ),
                    icon: const Icon(Icons.check_rounded, size: 16),
                    label: const Text(
                      'Accept',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ],
            ),
          ] else if (outgoingPending) ...[
            const SizedBox(height: 10),
            _WaitingChip(),
          ],
        ],
      ),
    );
  }

  String _directionLine(String otherName) {
    final when = DateFormat('MMM d · h:mm a').format(
      connection.updatedAt.toLocal(),
    );
    if (connection.status == 'pending') {
      return connection.requesterId == selfId
          ? 'Sent to $otherName · $when'
          : '$otherName wants to connect · $when';
    }
    if (connection.status == 'accepted') return 'Connected · $when';
    if (connection.status == 'declined') return 'Declined · $when';
    if (connection.status == 'blocked') return 'Blocked · $when';
    return when;
  }

  /// "ML Engineer · Nagarro" / "ML Engineer" / "Nagarro" / null.
  static String? _roleCompany(UserRead? u) {
    if (u == null) return null;
    final r = (u.role ?? '').trim();
    final c = (u.company ?? '').trim();
    if (r.isNotEmpty && c.isNotEmpty) return '$r · $c';
    if (r.isNotEmpty) return r;
    if (c.isNotEmpty) return c;
    return null;
  }
}

// ═════════════════════════════  Avatar  ═════════════════════════════════════

class _Avatar extends StatelessWidget {
  final UserRead? user;
  final int fallbackId;
  const _Avatar({required this.user, required this.fallbackId});

  @override
  Widget build(BuildContext context) {
    final url = user?.avatarUrl;
    final id = user?.id ?? fallbackId;
    final palette = _palettes[id.abs() % _palettes.length];
    final name = (user?.name ?? '').trim();
    final initial = name.isEmpty ? '·' : name.substring(0, 1).toUpperCase();

    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: SizedBox(
        width: 48,
        height: 48,
        child: url != null && url.isNotEmpty
            ? Image.network(
                url,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) =>
                    _fallbackGradient(palette, initial),
              )
            : _fallbackGradient(palette, initial),
      ),
    );
  }

  Widget _fallbackGradient(List<Color> palette, String initial) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: palette,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Center(
        child: Text(
          initial,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 18,
            fontWeight: FontWeight.w800,
            color: Colors.white,
            letterSpacing: -0.5,
          ),
        ),
      ),
    );
  }

  // Deterministic per-user gradient so re-renders don't shuffle colours.
  static const _palettes = <List<Color>>[
    [Color(0xFF14B8A6), Color(0xFF06B6D4)],
    [Color(0xFF8B5CF6), Color(0xFFEC4899)],
    [Color(0xFFF59E0B), Color(0xFFEF4444)],
    [Color(0xFF10B981), Color(0xFF3B82F6)],
    [Color(0xFF6366F1), Color(0xFF14B8A6)],
    [Color(0xFFEC4899), Color(0xFFF59E0B)],
  ];
}

// ═════════════════════════════  Status pill  ════════════════════════════════

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    final (bg, fg, icon, label) = _theme(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: fg),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w800,
              color: fg,
              letterSpacing: 0.4,
            ),
          ),
        ],
      ),
    );
  }

  (Color, Color, IconData, String) _theme(String s) {
    switch (s) {
      case 'accepted':
        return (
          AppColors.accent.withValues(alpha: 0.12),
          AppColors.accentDark,
          Icons.check_circle_rounded,
          'CONNECTED',
        );
      case 'declined':
        return (
          AppColors.surfaceMuted,
          AppColors.textSecondary,
          Icons.cancel_rounded,
          'DECLINED',
        );
      case 'blocked':
        return (
          AppColors.surfaceMuted,
          AppColors.textTertiary,
          Icons.block_rounded,
          'BLOCKED',
        );
      default:
        return (
          const Color(0xFFFEF3C7),
          const Color(0xFF92400E),
          Icons.schedule_rounded,
          'PENDING',
        );
    }
  }
}

// ═════════════════════════════  Waiting chip  ═══════════════════════════════

class _WaitingChip extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.hourglass_top_rounded,
              size: 13, color: AppColors.textTertiary),
          const SizedBox(width: 6),
          Text(
            'Waiting for response',
            style: TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

// ═════════════════════════════  Empty state  ═══════════════════════════════

class _EmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 80),
        Center(
          child: Container(
            width: 68,
            height: 68,
            decoration: BoxDecoration(
              color: AppColors.accentLight,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.people_outline_rounded,
              size: 32,
              color: AppColors.accentDark,
            ),
          ),
        ),
        const SizedBox(height: 16),
        Center(
          child: Text(
            'No connections yet',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 17,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
        ),
        const SizedBox(height: 6),
        Center(
          child: Text(
            'Swipe on the People deck to send your first request.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ),
      ],
    );
  }
}
