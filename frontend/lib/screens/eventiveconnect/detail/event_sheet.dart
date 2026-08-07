import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../../models/event.dart';
import '../../../models/speaker.dart';
import '../../../services/event_interactions_store.dart';
import '../../../services/services.dart';
import '../../../theme/colors.dart';
import '../../../theme/radius.dart';
import '../../../utils/haptics.dart';
import '../../../utils/ui_errors.dart';
import '../../speakers/speaker_detail_screen.dart';

/// Bottom sheet that opens when a user taps an event card.
///
/// Renders the event, its prompt tiles, and — most importantly — an
/// interactive action rail whose chips are wired to
/// [EventInteractionsStore] so their selected/loading state is shared
/// across every screen in the app.
class EventDetailSheet extends StatefulWidget {
  final EventCard card;

  const EventDetailSheet({super.key, required this.card});

  @override
  State<EventDetailSheet> createState() => _EventDetailSheetState();
}

class _EventDetailSheetState extends State<EventDetailSheet> {
  late EventRead _event;
  late List<EventCardPrompt> _prompts;
  bool _refreshing = false;
  bool _refreshingVibe = false;
  final Set<String> _busyInteractions = <String>{};

  @override
  void initState() {
    super.initState();
    _event = widget.card.event;
    // Reorder so the most information-dense highlights land first:
    // vibe → topic → speaker → when/where → who's going. The `cover` prompt
    // is dropped inside `_sortedPrompts` because its label duplicates the
    // sheet header and its body is a raw URL.
    _prompts = _sortedPrompts(List.of(widget.card.prompts));
  }

  static const _promptOrder = <String>[
    'vibe',
    'topic',
    'speaker',
    'when_where',
    'who_is_going',
  ];

  /// Filters + orders the prompts we surface as highlight tiles.
  ///
  /// `cover` is skipped: its `label` duplicates the sheet header and its
  /// `body` is a raw cover-image URL, not a human sentence. The remaining
  /// five prompts each carry a distinct signal worth showing.
  List<EventCardPrompt> _sortedPrompts(List<EventCardPrompt> raw) {
    final filtered =
        raw.where((p) => _promptOrder.contains(p.promptType)).toList();
    int rank(String type) {
      final i = _promptOrder.indexOf(type);
      return i < 0 ? _promptOrder.length : i;
    }
    filtered.sort((a, b) => rank(a.promptType).compareTo(rank(b.promptType)));
    return filtered;
  }

  Future<void> _refresh() async {
    if (_refreshing) return;
    setState(() => _refreshing = true);
    try {
      final fresh = await ServiceScope.of(context).events.get(_event.id);
      if (!mounted) return;
      setState(() => _event = fresh);
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  Future<void> _refreshVibe() async {
    if (_refreshingVibe) return;
    setState(() => _refreshingVibe = true);
    try {
      final j = await ServiceScope.of(context).events.refreshVibe(_event.id);
      final vibe = j['vibe']?.toString();
      if (!mounted) return;
      if (vibe != null) {
        setState(() {
          _event = _copyWithVibe(_event, vibe);
        });
        showInfoSnack(context, 'Regenerated the vibe for this session.');
      }
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _refreshingVibe = false);
    }
  }

  EventRead _copyWithVibe(EventRead e, String vibe) => EventRead(
        id: e.id,
        externalId: e.externalId,
        title: e.title,
        description: e.description,
        abstractText: e.abstractText,
        track: e.track,
        startTime: e.startTime,
        endTime: e.endTime,
        timezone: e.timezone,
        location: e.location,
        room: e.room,
        capacity: e.capacity,
        status: e.status,
        coverImageUrl: e.coverImageUrl,
        vibeText: vibe,
        createdAt: e.createdAt,
        updatedAt: DateTime.now().toUtc(),
        speakers: e.speakers,
        interests: e.interests,
      );

  Future<void> _toggleInteraction(_ActionSpec spec) async {
    if (_busyInteractions.contains(spec.type)) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    AppHaptics.light();
    setState(() => _busyInteractions.add(spec.type));
    try {
      final nowActive = await services.eventInteractions.toggle(
        userId: userId,
        eventId: _event.id,
        type: spec.type,
      );
      if (!mounted) return;
      showInfoSnack(
        context,
        nowActive ? spec.confirmedCopy : spec.removedCopy,
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busyInteractions.remove(spec.type));
    }
  }

  @override
  Widget build(BuildContext context) {
    final store = ServiceScope.of(context).eventInteractions;
    return DraggableScrollableSheet(
      initialChildSize: 0.9,
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
                child: RefreshIndicator(
                  color: AppColors.accent,
                  onRefresh: _refresh,
                  child: ListenableBuilder(
                    listenable: store,
                    builder: (context, _) => ListView(
                      controller: scrollController,
                      padding:
                          const EdgeInsets.fromLTRB(24, 20, 24, 40),
                      children: [
                        _buildHeader(),
                        const SizedBox(height: 20),
                        _buildInfoRow(),
                        const SizedBox(height: 24),
                        _buildActionsBlock(store),
                        const SizedBox(height: 24),
                        if (_event.description != null &&
                            _event.description!.isNotEmpty) ...[
                          _sectionTitle('About'),
                          const SizedBox(height: 8),
                          Text(
                            _event.description!,
                            style: const TextStyle(
                              fontSize: 15,
                              color: AppColors.textSecondary,
                              height: 1.6,
                            ),
                          ),
                          const SizedBox(height: 24),
                        ],
                        _highlightsHeader(),
                        const SizedBox(height: 12),
                        ..._buildPromptTiles(),
                        const SizedBox(height: 24),
                        if (_event.speakers.isNotEmpty) ...[
                          _sectionTitle('Speakers'),
                          const SizedBox(height: 8),
                          ..._event.speakers.map(_speakerTile),
                          const SizedBox(height: 24),
                        ],
                        if (_event.interests.isNotEmpty) ...[
                          _sectionTitle('Topics'),
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: _event.interests
                                .map(
                                  (t) => Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 14, vertical: 7),
                                    decoration: BoxDecoration(
                                      color: AppColors.accentLight,
                                      borderRadius: AppRadius.borderFull,
                                    ),
                                    child: Text(
                                      t.label,
                                      style: TextStyle(
                                        color: AppColors.accentDark,
                                        fontSize: 13,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                )
                                .toList(),
                          ),
                        ],
                        const SizedBox(height: 100),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            _event.title,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
              letterSpacing: -0.5,
              height: 1.2,
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: AppColors.accentLight,
            borderRadius: AppRadius.borderFull,
          ),
          child: Text(
            _event.status,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: AppColors.accentDark,
              letterSpacing: 0.5,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildInfoRow() {
    final start = _event.startTime?.toLocal();
    final startText =
        start == null ? 'TBA' : DateFormat('EEE, MMM d · h:mm a').format(start);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _infoPill(Icons.calendar_today_rounded, startText),
        _infoPill(Icons.location_on_rounded, _event.locationSummary),
        if (_event.track != null && _event.track!.isNotEmpty)
          _infoPill(Icons.category_rounded, _event.track!),
        if (_event.capacity != null)
          _infoPill(Icons.people_rounded, '${_event.capacity} cap.'),
      ],
    );
  }

  /// Action rail with real visual hierarchy — the flat "three equal chips"
  /// row was giving the impression that RSVP, Save, and Attended are peer
  /// choices, which caused users to hesitate over which one to press.
  /// Now they're tiered:
  ///
  /// * **Primary** — big filled Going / Attending CTA. This is the
  ///   commitment path and the only one wired to a firm reminder push.
  /// * **Secondary** — a quiet outlined Save toggle for soft intent
  ///   ("I'm interested, don't commit me"). Gets a single soft nudge.
  /// * **Tertiary** — Attended chip that only appears once the session
  ///   has actually started. Progressive disclosure — you can't attend
  ///   something that hasn't happened yet.
  Widget _buildActionsBlock(EventInteractionsStore store) {
    final active = store.typesFor(_event.id);
    final rsvp = _actionSpecs.firstWhere((s) => s.type == 'rsvp');
    final save = _actionSpecs.firstWhere((s) => s.type == 'save');
    final attended = _actionSpecs.firstWhere((s) => s.type == 'mark_attended');

    final start = _event.startTime;
    final now = DateTime.now().toUtc();
    // Show "Attended" only once the event is under way (or done). This
    // eliminates one of the three visible actions for anyone browsing
    // a future session, leaving the choice at "Going vs Save" — the
    // meaningful pre-event fork.
    final canMarkAttended = start != null && !start.toUtc().isAfter(now);

    final rsvpActive = active.contains(rsvp.type);
    final saveActive = active.contains(save.type);
    final attendedActive = active.contains(attended.type);

    // The contextual hint picks the most-recently-relevant intent so the
    // helper text below the buttons always speaks to what the user just
    // did (or is most likely about to do).
    final _ActionSpec hintSource = rsvpActive
        ? rsvp
        : saveActive
            ? save
            : attendedActive
                ? attended
                : rsvp;
    final bool hintSelected = active.contains(hintSource.type);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _PrimaryActionButton(
          spec: rsvp,
          selected: rsvpActive,
          busy: _busyInteractions.contains(rsvp.type),
          onTap: () => _toggleInteraction(rsvp),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _SecondaryActionButton(
                spec: save,
                selected: saveActive,
                busy: _busyInteractions.contains(save.type),
                onTap: () => _toggleInteraction(save),
              ),
            ),
            if (canMarkAttended) ...[
              const SizedBox(width: 10),
              Expanded(
                child: _SecondaryActionButton(
                  spec: attended,
                  selected: attendedActive,
                  busy: _busyInteractions.contains(attended.type),
                  onTap: () => _toggleInteraction(attended),
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 14),
        _actionHint(hintSource, hintSelected),
      ],
    );
  }

  Widget _actionHint(_ActionSpec spec, bool selected) {
    final text = selected ? spec.selectedHint : spec.idleHint;
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      child: Container(
        key: ValueKey('hint-${spec.type}-$selected'),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: AppRadius.borderMd,
          border: Border.all(color: AppColors.borderLight),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              selected ? Icons.check_circle_rounded : Icons.lightbulb_rounded,
              size: 16,
              color: selected ? AppColors.accent : AppColors.textTertiary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.4,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Section header for "Session highlights" — a title on the left, a small
  /// inline text button on the right that lets Eventive rewrite the vibe line.
  /// The vibe rewrite is contextual to this section (it changes the "Vibe"
  /// highlight tile), so it lives here rather than competing with the
  /// primary Save / RSVP / Attended actions at the top.
  Widget _highlightsHeader() {
    return Row(
      children: [
        _sectionTitle('Session highlights'),
        const Spacer(),
        _refreshVibeInline(),
      ],
    );
  }

  Widget _refreshVibeInline() {
    return Tooltip(
      message: 'Ask Eventive to rewrite the vibe line using its latest signals.',
      waitDuration: const Duration(milliseconds: 300),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: AppRadius.borderFull,
          onTap: _refreshingVibe ? null : _refreshVibe,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutCubic,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            decoration: BoxDecoration(
              color: _refreshingVibe
                  ? AppColors.accentLight
                  : AppColors.accentLight.withValues(alpha: 0.7),
              borderRadius: AppRadius.borderFull,
              border: Border.all(
                color: AppColors.accent.withValues(alpha: 0.35),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_refreshingVibe)
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(
                      color: AppColors.accentDark,
                      strokeWidth: 2,
                    ),
                  )
                else
                  Icon(
                    Icons.auto_awesome_rounded,
                    size: 13,
                    color: AppColors.accentDark,
                  ),
                const SizedBox(width: 6),
                Text(
                  _refreshingVibe ? 'Rewriting…' : 'Refresh vibe',
                  style: TextStyle(
                    color: AppColors.accentDark,
                    fontWeight: FontWeight.w700,
                    fontSize: 12,
                    letterSpacing: 0.1,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Iterable<Widget> _buildPromptTiles() sync* {
    for (int i = 0; i < _prompts.length; i++) {
      final p = _prompts[i];
      final view = _promptView(p);
      final isVibe = p.promptType == 'vibe';
      yield TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: Duration(milliseconds: 220 + (i * 40).clamp(0, 200)),
        curve: Curves.easeOutCubic,
        builder: (context, t, child) => Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, (1 - t) * 8),
            child: child,
          ),
        ),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: isVibe
                ? AppColors.accentLight.withValues(alpha: 0.35)
                : AppColors.surface,
            borderRadius: AppRadius.borderLg,
            border: Border.all(
              color: isVibe
                  ? AppColors.accent.withValues(alpha: 0.25)
                  : AppColors.borderLight,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: AppColors.accentLight,
                  borderRadius: AppRadius.borderSm,
                ),
                alignment: Alignment.center,
                child: Icon(
                  _iconForPrompt(p.promptType),
                  size: 17,
                  color: AppColors.accentDark,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      view.header,
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textTertiary,
                        letterSpacing: 0.6,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      view.body,
                      style: TextStyle(
                        fontSize: 14,
                        color: view.dimmed
                            ? AppColors.textTertiary
                            : AppColors.textPrimary,
                        fontWeight: FontWeight.w600,
                        height: 1.4,
                        fontStyle:
                            isVibe ? FontStyle.italic : FontStyle.normal,
                      ),
                    ),
                    if (view.footer != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        view.footer!,
                        style: TextStyle(
                          fontSize: 13,
                          color: AppColors.textSecondary,
                          height: 1.35,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }
  }

  /// Normalises the polymorphic `(label, body)` pair the backend attaches to
  /// each prompt into a `(header, body, footer)` triplet that reads well as a
  /// highlight tile. The mapping mirrors how ``_build_event_card`` in
  /// ``backend/app/domain/event_service.py`` populates each prompt type:
  ///
  ///   * `speaker`      → label = name, body = "title · company"
  ///   * `topic`        → label = "Topic", body = abstract
  ///   * `when_where`   → label = formatted-date, body = location · room
  ///   * `vibe`         → label = "Vibe", body = vibe_text
  ///   * `who_is_going` → label = "Who's going", body = ", ".join(names)
  _PromptTileView _promptView(EventCardPrompt p) {
    final body = (p.body ?? '').trim();
    switch (p.promptType) {
      case 'speaker':
        return _PromptTileView(
          header: 'SPEAKER',
          body: p.label,
          footer: body.isEmpty ? null : body,
        );
      case 'topic':
        return _PromptTileView(
          header: 'TOPIC',
          body: body.isEmpty ? 'No abstract yet.' : body,
          dimmed: body.isEmpty,
        );
      case 'when_where':
        return _PromptTileView(
          header: 'WHEN & WHERE',
          body: p.label,
          footer: body.isEmpty ? null : body,
        );
      case 'vibe':
        return _PromptTileView(
          header: 'VIBE',
          body: body.isEmpty
              ? 'Tap “Refresh vibe” for a Eventive-generated line.'
              : body,
          dimmed: body.isEmpty,
        );
      case 'who_is_going':
        return _PromptTileView(
          header: "WHO'S GOING",
          body: body.isEmpty ? 'No one from your network yet.' : body,
          dimmed: body.isEmpty,
        );
      default:
        return _PromptTileView(
          header: p.label.toUpperCase(),
          body: body.isEmpty ? '—' : body,
          dimmed: body.isEmpty,
        );
    }
  }

  Widget _speakerTile(SpeakerRead speaker) {
    return GestureDetector(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => SpeakerDetailScreen(
            speakerId: speaker.id,
            preloaded: speaker,
          ),
        ),
      ),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: AppRadius.borderLg,
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.accent,
              ),
              alignment: Alignment.center,
              child: Text(
                speaker.name.isNotEmpty
                    ? speaker.name.characters.first.toUpperCase()
                    : '?',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    speaker.name,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (speaker.title != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      speaker.company != null
                          ? '${speaker.title} · ${speaker.company}'
                          : speaker.title!,
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded,
                color: AppColors.textTertiary),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String label) => Text(
        label,
        style: GoogleFonts.plusJakartaSans(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: AppColors.textPrimary,
        ),
      );

  Widget _infoPill(IconData icon, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: AppRadius.borderFull,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.textTertiary),
          const SizedBox(width: 6),
          Text(
            text,
            style: const TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  IconData _iconForPrompt(String type) {
    switch (type) {
      case 'cover':
        return Icons.image_rounded;
      case 'speaker':
        return Icons.mic_rounded;
      case 'topic':
        return Icons.topic_rounded;
      case 'when_where':
        return Icons.schedule_rounded;
      case 'vibe':
        return Icons.auto_awesome;
      case 'who_is_going':
        return Icons.people_rounded;
      default:
        return Icons.info_rounded;
    }
  }
}

/// Small value type describing the three text slots each highlight tile
/// exposes. Kept local because the mapping from backend prompt payload to
/// these fields is tightly coupled to this screen's rendering choices.
class _PromptTileView {
  final String header;
  final String body;
  final String? footer;
  final bool dimmed;

  const _PromptTileView({
    required this.header,
    required this.body,
    this.footer,
    this.dimmed = false,
  });
}

/// Primary CTA — big filled button that owns the "hard commitment" path
/// (RSVP → Going). Sized and coloured to be the single obvious action on
/// the sheet so users never have to weigh three equal-weight chips.
class _PrimaryActionButton extends StatefulWidget {
  final _ActionSpec spec;
  final bool selected;
  final bool busy;
  final VoidCallback onTap;

  const _PrimaryActionButton({
    required this.spec,
    required this.selected,
    required this.busy,
    required this.onTap,
  });

  @override
  State<_PrimaryActionButton> createState() => _PrimaryActionButtonState();
}

class _PrimaryActionButtonState extends State<_PrimaryActionButton>
    with SingleTickerProviderStateMixin {
  bool _pressed = false;
  late final AnimationController _popController;
  late final Animation<double> _pop;

  @override
  void initState() {
    super.initState();
    _popController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 360),
    );
    // Slightly larger pop than the old chip (1.0 → 1.04 → 1.0) — this
    // button owns the "you're going" moment and deserves the flourish.
    _pop = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 1.0, end: 1.04)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 1.04, end: 1.0)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 50,
      ),
    ]).animate(_popController);
  }

  @override
  void didUpdateWidget(covariant _PrimaryActionButton old) {
    super.didUpdateWidget(old);
    if (!old.selected && widget.selected) {
      _popController.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _popController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selected = widget.selected;
    final busy = widget.busy;
    final spec = widget.spec;

    // Idle = filled teal (calling to action). Selected = filled darker
    // teal with a check (confirming). Both are strong on purpose — this
    // is the primary action.
    final bg = selected ? AppColors.accentDark : AppColors.accent;
    const fg = Colors.white;

    return Semantics(
      button: true,
      selected: selected,
      label: selected ? spec.selectedLabel : spec.idleLabel,
      child: Listener(
        onPointerDown: (_) => setState(() => _pressed = true),
        onPointerUp: (_) => setState(() => _pressed = false),
        onPointerCancel: (_) => setState(() => _pressed = false),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: busy ? null : widget.onTap,
          child: AnimatedScale(
            scale: _pressed ? 0.98 : 1.0,
            duration: const Duration(milliseconds: 140),
            curve: Curves.easeOutCubic,
            child: ScaleTransition(
              scale: _pop,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 240),
                curve: Curves.easeOutCubic,
                height: 52,
                width: double.infinity,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: selected
                        ? [AppColors.accentDark, AppColors.accent]
                        : [AppColors.accent, AppColors.accentDark],
                  ),
                  color: bg,
                  borderRadius: AppRadius.borderFull,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.36),
                      blurRadius: 22,
                      offset: const Offset(0, 10),
                    ),
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.18),
                      blurRadius: 6,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Center(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SizedBox(
                        width: 20,
                        height: 20,
                        child: busy
                            ? const CircularProgressIndicator(
                                strokeWidth: 2.4,
                                color: Colors.white,
                              )
                            : AnimatedSwitcher(
                                duration: const Duration(milliseconds: 220),
                                switchInCurve: Curves.easeOutCubic,
                                switchOutCurve: Curves.easeInCubic,
                                transitionBuilder: (child, animation) {
                                  return FadeTransition(
                                    opacity: animation,
                                    child: ScaleTransition(
                                      scale: animation,
                                      child: child,
                                    ),
                                  );
                                },
                                child: Icon(
                                  selected
                                      ? Icons.check_circle_rounded
                                      : spec.icon,
                                  key: ValueKey(
                                      'primary-icon-${spec.type}-$selected'),
                                  size: 20,
                                  color: fg,
                                ),
                              ),
                      ),
                      const SizedBox(width: 10),
                      AnimatedDefaultTextStyle(
                        duration: const Duration(milliseconds: 240),
                        curve: Curves.easeOutCubic,
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: fg,
                          letterSpacing: 0.2,
                        ),
                        child: Text(
                          selected ? spec.selectedLabel : spec.idleLabel,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Secondary action — quiet outlined toggle for the soft-intent side of the
/// hierarchy (Save, and post-event Attended). Same behavioural surface as
/// the primary button (busy state, tap ripple, pop on select) but visually
/// deferential so the user's eye lands on the primary CTA first.
class _SecondaryActionButton extends StatefulWidget {
  final _ActionSpec spec;
  final bool selected;
  final bool busy;
  final VoidCallback onTap;

  const _SecondaryActionButton({
    required this.spec,
    required this.selected,
    required this.busy,
    required this.onTap,
  });

  @override
  State<_SecondaryActionButton> createState() => _SecondaryActionButtonState();
}

class _SecondaryActionButtonState extends State<_SecondaryActionButton>
    with SingleTickerProviderStateMixin {
  bool _pressed = false;
  late final AnimationController _popController;
  late final Animation<double> _pop;

  @override
  void initState() {
    super.initState();
    _popController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
    _pop = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 1.0, end: 1.05)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween(begin: 1.05, end: 1.0)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 50,
      ),
    ]).animate(_popController);
  }

  @override
  void didUpdateWidget(covariant _SecondaryActionButton old) {
    super.didUpdateWidget(old);
    if (!old.selected && widget.selected) {
      _popController.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _popController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selected = widget.selected;
    final busy = widget.busy;
    final spec = widget.spec;

    final bg = selected ? AppColors.accentLight : AppColors.surface;
    final fg = selected ? AppColors.accentDark : AppColors.textSecondary;
    final borderColor =
        selected ? AppColors.accent.withValues(alpha: 0.55) : AppColors.border;

    return Tooltip(
      message: spec.tooltip,
      waitDuration: const Duration(milliseconds: 400),
      child: Semantics(
        button: true,
        selected: selected,
        label: selected ? spec.selectedLabel : spec.idleLabel,
        child: Listener(
          onPointerDown: (_) => setState(() => _pressed = true),
          onPointerUp: (_) => setState(() => _pressed = false),
          onPointerCancel: (_) => setState(() => _pressed = false),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: busy ? null : widget.onTap,
            child: AnimatedScale(
              scale: _pressed ? 0.97 : 1.0,
              duration: const Duration(milliseconds: 120),
              curve: Curves.easeOutCubic,
              child: ScaleTransition(
                scale: _pop,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  height: 44,
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: AppRadius.borderFull,
                    border: Border.all(color: borderColor, width: 1.2),
                  ),
                  child: Center(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        SizedBox(
                          width: 16,
                          height: 16,
                          child: busy
                              ? CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: selected
                                      ? AppColors.accentDark
                                      : AppColors.accent,
                                )
                              : AnimatedSwitcher(
                                  duration: const Duration(milliseconds: 200),
                                  switchInCurve: Curves.easeOutCubic,
                                  switchOutCurve: Curves.easeInCubic,
                                  transitionBuilder: (child, animation) {
                                    return FadeTransition(
                                      opacity: animation,
                                      child: ScaleTransition(
                                        scale: animation,
                                        child: child,
                                      ),
                                    );
                                  },
                                  child: Icon(
                                    selected
                                        ? Icons.check_rounded
                                        : spec.icon,
                                    key: ValueKey(
                                        'secondary-icon-${spec.type}-$selected'),
                                    size: 16,
                                    color: fg,
                                  ),
                                ),
                        ),
                        const SizedBox(width: 8),
                        AnimatedDefaultTextStyle(
                          duration: const Duration(milliseconds: 240),
                          curve: Curves.easeOutCubic,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: fg,
                            letterSpacing: 0.1,
                          ),
                          child: Text(
                            selected ? spec.selectedLabel : spec.idleLabel,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Copy + icons for every interaction chip. Keeping these here means the
/// EventDetailSheet, Profile activity sections, and Event Cards can share a
/// single source of truth for how each interaction is described.
class _ActionSpec {
  final String type;
  final IconData icon;
  final String idleLabel;
  final String selectedLabel;
  final String tooltip;
  final String idleHint;
  final String selectedHint;
  final String confirmedCopy;
  final String removedCopy;

  const _ActionSpec({
    required this.type,
    required this.icon,
    required this.idleLabel,
    required this.selectedLabel,
    required this.tooltip,
    required this.idleHint,
    required this.selectedHint,
    required this.confirmedCopy,
    required this.removedCopy,
  });
}

// Three intents, three tiers of visual weight — matched to distinct
// notification behaviour so users have a real reason to pick one:
//
//   * `rsvp` (Going)   — primary CTA. Two pushes: 30-min heads-up and a
//                        10-min "starting soon" alarm. Hard commitment.
//   * `save` (Save)    — quiet secondary toggle. One soft nudge at
//                        10-min if the user never upgraded to RSVP.
//   * `mark_attended`  — tertiary, only shown after the session starts.
//                        No pushes; feeds Wrapped.
//
// `like`, `add_to_my_day`, and `add_to_calendar` are still valid backend
// types (the store keeps tracking them) but don't get a chip here.
const List<_ActionSpec> _actionSpecs = [
  _ActionSpec(
    type: 'rsvp',
    icon: Icons.event_available_rounded,
    idleLabel: "I'm going",
    selectedLabel: "You're going",
    tooltip:
        "Commit to attending — we'll ping you 30 min and 10 min before it starts.",
    idleHint:
        "Tap 'I'm going' to commit — Eventive will ping you 30 min and again 10 min before it starts.",
    selectedHint:
        "You're locked in. Reminders queued for 30 min and 10 min before start.",
    confirmedCopy: "You're going — reminders queued.",
    removedCopy: 'RSVP removed — reminders cancelled.',
  ),
  _ActionSpec(
    type: 'save',
    icon: Icons.bookmark_add_rounded,
    idleLabel: 'Save',
    selectedLabel: 'Saved',
    tooltip:
        "Bookmark for later. We'll send one gentle nudge 10 min before it starts.",
    idleHint:
        "Not sure yet? Save it — Eventive will nudge you once, 10 min before it starts.",
    selectedHint: "Saved. We'll nudge you 10 min before it starts.",
    confirmedCopy: 'Saved — nudge queued.',
    removedCopy: 'Removed from Saved.',
  ),
  _ActionSpec(
    type: 'mark_attended',
    icon: Icons.check_circle_rounded,
    idleLabel: 'Log attendance',
    selectedLabel: 'Attended',
    tooltip: 'Log that you attended so your Wrapped stays accurate.',
    idleHint: 'Log that you attended to power your Wrapped recap.',
    selectedHint: 'Marked attended — nice one.',
    confirmedCopy: 'Marked as attended.',
    removedCopy: 'Attendance mark removed.',
  ),
];
