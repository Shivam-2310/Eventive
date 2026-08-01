import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../app_shell.dart' show kAppHeaderHeight;
import '../../models/event.dart';
import '../../models/recommendation.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../utils/haptics.dart';
import '../../utils/ui_errors.dart';
import '../../widgets/cards/card_stack.dart';
import 'detail/event_sheet.dart';
import 'detail/person_sheet.dart';
import 'widgets/event_card.dart';
import 'widgets/event_row.dart';
import 'widgets/person_card.dart';

enum FlonnectMode { events, people }

/// Sub-modes for the Events tab.
///
/// * [all] — a chronological, light-themed list backed by `/events/discover`
///   (cursor-paginated) with an inline search field that filters the already
///   loaded page client-side. Feels like the rest of the app (My Activity,
///   Profile, etc.), not like Hinge.
/// * [forYou] — the interest-scored deck backed by `/events/discover/for-you`.
///   Full-bleed Hinge-style cards deliberately, so the personalisation moment
///   feels distinct.
enum EventDeckMode { all, forYou }

/// The main discovery surface — chronological Events list, personalised For
/// You deck, or People recommendations.
class FlonnectScreen extends StatefulWidget {
  const FlonnectScreen({super.key});

  @override
  State<FlonnectScreen> createState() => _FlonnectScreenState();
}

class _FlonnectScreenState extends State<FlonnectScreen> {
  FlonnectMode _mode = FlonnectMode.events;
  EventDeckMode _eventDeck = EventDeckMode.all;

  final List<EventCard> _eventCards = [];
  int? _eventCursor;
  bool _loadingEvents = false;
  bool _eventsError = false;
  bool _eventsExhausted = false;

  final List<EventCard> _forYouCards = [];
  bool _loadingForYou = false;
  bool _forYouError = false;
  bool _forYouLoadedOnce = false;

  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _allEventsScroll = ScrollController();

  final List<PersonRecommendation> _people = [];
  bool _loadingPeople = false;
  bool _peopleError = false;

  bool _hydrated = false;

  @override
  void initState() {
    super.initState();
    // Infinite scroll for the "All events" chronological list. We prefetch
    // when the user is within ~400px of the bottom so the next page has
    // usually landed by the time they get there.
    _allEventsScroll.addListener(() {
      if (!_allEventsScroll.hasClients) return;
      final pos = _allEventsScroll.position;
      if (pos.pixels >= pos.maxScrollExtent - 400) {
        if (_mode == FlonnectMode.events &&
            _eventDeck == EventDeckMode.all &&
            !_loadingEvents &&
            !_eventsExhausted) {
          _loadMoreEvents();
        }
      }
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _allEventsScroll.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _loadInitial();
    }
  }

  Future<void> _loadInitial() async {
    _loadMoreEvents(reset: true);
    _loadPeople();
  }

  Future<void> _loadMoreEvents({bool reset = false}) async {
    if (_loadingEvents) return;
    if (_eventsExhausted && !reset) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _loadingEvents = true;
      _eventsError = false;
      if (reset) {
        _eventCards.clear();
        _eventCursor = null;
        _eventsExhausted = false;
      }
    });
    try {
      final page = await services.events.discover(
        userId: userId,
        cursor: _eventCursor,
        limit: 10,
      );
      if (!mounted) return;
      setState(() {
        _eventCards.addAll(page.cards);
        _eventCursor = page.nextCursor;
        _loadingEvents = false;
        if (page.cards.isEmpty || page.nextCursor == null) {
          _eventsExhausted = true;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingEvents = false;
        _eventsError = true;
      });
      showErrorSnack(context, e);
    }
  }

  Future<void> _loadForYou({bool reset = false}) async {
    if (_loadingForYou) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _loadingForYou = true;
      _forYouError = false;
      if (reset) _forYouCards.clear();
    });
    try {
      final page = await services.events.discoverForYou(
        userId: userId,
        limit: 20,
      );
      if (!mounted) return;
      setState(() {
        _forYouCards
          ..clear()
          ..addAll(page.cards);
        _loadingForYou = false;
        _forYouLoadedOnce = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingForYou = false;
        _forYouError = true;
      });
      showErrorSnack(context, e);
    }
  }

  Future<void> _loadPeople() async {
    if (_loadingPeople) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _loadingPeople = true;
      _peopleError = false;
    });
    try {
      final list = await services.recommendations.people(userId, limit: 30);
      if (!mounted) return;
      setState(() {
        _people
          ..clear()
          ..addAll(list);
        _loadingPeople = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingPeople = false;
        _peopleError = true;
      });
      showErrorSnack(context, e);
    }
  }

  /// Right-swipe on an event card = **Save**.
  ///
  /// The gesture writes three things, in decreasing order of user visibility:
  ///
  /// 1. `EventInteraction(type='save')` — the user-facing shortlist. The
  ///    card immediately appears in Profile → Saved and the notifier
  ///    queues a soft 10-min "Still want to catch...?" nudge.
  /// 2. `EventCardReaction(prompt_type='cover', reaction='like')` — the
  ///    positive taste signal that trains the Discover recommender. Never
  ///    surfaced back to the user.
  /// 3. `EventInteraction(type='like')` — internal engagement counter used
  ///    by the `like_events` mission and the admin pulse dashboard. Kept
  ///    as an invisible dual-write so those downstream counters keep
  ///    working; the user never sees it.
  ///
  /// The RSVP path stays deliberate — swiping doesn't commit you to
  /// showing up, it just adds to your shortlist. Firm reminders only
  /// arrive if the user opens the sheet and taps "I'm going".
  void _onEventLike(EventCard card) async {
    AppHaptics.light();
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId != null) {
      try {
        await services.events.react(
          card.event.id,
          userId: userId,
          promptType: 'cover',
          reaction: 'like',
        );
        // Save = the visible shortlist bucket (soft nudge, Profile → Saved).
        await services.eventInteractions.setActive(
          userId: userId,
          eventId: card.event.id,
          type: 'save',
          active: true,
        );
        // Internal like-counter for missions / pulse. Fire-and-forget:
        // if it fails, the save above still succeeded and the user sees
        // no error — mission progress will simply lag by one tick.
        unawaited(
          services.eventInteractions
              .setActive(
                userId: userId,
                eventId: card.event.id,
                type: 'like',
                active: true,
              )
              .catchError((_) {}),
        );
        if (mounted) {
          showInfoSnack(
            context,
            'Saved — we\'ll nudge you 10 min before it starts.',
          );
        }
      } catch (e) {
        if (!mounted) return;
        showErrorSnack(context, e);
      }
    }
    _popEventCard(card);
  }

  void _onEventDislike(EventCard card) async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId != null) {
      try {
        await services.events.react(
          card.event.id,
          userId: userId,
          promptType: 'cover',
          reaction: 'pass',
        );
      } catch (_) {}
    }
    _popEventCard(card);
  }

  void _popEventCard(EventCard card) {
    setState(() {
      _eventCards.remove(card);
      _forYouCards.removeWhere((c) => c.event.id == card.event.id);
    });
    if (_eventDeck == EventDeckMode.forYou && _forYouCards.length < 3) {
      _loadForYou(reset: true);
    }
  }

  void _onPersonLike(PersonRecommendation p) async {
    AppHaptics.light();
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId != null) {
      try {
        await services.chat.requestConnection(
          requesterId: userId,
          receiverId: p.otherUserId,
        );
        if (mounted) showInfoSnack(context, 'Connection request sent');
      } catch (e) {
        if (!mounted) return;
        showErrorSnack(context, e);
      }
    }
    setState(() => _people.remove(p));
  }

  void _onPersonDislike(PersonRecommendation p) {
    setState(() => _people.remove(p));
  }

  void _onEventTap(EventCard card) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => EventDetailSheet(card: card),
    );
  }

  void _onPersonTap(PersonRecommendation p) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => PersonDetailSheet(person: p),
    );
  }

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;
    final isAllList =
        _mode == FlonnectMode.events && _eventDeck == EventDeckMode.all;

    // The "All events" branch owns a full light-themed scaffold (its own
    // header, search field and list). The other two branches are full-bleed
    // Hinge-style decks with a floating dark pill overlay.
    if (isAllList) {
      return _buildAllEventsScaffold(topPadding);
    }

    final body =
        _mode == FlonnectMode.events ? _buildForYouDeck() : _buildPeople();
    // The immersive Hinge-style decks use a card with rounded corners
    // (ClipRRect in SwipeableCard). Without a dark backdrop, those rounded
    // corners reveal the Scaffold's default white background as small white
    // wedges at the bottom-left / bottom-right of every card. Painting a
    // solid black layer behind the deck keeps the corner cuts consistent
    // with the card's dark aesthetic and makes the card visually cover the
    // entire viewport.
    return ColoredBox(
      color: Colors.black,
      child: Stack(
        children: [
          Positioned.fill(child: body),
          Positioned(
            top: topPadding + kAppHeaderHeight + 12,
            left: 0,
            right: 0,
            child: Center(child: _buildModeToggle(dark: true)),
          ),
          if (_mode == FlonnectMode.events)
            Positioned(
              top: topPadding + kAppHeaderHeight + 64,
              left: 0,
              right: 0,
              child: Center(child: _buildEventSubToggle(dark: true)),
            ),
        ],
      ),
    );
  }

  // ─────────────────────────────  All Events (light)  ─────────────────────

  Widget _buildAllEventsScaffold(double topPadding) {
    return Container(
      color: AppColors.background,
      child: Column(
        children: [
          SizedBox(height: topPadding + kAppHeaderHeight + 12),
          Center(child: _buildModeToggle(dark: false)),
          const SizedBox(height: 10),
          Center(child: _buildEventSubToggle(dark: false)),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: _LightSearchField(
              controller: _searchController,
              onChanged: (v) => setState(() => _searchQuery = v),
              onClear: () {
                _searchController.clear();
                setState(() => _searchQuery = '');
              },
              hasText: _searchQuery.isNotEmpty,
            ),
          ),
          const SizedBox(height: 12),
          Expanded(child: _buildAllEventsBody()),
        ],
      ),
    );
  }

  Widget _buildAllEventsBody() {
    if (_loadingEvents && _eventCards.isEmpty) {
      return const Center(
        child: CircularProgressIndicator(color: AppColors.accent),
      );
    }
    if (_eventsError && _eventCards.isEmpty) {
      return _LightErrorState(
        message: 'Could not load events.',
        onRetry: () => _loadMoreEvents(reset: true),
      );
    }

    final visible = _filteredEventCards();

    if (visible.isEmpty) {
      return _searchQuery.isNotEmpty
          ? _LightSearchEmptyState(
              query: _searchQuery,
              onClear: () {
                _searchController.clear();
                setState(() => _searchQuery = '');
              },
            )
          : _LightEmptyState(
              icon: Icons.event_rounded,
              title: "No events available",
              body: 'Check back soon — new sessions get added regularly.',
              actionLabel: 'Refresh',
              onAction: () => _loadMoreEvents(reset: true),
            );
    }

    return RefreshIndicator(
      color: AppColors.accent,
      onRefresh: () => _loadMoreEvents(reset: true),
      child: ListView.separated(
        controller: _allEventsScroll,
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 40),
        itemCount: visible.length + (_eventsExhausted ? 0 : 1),
        separatorBuilder: (_, _) => const SizedBox(height: 10),
        itemBuilder: (context, i) {
          if (i >= visible.length) {
            return const _ListLoadMoreTile();
          }
          final card = visible[i];
          return EventListRow(
            card: card,
            onTap: () => _onEventTap(card),
          );
        },
      ),
    );
  }

  List<EventCard> _filteredEventCards() {
    final q = _searchQuery.trim().toLowerCase();
    if (q.isEmpty) return _eventCards;
    return _eventCards.where((card) {
      final ev = card.event;
      if (ev.title.toLowerCase().contains(q)) return true;
      if ((ev.track ?? '').toLowerCase().contains(q)) return true;
      for (final tag in ev.interests) {
        if (tag.label.toLowerCase().contains(q)) return true;
      }
      for (final speaker in ev.speakers) {
        if (speaker.name.toLowerCase().contains(q)) return true;
      }
      return false;
    }).toList();
  }

  // ─────────────────────────────  For You (dark deck)  ─────────────────────

  Widget _buildForYouDeck() {
    if (_loadingForYou && _forYouCards.isEmpty) {
      return const _DarkLoader();
    }
    if (_forYouError && _forYouCards.isEmpty) {
      return _DarkErrorState(
        message: 'Could not load your For You feed.',
        onRetry: () => _loadForYou(reset: true),
      );
    }
    return CardStack<EventCard>(
      key: const ValueKey('events-foryou'),
      items: _forYouCards,
      cardBuilder: (card) => EventCardWidget(card: card),
      onLike: _onEventLike,
      onDislike: _onEventDislike,
      onTap: _onEventTap,
      // Right-swipe on an event is now Save (not a Tinder-style Like).
      rightSwipeLabel: 'SAVE',
      leftSwipeLabel: 'PASS',
      emptyState: _ForYouEmptyState(onRefresh: () => _loadForYou(reset: true)),
    );
  }

  // ─────────────────────────────  People (dark deck)  ──────────────────────

  Widget _buildPeople() {
    if (_loadingPeople && _people.isEmpty) {
      return const _DarkLoader();
    }
    if (_peopleError && _people.isEmpty) {
      return _DarkErrorState(
        message: 'Could not load recommendations.',
        onRetry: _loadPeople,
      );
    }
    return CardStack<PersonRecommendation>(
      key: const ValueKey('people'),
      items: _people,
      cardBuilder: (p) => PersonCardWidget(person: p),
      onLike: _onPersonLike,
      onDislike: _onPersonDislike,
      onTap: _onPersonTap,
      emptyState: _PeopleEmptyState(onRefresh: _loadPeople),
    );
  }

  // ─────────────────────────────  Toggle chrome  ───────────────────────────

  Widget _buildModeToggle({required bool dark}) {
    return _PillContainer(
      dark: dark,
      radius: 30,
      innerHPad: 6,
      innerVPad: 4,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _PillButton(
            label: 'Events',
            selected: _mode == FlonnectMode.events,
            dark: dark,
            hPad: 20,
            vPad: 8,
            fontSize: 14,
            radius: 24,
            onTap: () {
              if (_mode == FlonnectMode.events) return;
              AppHaptics.selection();
              setState(() => _mode = FlonnectMode.events);
            },
          ),
          _PillButton(
            label: 'People',
            selected: _mode == FlonnectMode.people,
            dark: dark,
            hPad: 20,
            vPad: 8,
            fontSize: 14,
            radius: 24,
            onTap: () {
              if (_mode == FlonnectMode.people) return;
              AppHaptics.selection();
              setState(() => _mode = FlonnectMode.people);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildEventSubToggle({required bool dark}) {
    return _PillContainer(
      dark: dark,
      radius: 24,
      innerHPad: 4,
      innerVPad: 3,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _PillButton(
            label: 'All',
            selected: _eventDeck == EventDeckMode.all,
            dark: dark,
            hPad: 18,
            vPad: 7,
            fontSize: 12.5,
            radius: 20,
            onTap: () => _switchDeck(EventDeckMode.all),
          ),
          _PillButton(
            label: 'For You',
            selected: _eventDeck == EventDeckMode.forYou,
            dark: dark,
            hPad: 18,
            vPad: 7,
            fontSize: 12.5,
            radius: 20,
            leading: Icon(
              Icons.auto_awesome_rounded,
              size: 12,
              color: _eventDeck == EventDeckMode.forYou
                  ? (dark ? Colors.white : AppColors.accentDark)
                  : (dark
                      ? Colors.white.withValues(alpha: 0.55)
                      : AppColors.textTertiary),
            ),
            onTap: () => _switchDeck(EventDeckMode.forYou),
          ),
        ],
      ),
    );
  }

  void _switchDeck(EventDeckMode deck) {
    if (_eventDeck == deck) return;
    AppHaptics.selection();
    setState(() => _eventDeck = deck);
    if (deck == EventDeckMode.forYou && !_forYouLoadedOnce) {
      _loadForYou();
    }
  }
}

// ═════════════════════════════  Toggle primitives  ═════════════════════════

class _PillContainer extends StatelessWidget {
  final bool dark;
  final double radius;
  final double innerHPad;
  final double innerVPad;
  final Widget child;

  const _PillContainer({
    required this.dark,
    required this.radius,
    required this.innerHPad,
    required this.innerVPad,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: innerHPad, vertical: innerVPad),
      decoration: dark
          ? BoxDecoration(
              color: Colors.black.withValues(alpha: 0.25),
              borderRadius: BorderRadius.circular(radius),
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
            )
          : BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(radius),
              border: Border.all(color: AppColors.border),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
      child: child,
    );
  }
}

class _PillButton extends StatelessWidget {
  final String label;
  final bool selected;
  final bool dark;
  final double hPad;
  final double vPad;
  final double fontSize;
  final double radius;
  final Widget? leading;
  final VoidCallback onTap;

  const _PillButton({
    required this.label,
    required this.selected,
    required this.dark,
    required this.hPad,
    required this.vPad,
    required this.fontSize,
    required this.radius,
    this.leading,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final Color bg;
    final Color fg;
    if (dark) {
      bg = selected ? Colors.white.withValues(alpha: 0.18) : Colors.transparent;
      fg = selected ? Colors.white : Colors.white.withValues(alpha: 0.62);
    } else {
      bg = selected ? AppColors.accentLight : Colors.transparent;
      fg = selected ? AppColors.accentDark : AppColors.textSecondary;
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.symmetric(horizontal: hPad, vertical: vPad),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (leading != null) ...[
              leading!,
              const SizedBox(width: 5),
            ],
            Text(
              label,
              style: GoogleFonts.plusJakartaSans(
                fontSize: fontSize,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                color: fg,
                letterSpacing: -0.1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═════════════════════════════  Search field  ══════════════════════════════

class _LightSearchField extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onClear;
  final bool hasText;

  const _LightSearchField({
    required this.controller,
    required this.onChanged,
    required this.onClear,
    required this.hasText,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 46,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          Icon(Icons.search_rounded, size: 20, color: AppColors.textTertiary),
          const SizedBox(width: 10),
          Expanded(
            child: TextField(
              controller: controller,
              onChanged: onChanged,
              cursorColor: AppColors.accent,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 14,
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w500,
              ),
              decoration: InputDecoration(
                border: InputBorder.none,
                isDense: true,
                contentPadding: EdgeInsets.zero,
                hintText: 'Search by title, track, tag or speaker',
                hintStyle: GoogleFonts.plusJakartaSans(
                  fontSize: 13.5,
                  color: AppColors.textTertiary,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ),
          if (hasText)
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onClear,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: AppColors.surfaceMuted,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.close_rounded,
                    size: 14,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// ═════════════════════════════  List trailing tile  ════════════════════════

class _ListLoadMoreTile extends StatelessWidget {
  const _ListLoadMoreTile();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 16),
      child: Center(
        child: SizedBox(
          width: 22,
          height: 22,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppColors.accent,
          ),
        ),
      ),
    );
  }
}

// ═════════════════════════════  Light empty / error  ══════════════════════

class _LightEmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;
  final String actionLabel;
  final VoidCallback onAction;

  const _LightEmptyState({
    required this.icon,
    required this.title,
    required this.body,
    required this.actionLabel,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 68,
              height: 68,
              decoration: BoxDecoration(
                color: AppColors.accentLight,
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: AppColors.accentDark, size: 30),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: GoogleFonts.plusJakartaSans(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              body,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textSecondary,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 18),
            OutlinedButton(
              onPressed: onAction,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.accentDark,
                side: BorderSide(color: AppColors.accent.withValues(alpha: 0.4)),
                padding:
                    const EdgeInsets.symmetric(horizontal: 22, vertical: 10),
                shape: RoundedRectangleBorder(
                  borderRadius: AppRadius.borderFull,
                ),
              ),
              child: Text(actionLabel),
            ),
          ],
        ),
      ),
    );
  }
}

class _LightSearchEmptyState extends StatelessWidget {
  final String query;
  final VoidCallback onClear;
  const _LightSearchEmptyState({required this.query, required this.onClear});

  @override
  Widget build(BuildContext context) {
    return _LightEmptyState(
      icon: Icons.search_off_rounded,
      title: 'No matches for "$query"',
      body: 'Try a broader search, or clear it to see every session.',
      actionLabel: 'Clear search',
      onAction: onClear,
    );
  }
}

class _LightErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _LightErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return _LightEmptyState(
      icon: Icons.cloud_off_rounded,
      title: 'Offline for a sec',
      body: message,
      actionLabel: 'Try again',
      onAction: onRetry,
    );
  }
}

// ═════════════════════════════  Dark empty / error (decks)  ════════════════

class _DarkLoader extends StatelessWidget {
  const _DarkLoader();

  @override
  Widget build(BuildContext context) => Container(
        color: AppColors.background,
        alignment: Alignment.center,
        child: const CircularProgressIndicator(color: AppColors.accent),
      );
}

class _DarkErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _DarkErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_rounded,
              size: 42, color: AppColors.textTertiary),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 15,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(onPressed: onRetry, child: const Text('Try again')),
        ],
      ),
    );
  }
}

class _ForYouEmptyState extends StatelessWidget {
  final VoidCallback onRefresh;
  const _ForYouEmptyState({required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.auto_awesome_rounded, size: 42, color: AppColors.accent),
          const SizedBox(height: 12),
          const Text(
            'No personalised picks yet',
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 17,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Add or refine your interests in Profile to power this feed.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textTertiary),
          ),
          const SizedBox(height: 16),
          ElevatedButton(onPressed: onRefresh, child: const Text('Refresh')),
        ],
      ),
    );
  }
}

class _PeopleEmptyState extends StatelessWidget {
  final VoidCallback onRefresh;
  const _PeopleEmptyState({required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.people_rounded, size: 42, color: AppColors.accent),
          const SizedBox(height: 12),
          const Text(
            "No new people yet",
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 17,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Add interests in your profile to power recommendations.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textTertiary),
          ),
          const SizedBox(height: 16),
          ElevatedButton(onPressed: onRefresh, child: const Text('Refresh')),
        ],
      ),
    );
  }
}
