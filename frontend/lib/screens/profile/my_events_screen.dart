import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/event.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../utils/ui_errors.dart';
import '../eventiveconnect/detail/event_sheet.dart';

/// "My activity" screen — one tab per interaction bucket, each backed by
/// `GET /users/{id}/events`. Every card observes the shared
/// [EventInteractionsStore] so removing a Save on this screen updates
/// Discover, the Event Details sheet, and the Profile stats live.
///
/// We intentionally expose only three user-managed buckets:
///
/// * **Upcoming** (`rsvp`) — hard commitment, "I'm going".
/// * **Saved** (`save`) — soft shortlist, "I'll decide later".
/// * **Attended** (`mark_attended`) — post-event log for Wrapped.
///
/// `like` is deliberately not a tab: it's a behavioural fingerprint from the
/// Discover swipe deck used only for personalization, not something users
/// need to curate. `add_to_my_day` / `add_to_calendar` are legacy overlaps
/// with Save/RSVP and stay off this screen too.
class MyEventsScreen extends StatefulWidget {
  const MyEventsScreen({super.key, this.initialBucket = 'upcoming_rsvp'});

  final String initialBucket;

  @override
  State<MyEventsScreen> createState() => _MyEventsScreenState();
}

class _MyEventsScreenState extends State<MyEventsScreen>
    with SingleTickerProviderStateMixin {
  static const _tabs = <_BucketTab>[
    _BucketTab(
      bucket: 'upcoming_rsvp',
      interactionType: 'rsvp',
      label: 'Upcoming',
      icon: Icons.event_available_rounded,
      accent: Color(0xFF14B8A6),
      emptyTitle: 'No upcoming sessions yet',
      emptyBody:
          'RSVP to a session and it will land here so you never miss it.',
    ),
    _BucketTab(
      bucket: 'save',
      interactionType: 'save',
      label: 'Saved',
      icon: Icons.bookmark_rounded,
      accent: Color(0xFF0EA5E9),
      emptyTitle: 'Nothing saved yet',
      emptyBody:
          "Tap Save on a session you'd like to revisit — it'll show up here.",
    ),
    _BucketTab(
      bucket: 'mark_attended',
      interactionType: 'mark_attended',
      label: 'Attended',
      icon: Icons.check_circle_rounded,
      accent: Color(0xFF8B5CF6),
      emptyTitle: 'Attended list is empty',
      emptyBody:
          'Mark a session as attended so Eventive can power your Wrapped recap.',
    ),
  ];

  late final TabController _controller;
  bool _loading = true;
  Map<String, List<EventRead>> _buckets = const {};
  Object? _error;
  bool _hydrated = false;

  @override
  void initState() {
    super.initState();
    final initial = _tabs.indexWhere((t) => t.bucket == widget.initialBucket);
    _controller = TabController(
      length: _tabs.length,
      vsync: this,
      initialIndex: initial < 0 ? 0 : initial,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final buckets = await services.events.userEventBuckets(userId);
      // Keep the interactions store aligned with the freshly fetched data so
      // the badges on other screens (Event Card, Discover) reflect any
      // changes made from another device between refreshes.
      await services.eventInteractions.refresh(userId);
      if (!mounted) return;
      setState(() {
        _buckets = buckets;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e;
      });
      showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final activeTab = _tabs[_controller.index.clamp(0, _tabs.length - 1)];
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          'My activity',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 18,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
          ),
        ),
        backgroundColor: AppColors.background,
        elevation: 0,
        centerTitle: false,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(64),
          child: AnimatedBuilder(
            animation: _controller.animation ?? _controller,
            builder: (context, _) {
              return _TabPillBar(
                tabs: _tabs,
                controller: _controller,
                counts: {
                  for (final t in _tabs)
                    t.bucket: (_buckets[t.bucket] ?? const []).length,
                },
              );
            },
          ),
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent))
          : _error != null
              ? _ErrorState(onRetry: _load)
              : TabBarView(
                  controller: _controller,
                  children: [
                    for (final tab in _tabs)
                      _BucketList(
                        tab: tab,
                        events: _buckets[tab.bucket] ?? const [],
                        onRefresh: _load,
                      ),
                  ],
                ),
      // Total count strip at the bottom keeps the ambient "how am I doing"
      // read-out that the old count pills used to provide, without
      // cluttering the tab row.
      bottomNavigationBar: _loading || _error != null
          ? null
          : SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                child: _FooterSummary(
                  tab: activeTab,
                  count: (_buckets[activeTab.bucket] ?? const []).length,
                ),
              ),
            ),
    );
  }
}

class _BucketTab {
  final String bucket;

  /// Corresponding row in `event_interactions.type` — used both to trim
  /// duplicate chips on cards ("we're already in the Saved tab, don't
  /// re-show `Saved`") and to power the row's Remove action.
  final String interactionType;
  final String label;
  final IconData icon;
  final Color accent;
  final String emptyTitle;
  final String emptyBody;
  const _BucketTab({
    required this.bucket,
    required this.interactionType,
    required this.label,
    required this.icon,
    required this.accent,
    required this.emptyTitle,
    required this.emptyBody,
  });
}

/// Custom pill-style tab strip. We rebuild it from `TabController.animation`
/// so both direct taps and horizontal swipes on the [TabBarView] animate the
/// selection smoothly.
class _TabPillBar extends StatelessWidget {
  final List<_BucketTab> tabs;
  final TabController controller;
  final Map<String, int> counts;

  const _TabPillBar({
    required this.tabs,
    required this.controller,
    required this.counts,
  });

  @override
  Widget build(BuildContext context) {
    final selectedIndex = controller.index;
    return SizedBox(
      height: 60,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
        itemCount: tabs.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final tab = tabs[i];
          return _TabPill(
            tab: tab,
            selected: selectedIndex == i,
            count: counts[tab.bucket] ?? 0,
            onTap: () => controller.animateTo(i),
          );
        },
      ),
    );
  }
}

class _TabPill extends StatelessWidget {
  final _BucketTab tab;
  final bool selected;
  final int count;
  final VoidCallback onTap;

  const _TabPill({
    required this.tab,
    required this.selected,
    required this.count,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final bg = selected ? tab.accent : AppColors.surface;
    final fg = selected ? Colors.white : AppColors.textSecondary;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppRadius.borderFull,
        border: Border.all(
          color: selected ? Colors.transparent : AppColors.borderLight,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: tab.accent.withValues(alpha: 0.28),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ]
            : null,
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: AppRadius.borderFull,
        child: InkWell(
          borderRadius: AppRadius.borderFull,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(tab.icon, size: 14, color: fg),
                const SizedBox(width: 6),
                Text(
                  tab.label,
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: fg,
                    letterSpacing: 0.1,
                  ),
                ),
                if (count > 0) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: selected
                          ? Colors.white.withValues(alpha: 0.22)
                          : tab.accent.withValues(alpha: 0.14),
                      borderRadius: AppRadius.borderFull,
                    ),
                    child: Text(
                      '$count',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: selected ? Colors.white : tab.accent,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BucketList extends StatelessWidget {
  final _BucketTab tab;
  final List<EventRead> events;
  final Future<void> Function() onRefresh;

  const _BucketList({
    required this.tab,
    required this.events,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return RefreshIndicator(
        color: tab.accent,
        onRefresh: onRefresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(top: 64),
          children: [_EmptyState(tab: tab)],
        ),
      );
    }
    return RefreshIndicator(
      color: tab.accent,
      onRefresh: onRefresh,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 32),
        itemCount: events.length,
        separatorBuilder: (_, _) => const SizedBox(height: 12),
        itemBuilder: (context, i) => _EventRow(
          event: events[i],
          tab: tab,
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final _BucketTab tab;
  const _EmptyState({required this.tab});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 84,
            height: 84,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  tab.accent.withValues(alpha: 0.20),
                  tab.accent.withValues(alpha: 0.04),
                ],
              ),
              border: Border.all(color: tab.accent.withValues(alpha: 0.24)),
            ),
            child: Icon(tab.icon, color: tab.accent, size: 36),
          ),
          const SizedBox(height: 18),
          Text(
            tab.emptyTitle,
            textAlign: TextAlign.center,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 17,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            tab.emptyBody,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

class _EventRow extends StatelessWidget {
  final EventRead event;
  final _BucketTab tab;

  const _EventRow({required this.event, required this.tab});

  @override
  Widget build(BuildContext context) {
    final start = event.startTime?.toLocal();
    final startText = start == null
        ? 'Time TBA'
        : DateFormat('EEE, MMM d · h:mm a').format(start);
    final services = ServiceScope.of(context);
    final store = services.eventInteractions;
    final userId = services.session.userId;
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final active = store.typesFor(event.id);
        // Only show *user-managed* cross-signals that are semantically
        // distinct from the current tab. `like` is an implicit taste
        // signal (Discover swipe deck), not a shortlist — showing it as
        // a chip would suggest the user manages it, which they don't.
        // `add_to_my_day` / `add_to_calendar` overlap with Save/RSVP.
        final extras = active
            .where((t) {
              if (t == tab.interactionType) return false;
              if (t == 'like') return false;
              if (t == 'add_to_my_day' || t == 'add_to_calendar') return false;
              return true;
            })
            .take(2)
            .toList();

        return Material(
          color: Colors.transparent,
          borderRadius: AppRadius.borderLg,
          child: InkWell(
            borderRadius: AppRadius.borderLg,
            onTap: () => _openSheet(context, services, event),
            child: Ink(
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.borderLg,
                border: Border.all(color: AppColors.borderLight),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x0F0F172A),
                    blurRadius: 14,
                    offset: Offset(0, 4),
                  ),
                ],
              ),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      width: 5,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            tab.accent,
                            tab.accent.withValues(alpha: 0.55),
                          ],
                        ),
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(AppRadius.lg),
                          bottomLeft: Radius.circular(AppRadius.lg),
                        ),
                      ),
                    ),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                Expanded(
                                  child: _TrackPill(
                                    label: event.track ?? event.status,
                                    accent: tab.accent,
                                  ),
                                ),
                                if (userId != null &&
                                    tab.bucket != 'upcoming_rsvp')
                                  _RemoveIconButton(
                                    onTap: () async {
                                      try {
                                        await store.setActive(
                                          userId: userId,
                                          eventId: event.id,
                                          type: tab.interactionType,
                                          active: false,
                                        );
                                        if (!context.mounted) return;
                                        showInfoSnack(
                                          context,
                                          'Removed from ${tab.label}',
                                        );
                                      } catch (e) {
                                        if (!context.mounted) return;
                                        showErrorSnack(context, e);
                                      }
                                    },
                                  ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Text(
                              event.title,
                              style: GoogleFonts.plusJakartaSans(
                                fontSize: 15.5,
                                fontWeight: FontWeight.w800,
                                color: AppColors.textPrimary,
                                height: 1.25,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 8),
                            _MetaLine(
                              startText: startText,
                              location: event.locationSummary,
                            ),
                            if (extras.isNotEmpty) ...[
                              const SizedBox(height: 12),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: extras
                                    .map((t) => _CrossSignalChip(type: t))
                                    .toList(),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _openSheet(
      BuildContext context, Services services, EventRead event) async {
    try {
      final refreshed = await services.events.get(event.id);
      if (!context.mounted) return;
      await showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => EventDetailSheet(
          card: EventCard(
            event: refreshed,
            prompts: const [],
            alreadyLikedSpeaker: false,
          ),
        ),
      );
    } catch (e) {
      if (!context.mounted) return;
      showErrorSnack(context, e);
    }
  }
}

class _TrackPill extends StatelessWidget {
  final String label;
  final Color accent;
  const _TrackPill({required this.label, required this.accent});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: accent.withValues(alpha: 0.12),
          borderRadius: AppRadius.borderFull,
          border: Border.all(color: accent.withValues(alpha: 0.22)),
        ),
        child: Text(
          label.toUpperCase(),
          style: GoogleFonts.plusJakartaSans(
            fontSize: 10.5,
            fontWeight: FontWeight.w800,
            color: accent,
            letterSpacing: 0.6,
          ),
        ),
      ),
    );
  }
}

class _MetaLine extends StatelessWidget {
  final String startText;
  final String location;
  const _MetaLine({required this.startText, required this.location});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.schedule_rounded,
                size: 13, color: AppColors.textTertiary),
            const SizedBox(width: 4),
            Text(
              startText,
              style: const TextStyle(
                  fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
        if (location.isNotEmpty)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.place_rounded,
                  size: 13, color: AppColors.textTertiary),
              const SizedBox(width: 3),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 180),
                child: Text(
                  location,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 12, color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class _CrossSignalChip extends StatelessWidget {
  final String type;
  const _CrossSignalChip({required this.type});

  @override
  Widget build(BuildContext context) {
    final (icon, label, color) = switch (type) {
      'rsvp' => (
          Icons.event_available_rounded,
          'Going',
          const Color(0xFF14B8A6)
        ),
      'save' => (Icons.bookmark_rounded, 'Saved', const Color(0xFF0EA5E9)),
      'mark_attended' => (
          Icons.check_circle_rounded,
          'Attended',
          const Color(0xFF8B5CF6)
        ),
      _ => (Icons.check_rounded, type, AppColors.accentDark),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              color: color,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }
}

class _RemoveIconButton extends StatelessWidget {
  final VoidCallback onTap;
  const _RemoveIconButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 32,
      height: 32,
      child: Material(
        color: AppColors.surfaceVariant,
        borderRadius: AppRadius.borderFull,
        child: InkWell(
          borderRadius: AppRadius.borderFull,
          onTap: onTap,
          child: Icon(Icons.close_rounded,
              size: 16, color: AppColors.textSecondary),
        ),
      ),
    );
  }
}

class _FooterSummary extends StatelessWidget {
  final _BucketTab tab;
  final int count;
  const _FooterSummary({required this.tab, required this.count});

  @override
  Widget build(BuildContext context) {
    if (count == 0) return const SizedBox.shrink();
    final noun = count == 1 ? 'session' : 'sessions';
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      child: Container(
        key: ValueKey('${tab.bucket}-$count'),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: AppRadius.borderMd,
          border: Border.all(color: AppColors.borderLight),
        ),
        child: Row(
          children: [
            Container(
              width: 26,
              height: 26,
              decoration: BoxDecoration(
                color: tab.accent.withValues(alpha: 0.14),
                shape: BoxShape.circle,
              ),
              child: Icon(tab.icon, size: 14, color: tab.accent),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: RichText(
                text: TextSpan(
                  style: const TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textSecondary,
                  ),
                  children: [
                    TextSpan(
                      text: '$count',
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    TextSpan(text: ' $noun in ${tab.label}'),
                  ],
                ),
              ),
            ),
            Text(
              'Pull to refresh',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final VoidCallback onRetry;
  const _ErrorState({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.cloud_off_rounded,
              size: 40, color: AppColors.textTertiary),
          const SizedBox(height: 10),
          const Text('Could not load your activity.'),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: onRetry, child: const Text('Try again')),
        ],
      ),
    );
  }
}
