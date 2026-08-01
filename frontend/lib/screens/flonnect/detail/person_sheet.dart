import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../../models/connection.dart';
import '../../../models/recommendation.dart';
import '../../../models/thread.dart';
import '../../../services/services.dart';
import '../../../theme/colors.dart';
import '../../../theme/radius.dart';
import '../../../utils/haptics.dart';
import '../../../utils/ui_errors.dart';
import '../../connections/chat_screen.dart';

/// One of the four states the current user can be in vs. [person].
///
/// Drives which CTA the sheet shows: connect / accept / DM / already sent.
enum _RelState { unknown, none, outgoingPending, incomingPending, accepted }

class PersonDetailSheet extends StatefulWidget {
  final PersonRecommendation person;

  const PersonDetailSheet({super.key, required this.person});

  @override
  State<PersonDetailSheet> createState() => _PersonDetailSheetState();
}

class _PersonDetailSheetState extends State<PersonDetailSheet> {
  _RelState _rel = _RelState.unknown;
  ConnectionRead? _connection;
  ThreadRead? _thread;

  bool _requesting = false;
  bool _accepting = false;
  bool _openingDm = false;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _hydrateRelationship();
    }
  }

  /// Look at the current user's connections + threads to decide which CTA
  /// this sheet should show for [widget.person]. Fetches are done in
  /// parallel and swallow errors — worst case we fall back to the "send
  /// connection request" CTA, which the backend will reject cleanly if a
  /// row already exists.
  Future<void> _hydrateRelationship() async {
    final services = ServiceScope.of(context);
    final selfId = services.session.userId;
    if (selfId == null) {
      if (mounted) setState(() => _rel = _RelState.none);
      return;
    }
    try {
      final results = await Future.wait([
        services.chat.listConnections(selfId),
        services.chat.listThreads(selfId),
      ]);
      final conns = results[0] as List<ConnectionRead>;
      final threads = results[1] as List<ThreadRead>;
      final match = _findConnection(conns, selfId, widget.person.otherUserId);
      ThreadRead? thread;
      if (match != null && match.status == 'accepted') {
        for (final t in threads) {
          if (t.connectionId == match.id) {
            thread = t;
            break;
          }
        }
        // Fallback: some environments key the thread on participant ids
        // instead of connection id — accept the first thread whose other
        // participant matches.
        thread ??= threads.firstWhere(
          (t) => t.otherParticipantId(selfId) == widget.person.otherUserId,
          orElse: () => ThreadRead(
            id: -1,
            createdAt: DateTime.now().toUtc(),
            participantIds: const [],
          ),
        );
        if (thread.id == -1) thread = null;
      }
      if (!mounted) return;
      setState(() {
        _connection = match;
        _thread = thread;
        _rel = _relFor(match, selfId);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _rel = _RelState.none);
    }
  }

  static ConnectionRead? _findConnection(
    List<ConnectionRead> rows,
    int selfId,
    int otherId,
  ) {
    for (final c in rows) {
      final matches = (c.requesterId == selfId && c.receiverId == otherId) ||
          (c.receiverId == selfId && c.requesterId == otherId);
      if (matches) return c;
    }
    return null;
  }

  static _RelState _relFor(ConnectionRead? c, int selfId) {
    if (c == null) return _RelState.none;
    switch (c.status) {
      case 'accepted':
        return _RelState.accepted;
      case 'pending':
        return c.requesterId == selfId
            ? _RelState.outgoingPending
            : _RelState.incomingPending;
      default:
        return _RelState.none;
    }
  }

  Future<void> _requestConnection() async {
    if (_requesting) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    AppHaptics.light();
    setState(() => _requesting = true);
    try {
      final created = await services.chat.requestConnection(
        requesterId: userId,
        receiverId: widget.person.otherUserId,
      );
      if (!mounted) return;
      setState(() {
        _requesting = false;
        _connection = created;
        _rel = _relFor(created, userId);
      });
      showInfoSnack(context, 'Connection request sent');
    } catch (e) {
      if (!mounted) return;
      setState(() => _requesting = false);
      showErrorSnack(context, e);
    }
  }

  Future<void> _acceptIncoming() async {
    final conn = _connection;
    if (_accepting || conn == null) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    AppHaptics.light();
    setState(() => _accepting = true);
    try {
      final updated = await services.chat.updateConnection(
        connectionId: conn.id,
        userId: userId,
        status: 'accepted',
      );
      if (!mounted) return;
      // Re-fetch threads so we can offer DM straight away.
      final threads = await services.chat.listThreads(userId);
      ThreadRead? thread;
      for (final t in threads) {
        if (t.connectionId == updated.id) {
          thread = t;
          break;
        }
      }
      if (!mounted) return;
      setState(() {
        _accepting = false;
        _connection = updated;
        _thread = thread;
        _rel = _relFor(updated, userId);
      });
      showInfoSnack(context, 'Connection accepted');
    } catch (e) {
      if (!mounted) return;
      setState(() => _accepting = false);
      showErrorSnack(context, e);
    }
  }

  Future<void> _openDm() async {
    if (_openingDm) return;
    AppHaptics.light();
    setState(() => _openingDm = true);
    final navigator = Navigator.of(context);
    var thread = _thread;

    if (thread == null) {
      // We know they're connected but the thread cache didn't have it —
      // refetch once. The backend auto-creates one on accept, so this is
      // almost always populated.
      final services = ServiceScope.of(context);
      final selfId = services.session.userId;
      if (selfId != null && _connection != null) {
        try {
          final threads = await services.chat.listThreads(selfId);
          for (final t in threads) {
            if (t.connectionId == _connection!.id ||
                t.otherParticipantId(selfId) == widget.person.otherUserId) {
              thread = t;
              break;
            }
          }
        } catch (_) {
          // fall through — we'll show an error snack below
        }
      }
    }

    if (!mounted) return;
    setState(() => _openingDm = false);
    if (thread == null) {
      showErrorSnack(context, 'Could not open the chat right now.');
      return;
    }
    navigator.pop();
    await navigator.push(
      MaterialPageRoute<void>(builder: (_) => ChatScreen(thread: thread!)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.88,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 12),
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.surfaceMuted,
                  borderRadius: AppRadius.borderFull,
                ),
              ),
              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.fromLTRB(24, 20, 24, 40),
                  children: [
                    Center(
                      child: Container(
                        width: 110,
                        height: 110,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const LinearGradient(
                            colors: AppColors.accentGradient,
                          ),
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          _initials(widget.person.name),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 38,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Center(
                      child: Text(
                        widget.person.name,
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          color: AppColors.textPrimary,
                          letterSpacing: -0.5,
                        ),
                      ),
                    ),
                    if (widget.person.headline != null &&
                        widget.person.headline!.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Center(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 6),
                          decoration: BoxDecoration(
                            color: AppColors.surfaceVariant,
                            borderRadius: AppRadius.borderFull,
                          ),
                          child: Text(
                            widget.person.headline!,
                            style: const TextStyle(
                              fontSize: 13,
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ),
                    ],
                    if (_rel == _RelState.accepted) ...[
                      const SizedBox(height: 16),
                      Center(child: _relBadge('You are connected')),
                    ],
                    const SizedBox(height: 24),
                    Text(
                      _rel == _RelState.accepted
                          ? 'Shared context'
                          : 'Why you should connect',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (widget.person.reasons.isEmpty)
                      Text(
                        _rel == _RelState.accepted
                            ? 'No shared signals highlighted — you can still say hi.'
                            : 'No shared signals yet — take a chance!',
                        style:
                            TextStyle(color: AppColors.textTertiary, fontSize: 14),
                      )
                    else
                      ...widget.person.reasons.map(
                        (r) => Container(
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.surfaceVariant,
                            borderRadius: AppRadius.borderLg,
                          ),
                          child: Row(
                            children: [
                              Icon(Icons.auto_awesome,
                                  size: 16, color: AppColors.accent),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  r,
                                  style: const TextStyle(
                                    fontSize: 14,
                                    color: AppColors.textSecondary,
                                    height: 1.45,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    const SizedBox(height: 20),
                    _buildCta(),
                    const SizedBox(height: 60),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildCta() {
    switch (_rel) {
      case _RelState.unknown:
        return _ctaShell(
          label: 'Checking status…',
          onTap: null,
          loading: true,
          muted: true,
        );
      case _RelState.accepted:
        return _ctaShell(
          label: 'Send DM',
          icon: Icons.chat_bubble_rounded,
          onTap: _openDm,
          loading: _openingDm,
        );
      case _RelState.outgoingPending:
        return _ctaShell(
          label: 'Request sent',
          onTap: null,
          muted: true,
        );
      case _RelState.incomingPending:
        return _ctaShell(
          label: 'Accept connection request',
          icon: Icons.person_add_alt_1_rounded,
          onTap: _acceptIncoming,
          loading: _accepting,
        );
      case _RelState.none:
        return _ctaShell(
          label: 'Send connection request',
          icon: Icons.person_add_alt_1_rounded,
          onTap: _requestConnection,
          loading: _requesting,
        );
    }
  }

  Widget _ctaShell({
    required String label,
    IconData? icon,
    VoidCallback? onTap,
    bool loading = false,
    bool muted = false,
  }) {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: GestureDetector(
        onTap: loading ? null : onTap,
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: muted
                  ? [AppColors.surfaceMuted, AppColors.surfaceMuted]
                  : AppColors.accentGradient,
            ),
            borderRadius: AppRadius.borderFull,
            boxShadow: muted
                ? []
                : [
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.3),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ],
          ),
          child: Center(
            child: loading
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      color: muted ? AppColors.textSecondary : Colors.white,
                      strokeWidth: 2,
                    ),
                  )
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (icon != null) ...[
                        Icon(icon,
                            size: 18,
                            color: muted
                                ? AppColors.textPrimary
                                : Colors.white),
                        const SizedBox(width: 8),
                      ],
                      Text(
                        label,
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: muted ? AppColors.textPrimary : Colors.white,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }

  Widget _relBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.accentLight,
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.check_circle_rounded,
              size: 14, color: AppColors.accentDark),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: AppColors.accentDark,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first.characters.first.toUpperCase();
    return (parts.first.characters.first + parts.last.characters.first)
        .toUpperCase();
  }
}
