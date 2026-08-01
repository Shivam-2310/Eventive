import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../../models/event.dart';
import '../../../services/services.dart';
import '../../../theme/colors.dart';
import '../../../theme/radius.dart';

/// Chronological list row used by the "All Events" tab on Flonnect.
///
/// Design brief: match the rest of the app's list surfaces (My Activity,
/// Profile, etc.) instead of a Hinge-style full-bleed card. That means a
/// light [AppColors.surface] tile with a soft border, a compact cover
/// thumbnail on the left, and a readable title / date / location block on
/// the right — all wrapped in a single `InkWell` that opens the event detail
/// sheet on tap.
class EventListRow extends StatelessWidget {
  final EventCard card;
  final VoidCallback onTap;

  const EventListRow({
    super.key,
    required this.card,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final event = card.event;
    final start = event.startTime?.toLocal();
    final dateText = start == null
        ? 'Time TBA'
        : DateFormat('EEE, MMM d · h:mm a').format(start);
    final store = ServiceScope.of(context).eventInteractions;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.borderLg,
        child: Ink(
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
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _CoverThumb(event: event),
              const SizedBox(width: 12),
              Expanded(
                child: ListenableBuilder(
                  listenable: store,
                  builder: (context, _) {
                    final activeTypes = store.typesFor(event.id);
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _TopChipRow(event: event),
                        const SizedBox(height: 8),
                        Text(
                          event.title,
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 15,
                            fontWeight: FontWeight.w800,
                            color: AppColors.textPrimary,
                            height: 1.25,
                            letterSpacing: -0.2,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 8),
                        _MetaRow(
                          icon: Icons.calendar_today_rounded,
                          text: dateText,
                        ),
                        if (event.locationSummary.isNotEmpty &&
                            event.locationSummary != 'TBA') ...[
                          const SizedBox(height: 4),
                          _MetaRow(
                            icon: Icons.location_on_rounded,
                            text: event.locationSummary,
                          ),
                        ],
                        if (event.interests.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 6,
                            runSpacing: 6,
                            children: event.interests
                                .take(3)
                                .map((t) => _TagChip(label: t.label))
                                .toList(),
                          ),
                        ],
                        if (activeTypes.isNotEmpty) ...[
                          Builder(builder: (_) {
                            // Same visibility rule as the swipe-card deck:
                            // hide `like` (implicit taste signal) and the
                            // legacy `add_to_my_day` / `add_to_calendar`
                            // overlaps so rows only surface intents the
                            // user actually manages.
                            final visible = activeTypes
                                .where((t) =>
                                    t != 'like' &&
                                    t != 'add_to_my_day' &&
                                    t != 'add_to_calendar')
                                .toList();
                            if (visible.isEmpty) {
                              return const SizedBox.shrink();
                            }
                            return Padding(
                              padding: const EdgeInsets.only(top: 10),
                              child: Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children:
                                    visible.map(_activeChip).toList(),
                              ),
                            );
                          }),
                        ],
                      ],
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _activeChip(String type) {
    // Caller already filters `like`, `add_to_my_day`, `add_to_calendar`;
    // the remaining fallback keeps the switch total.
    final (icon, label) = switch (type) {
      'rsvp' => (Icons.event_available_rounded, 'Going'),
      'save' => (Icons.bookmark_rounded, 'Saved'),
      'mark_attended' => (Icons.check_circle_rounded, 'Attended'),
      _ => (Icons.check_rounded, type),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.accent.withValues(alpha: 0.12),
        borderRadius: AppRadius.borderFull,
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: AppColors.accentDark),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: AppColors.accentDark,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }
}

class _CoverThumb extends StatelessWidget {
  final EventRead event;
  const _CoverThumb({required this.event});

  @override
  Widget build(BuildContext context) {
    final url = event.coverImageUrl;
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: 68,
        height: 68,
        child: url != null && url.isNotEmpty
            ? Image.network(
                url,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => _FallbackThumb(event: event),
              )
            : _FallbackThumb(event: event),
      ),
    );
  }
}

class _FallbackThumb extends StatelessWidget {
  final EventRead event;
  const _FallbackThumb({required this.event});

  @override
  Widget build(BuildContext context) {
    // Deterministic gradient per event id so repeats look "themed" instead
    // of random on re-render.
    final palette = _palettes[event.id % _palettes.length];
    final initial = event.title.trim().isEmpty
        ? '·'
        : event.title.trim().substring(0, 1).toUpperCase();
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
            fontSize: 26,
            fontWeight: FontWeight.w800,
            color: Colors.white,
            letterSpacing: -0.5,
          ),
        ),
      ),
    );
  }

  static const _palettes = <List<Color>>[
    [Color(0xFF14B8A6), Color(0xFF06B6D4)],
    [Color(0xFF8B5CF6), Color(0xFFEC4899)],
    [Color(0xFFF59E0B), Color(0xFFEF4444)],
    [Color(0xFF10B981), Color(0xFF3B82F6)],
    [Color(0xFF6366F1), Color(0xFF14B8A6)],
    [Color(0xFFEC4899), Color(0xFFF59E0B)],
  ];
}

class _TopChipRow extends StatelessWidget {
  final EventRead event;
  const _TopChipRow({required this.event});

  @override
  Widget build(BuildContext context) {
    final track = event.track;
    return Row(
      children: [
        if (track != null && track.isNotEmpty)
          Flexible(
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.accentLight,
                borderRadius: AppRadius.borderFull,
              ),
              child: Text(
                track,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w800,
                  color: AppColors.accentDark,
                  letterSpacing: 0.4,
                ),
              ),
            ),
          ),
        if ((track ?? '').isNotEmpty) const SizedBox(width: 6),
        _StatusPill(status: event.status),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    if (status.isEmpty || status == 'scheduled') {
      return const SizedBox.shrink();
    }
    final (bg, fg) = switch (status) {
      'live' => (const Color(0xFFFEE2E2), const Color(0xFFDC2626)),
      'delayed' => (const Color(0xFFFEF3C7), const Color(0xFF92400E)),
      'finished' => (AppColors.surfaceMuted, AppColors.textSecondary),
      'canceled' => (AppColors.surfaceMuted, AppColors.textTertiary),
      _ => (AppColors.surfaceVariant, AppColors.textSecondary),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (status == 'live') ...[
            Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(
                color: Color(0xFFDC2626),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 5),
          ],
          Text(
            status.toUpperCase(),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              color: fg,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  final IconData icon;
  final String text;

  const _MetaRow({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 13, color: AppColors.textTertiary),
        const SizedBox(width: 5),
        Expanded(
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }
}

class _TagChip extends StatelessWidget {
  final String label;
  const _TagChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: AppRadius.borderFull,
      ),
      child: Text(
        '#$label',
        style: const TextStyle(
          fontSize: 10.5,
          fontWeight: FontWeight.w600,
          color: AppColors.textSecondary,
        ),
      ),
    );
  }
}
