import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../models/event.dart';
import '../../../services/services.dart';
import '../../../theme/colors.dart';
import '../../../theme/radius.dart';

class EventCardWidget extends StatelessWidget {
  final EventCard card;

  const EventCardWidget({super.key, required this.card});

  @override
  Widget build(BuildContext context) {
    final event = card.event;
    final startText = _formatDate(event.startTime);
    final locationText = event.locationSummary;
    final trackText = event.track ?? _promptBody(card, 'when_where')?.split('·').first.trim();
    final store = ServiceScope.of(context).eventInteractions;

    return Container(
      color: Colors.black,
      child: ListenableBuilder(
        listenable: store,
        builder: (context, _) {
          final activeTypes = store.typesFor(event.id);
          return Stack(
        fit: StackFit.expand,
        children: [
          if (event.coverImageUrl != null)
            Image.network(
              event.coverImageUrl!,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => _fallbackCover(event.title),
            )
          else
            _fallbackCover(event.title),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  stops: const [0.2, 0.5, 1.0],
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.3),
                    Colors.black.withValues(alpha: 0.85),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            top: 110,
            left: 16,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.15),
                borderRadius: AppRadius.borderFull,
                border:
                    Border.all(color: Colors.white.withValues(alpha: 0.2)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.event_rounded,
                      size: 13,
                      color: Colors.white.withValues(alpha: 0.9)),
                  const SizedBox(width: 5),
                  Text(
                    trackText ?? event.status,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.9),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.2,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (event.status.isNotEmpty)
            Positioned(
              top: 110,
              right: 16,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: _statusColor(event.status).withValues(alpha: 0.9),
                  borderRadius: AppRadius.borderFull,
                ),
                child: Text(
                  event.status.toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                  ),
                ),
              ),
            ),
          Positioned(
            left: 20,
            right: 20,
            bottom: 100,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (activeTypes.isNotEmpty) ...[
                  Builder(builder: (_) {
                    // Only surface *user-managed* signals on the card.
                    // `like` is written silently by the swipe-right gesture
                    // for personalization; showing it back to the user as a
                    // badge would be surprising ("I didn't tap anything").
                    // `add_to_my_day` / `add_to_calendar` are legacy types
                    // that overlap with Save/RSVP.
                    final visible = activeTypes
                        .where((t) =>
                            t != 'like' &&
                            t != 'add_to_my_day' &&
                            t != 'add_to_calendar')
                        .toList();
                    if (visible.isEmpty) return const SizedBox.shrink();
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: visible
                            .map(_activeBadgeFor)
                            .whereType<Widget>()
                            .toList(),
                      ),
                    );
                  }),
                ],
                Text(
                  event.title,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    letterSpacing: -0.5,
                    height: 1.2,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                if (event.vibeText != null && event.vibeText!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    event.vibeText!,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.85),
                      fontStyle: FontStyle.italic,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.calendar_today_rounded,
                        size: 13,
                        color: Colors.white.withValues(alpha: 0.7)),
                    const SizedBox(width: 5),
                    Text(
                      startText,
                      style: TextStyle(
                          fontSize: 13,
                          color: Colors.white.withValues(alpha: 0.8),
                          fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(width: 14),
                    Icon(Icons.location_on_rounded,
                        size: 13,
                        color: Colors.white.withValues(alpha: 0.7)),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        locationText,
                        style: TextStyle(
                            fontSize: 13,
                            color: Colors.white.withValues(alpha: 0.8),
                            fontWeight: FontWeight.w500),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (event.interests.isNotEmpty)
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: event.interests
                        .take(4)
                        .map((tag) => _tag(tag.label))
                        .toList(),
                  ),
                const SizedBox(height: 14),
                _tapForDetailsPill(),
              ],
            ),
          ),
        ],
      );
        },
      ),
    );
  }

  Widget _tapForDetailsPill() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.14),
        borderRadius: AppRadius.borderFull,
        border: Border.all(color: Colors.white.withValues(alpha: 0.22)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.touch_app_rounded,
              size: 13, color: Colors.white.withValues(alpha: 0.9)),
          const SizedBox(width: 6),
          Text(
            'Tap for details · swipe right to save',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.white.withValues(alpha: 0.9),
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }

  Widget? _activeBadgeFor(String type) {
    // Callers should already have filtered `like`, `add_to_my_day`, and
    // `add_to_calendar` before hitting this switch. The extra cases are
    // kept as a safe fallback so an unfiltered value renders sensibly
    // rather than crashing, but they should never actually surface.
    final (icon, label) = switch (type) {
      'rsvp' => (Icons.event_available_rounded, 'Going'),
      'save' => (Icons.bookmark_rounded, 'Saved'),
      'mark_attended' => (Icons.check_circle_rounded, 'Attended'),
      _ => (Icons.check_rounded, type),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.accent.withValues(alpha: 0.85),
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: Colors.white),
          const SizedBox(width: 4),
          Text(
            label,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }

  Widget _tag(String label) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.15),
          borderRadius: AppRadius.borderFull,
          border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: Colors.white.withValues(alpha: 0.9),
          ),
        ),
      );

  Widget _fallbackCover(String title) => Container(
        color: AppColors.surfaceVariant,
        alignment: Alignment.center,
        child: Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: AppColors.textTertiary,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
      );

  String? _promptBody(EventCard card, String type) {
    for (final p in card.prompts) {
      if (p.promptType == type) return p.body;
    }
    return null;
  }

  String _formatDate(DateTime? dt) {
    if (dt == null) return 'TBA';
    final local = dt.toLocal();
    return DateFormat('EEE, MMM d · h:mm a').format(local);
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'live':
        return const Color(0xFFDC2626);
      case 'canceled':
        return const Color(0xFF6B7280);
      case 'finished':
        return const Color(0xFF64748B);
      case 'delayed':
        return const Color(0xFFF59E0B);
      default:
        return AppColors.accent;
    }
  }
}
