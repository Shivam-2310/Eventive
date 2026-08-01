import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../models/event.dart';
import '../../models/speaker.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// Speaker detail screen — `GET /speakers/{id}` plus `GET /events?speaker_id=…`.
class SpeakerDetailScreen extends StatefulWidget {
  final int speakerId;
  final SpeakerRead? preloaded;

  const SpeakerDetailScreen({
    super.key,
    required this.speakerId,
    this.preloaded,
  });

  @override
  State<SpeakerDetailScreen> createState() => _SpeakerDetailScreenState();
}

class _SpeakerDetailScreenState extends State<SpeakerDetailScreen> {
  bool _loading = true;
  SpeakerRead? _speaker;
  List<EventRead> _events = const [];
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _speaker = widget.preloaded;
      _load();
    }
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        services.speakers.get(widget.speakerId),
        services.events.list(speakerId: widget.speakerId),
      ]);
      if (!mounted) return;
      setState(() {
        _speaker = results[0] as SpeakerRead;
        _events = results[1] as List<EventRead>;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(_speaker?.name ?? 'Speaker',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 17,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: _loading && _speaker == null
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent))
          : ListView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              children: [
                Center(
                  child: Container(
                    width: 110,
                    height: 110,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: const LinearGradient(
                          colors: AppColors.accentGradient),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      _initials(_speaker?.name ?? ''),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 40,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Center(
                  child: Text(
                    _speaker?.name ?? '',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
                if (_speaker?.title != null || _speaker?.company != null) ...[
                  const SizedBox(height: 6),
                  Center(
                    child: Text(
                      [_speaker?.title, _speaker?.company]
                          .whereType<String>()
                          .where((s) => s.isNotEmpty)
                          .join(' · '),
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  ),
                ],
                if (_speaker?.bio != null && _speaker!.bio!.isNotEmpty) ...[
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: AppRadius.borderLg,
                      border: Border.all(color: AppColors.borderLight),
                    ),
                    child: Text(
                      _speaker!.bio!,
                      style: const TextStyle(
                        fontSize: 14,
                        color: AppColors.textSecondary,
                        height: 1.6,
                      ),
                    ),
                  ),
                ],
                if (_speaker?.socialLinksMap.isNotEmpty ?? false) ...[
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _speaker!.socialLinksMap.entries
                        .map(
                          (e) => Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceVariant,
                              borderRadius: AppRadius.borderFull,
                            ),
                            child: Text(
                              '${e.key} · ${e.value}',
                              style: TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 12,
                              ),
                            ),
                          ),
                        )
                        .toList(),
                  ),
                ],
                const SizedBox(height: 24),
                Text(
                  'Sessions',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 10),
                if (_events.isEmpty)
                  Text('No sessions yet.',
                      style: TextStyle(color: AppColors.textTertiary))
                else
                  ..._events.map(_eventTile),
              ],
            ),
    );
  }

  Widget _eventTile(EventRead e) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.accentLight,
              borderRadius: AppRadius.borderMd,
            ),
            child: Icon(Icons.event_rounded, color: AppColors.accentDark),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  e.title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                Text(
                  e.locationSummary,
                  style: TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Text(
            e.status,
            style: TextStyle(
              color: AppColors.accent,
              fontWeight: FontWeight.w700,
              fontSize: 12,
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
