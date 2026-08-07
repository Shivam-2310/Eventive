import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/ai_chat_message.dart';
import '../../models/event.dart';
import '../../models/recommendation.dart';
import '../../models/speaker.dart';
import '../../models/user.dart';
import '../../screens/eventiveconnect/detail/event_sheet.dart';
import '../../screens/eventiveconnect/detail/person_sheet.dart';
import '../../screens/speakers/speaker_detail_screen.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../utils/haptics.dart';
import 'chat_entity_refs.dart';

/// Horizontally scrolling strip of compact cards rendered under an assistant
/// chat bubble.
///
/// Refs are extracted from the message text (`[event:5]`) plus any
/// `citation` SSE frames the backend emitted. Each card hydrates itself via
/// the existing REST services and taps through to the same detail views
/// used elsewhere in the app. No backend changes required.
class ChatAttachmentsRow extends StatelessWidget {
  final AiChatMessage message;

  const ChatAttachmentsRow({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final refs = extractChatRefs(
      message.text,
      message.citations,
      sqlResult: message.sqlResult,
    );
    if (refs.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: SizedBox(
        height: _cardHeight,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.zero,
          itemCount: refs.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (context, i) => _CardFor(ref: refs[i]),
        ),
      ),
    );
  }
}

const double _cardHeight = 96;
const double _cardWidth = 260;

// ---------------------------------------------------------------------------
// Per-widget-tree hydration cache. Each ref only hits the network once per
// app session; if the same event is cited from two different bubbles they
// share the future. Cleared automatically when the process ends.
class _EntityCache {
  static final _events = <int, Future<EventRead>>{};
  static final _users = <int, Future<UserRead>>{};
  static final _speakers = <int, Future<SpeakerRead>>{};

  static Future<EventRead> event(Services s, int id) =>
      _events.putIfAbsent(id, () => s.events.get(id));

  static Future<UserRead> user(Services s, int id) =>
      _users.putIfAbsent(id, () => s.users.get(id));

  static Future<SpeakerRead> speaker(Services s, int id) =>
      _speakers.putIfAbsent(id, () => s.speakers.get(id));
}

class _CardFor extends StatelessWidget {
  final ChatEntityRef ref;

  const _CardFor({required this.ref});

  @override
  Widget build(BuildContext context) {
    switch (ref.kind) {
      case ChatEntityKind.event:
        return _EventChatCard(id: ref.id, preloadedTitle: ref.preloadedTitle);
      case ChatEntityKind.user:
        return _UserChatCard(id: ref.id, preloadedTitle: ref.preloadedTitle);
      case ChatEntityKind.speaker:
        return _SpeakerChatCard(id: ref.id, preloadedTitle: ref.preloadedTitle);
    }
  }
}

// ---------------------------------------------------------------------------
// Event
// ---------------------------------------------------------------------------

class _EventChatCard extends StatelessWidget {
  final int id;
  final String? preloadedTitle;

  const _EventChatCard({required this.id, this.preloadedTitle});

  @override
  Widget build(BuildContext context) {
    final services = ServiceScope.of(context);
    return FutureBuilder<EventRead>(
      future: _EntityCache.event(services, id),
      builder: (context, snap) {
        if (snap.hasError) {
          return _CardShell(
            title: preloadedTitle ?? 'Event #$id',
            subtitle: 'Tap to retry',
            leading: _fallbackIcon(Icons.event_rounded),
          );
        }
        final ev = snap.data;
        if (ev == null) {
          return _CardShell(
            title: preloadedTitle ?? 'Loading event…',
            subtitle: '',
            leading: _loadingLeading(),
          );
        }
        return _CardShell(
          title: ev.title,
          subtitle: _eventSubtitle(ev),
          leading: _eventCover(ev),
          onTap: () => _openEventSheet(context, ev),
          trailingChip: ev.track,
        );
      },
    );
  }

  static String _eventSubtitle(EventRead ev) {
    final when = _shortDate(ev.startTime);
    final where = ev.locationSummary;
    if (when.isEmpty) return where;
    if (where == 'TBA') return when;
    return '$when · $where';
  }

  static Widget _eventCover(EventRead ev) {
    final url = ev.coverImageUrl;
    if (url == null || url.isEmpty) {
      return _fallbackIcon(Icons.event_rounded);
    }
    return ClipRRect(
      borderRadius: AppRadius.borderSm,
      child: Image.network(
        url,
        width: 56,
        height: 56,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => _fallbackIcon(Icons.event_rounded),
      ),
    );
  }

  static Future<void> _openEventSheet(
    BuildContext context,
    EventRead event,
  ) async {
    AppHaptics.light();
    await showModalBottomSheet<void>(
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
  }
}

// ---------------------------------------------------------------------------
// User (people the current user might know / should meet)
// ---------------------------------------------------------------------------

class _UserChatCard extends StatelessWidget {
  final int id;
  final String? preloadedTitle;

  const _UserChatCard({required this.id, this.preloadedTitle});

  @override
  Widget build(BuildContext context) {
    final services = ServiceScope.of(context);
    return FutureBuilder<UserRead>(
      future: _EntityCache.user(services, id),
      builder: (context, snap) {
        if (snap.hasError) {
          return _CardShell(
            title: preloadedTitle ?? 'User #$id',
            subtitle: 'Tap to retry',
            leading: _fallbackIcon(Icons.person_rounded),
          );
        }
        final u = snap.data;
        if (u == null) {
          return _CardShell(
            title: preloadedTitle ?? 'Loading person…',
            subtitle: '',
            leading: _loadingLeading(),
          );
        }
        return _CardShell(
          title: u.name.isEmpty ? 'User #$id' : u.name,
          subtitle: _userSubtitle(u),
          leading: _userAvatar(u),
          onTap: () => _openPersonSheet(context, u),
          trailingChip: u.company,
        );
      },
    );
  }

  static String _userSubtitle(UserRead u) {
    if (u.headline != null && u.headline!.isNotEmpty) return u.headline!;
    final bits = <String>[
      if (u.role != null && u.role!.isNotEmpty) u.role!,
      if (u.company != null && u.company!.isNotEmpty) u.company!,
    ];
    return bits.join(' · ');
  }

  static Widget _userAvatar(UserRead u) {
    final url = u.avatarUrl;
    if (url != null && url.isNotEmpty) {
      return ClipOval(
        child: Image.network(
          url,
          width: 44,
          height: 44,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _initialsAvatar(u.name),
        ),
      );
    }
    return _initialsAvatar(u.name);
  }

  static Future<void> _openPersonSheet(
    BuildContext context,
    UserRead u,
  ) async {
    AppHaptics.light();
    final person = PersonRecommendation(
      otherUserId: u.id,
      name: u.name,
      headline: u.headline,
      score: 0,
      reasons: const [],
    );
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => PersonDetailSheet(person: person),
    );
  }
}

// ---------------------------------------------------------------------------
// Speaker
// ---------------------------------------------------------------------------

class _SpeakerChatCard extends StatelessWidget {
  final int id;
  final String? preloadedTitle;

  const _SpeakerChatCard({required this.id, this.preloadedTitle});

  @override
  Widget build(BuildContext context) {
    final services = ServiceScope.of(context);
    return FutureBuilder<SpeakerRead>(
      future: _EntityCache.speaker(services, id),
      builder: (context, snap) {
        if (snap.hasError) {
          return _CardShell(
            title: preloadedTitle ?? 'Speaker #$id',
            subtitle: 'Tap to retry',
            leading: _fallbackIcon(Icons.mic_none_rounded),
          );
        }
        final sp = snap.data;
        if (sp == null) {
          return _CardShell(
            title: preloadedTitle ?? 'Loading speaker…',
            subtitle: '',
            leading: _loadingLeading(),
          );
        }
        return _CardShell(
          title: sp.name.isEmpty ? 'Speaker #$id' : sp.name,
          subtitle: _speakerSubtitle(sp),
          leading: _speakerHeadshot(sp),
          onTap: () => _openSpeakerScreen(context, sp),
          trailingChip: sp.company,
        );
      },
    );
  }

  static String _speakerSubtitle(SpeakerRead sp) {
    final bits = <String>[
      if (sp.title != null && sp.title!.isNotEmpty) sp.title!,
      if (sp.company != null && sp.company!.isNotEmpty) sp.company!,
    ];
    return bits.join(' @ ');
  }

  static Widget _speakerHeadshot(SpeakerRead sp) {
    final url = sp.headshotUrl;
    if (url != null && url.isNotEmpty) {
      return ClipOval(
        child: Image.network(
          url,
          width: 44,
          height: 44,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _initialsAvatar(sp.name),
        ),
      );
    }
    return _initialsAvatar(sp.name);
  }

  static Future<void> _openSpeakerScreen(
    BuildContext context,
    SpeakerRead sp,
  ) async {
    AppHaptics.light();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => SpeakerDetailScreen(speakerId: sp.id, preloaded: sp),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shared card shell + tiny helpers
// ---------------------------------------------------------------------------

class _CardShell extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget leading;
  final VoidCallback? onTap;
  final String? trailingChip;

  const _CardShell({
    required this.title,
    required this.subtitle,
    required this.leading,
    this.onTap,
    this.trailingChip,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: AppRadius.borderLg,
        onTap: onTap,
        child: Container(
          width: _cardWidth,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: AppRadius.borderLg,
            border: Border.all(color: AppColors.borderLight),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              leading,
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                        height: 1.25,
                      ),
                    ),
                    if (subtitle.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          color: AppColors.textSecondary,
                          height: 1.25,
                        ),
                      ),
                    ],
                    if (trailingChip != null && trailingChip!.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      _chip(trailingChip!),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static Widget _chip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.accentLight,
        borderRadius: AppRadius.borderFull,
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: AppColors.accentDark,
          letterSpacing: 0.2,
        ),
      ),
    );
  }
}

Widget _fallbackIcon(IconData icon) {
  return Container(
    width: 44,
    height: 44,
    decoration: BoxDecoration(
      color: AppColors.accentLight,
      borderRadius: AppRadius.borderSm,
    ),
    child: Icon(icon, size: 22, color: AppColors.accentDark),
  );
}

Widget _loadingLeading() {
  return Container(
    width: 44,
    height: 44,
    decoration: BoxDecoration(
      color: AppColors.surfaceMuted,
      borderRadius: AppRadius.borderSm,
    ),
    child: const Center(
      child: SizedBox(
        width: 14,
        height: 14,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: AppColors.accent,
        ),
      ),
    ),
  );
}

Widget _initialsAvatar(String name) {
  final parts = name.trim().split(RegExp(r'\s+'));
  final initials = parts.isEmpty || parts.first.isEmpty
      ? '?'
      : (parts.length == 1
          ? parts.first.characters.first
          : parts.first.characters.first + parts.last.characters.first)
              .toUpperCase();
  return Container(
    width: 44,
    height: 44,
    alignment: Alignment.center,
    decoration: const BoxDecoration(
      shape: BoxShape.circle,
      gradient: LinearGradient(
        colors: AppColors.accentGradient,
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
    ),
    child: Text(
      initials,
      style: const TextStyle(
        color: Colors.white,
        fontSize: 15,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
    ),
  );
}

String _shortDate(DateTime? dt) {
  if (dt == null) return '';
  final local = dt.toLocal();
  return DateFormat('EEE h:mm a').format(local);
}
