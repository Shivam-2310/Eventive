import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/pulse.dart';
import '../../services/services.dart';
import '../../services/ws_service.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// Live admin dashboard — snapshot on connect, plus a `/ws/admin/pulse` feed
/// that pushes a fresh snapshot every ~5s.
class PulseScreen extends StatefulWidget {
  const PulseScreen({super.key});

  @override
  State<PulseScreen> createState() => _PulseScreenState();
}

class _PulseScreenState extends State<PulseScreen> {
  PulseSnapshot? _snap;
  ReconnectingWebSocket? _ws;
  StreamSubscription<Map<String, dynamic>>? _wsSub;
  bool _loading = true;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _bootstrap();
    }
  }

  Future<void> _bootstrap() async {
    final services = ServiceScope.of(context);
    try {
      final snap = await services.pulse.snapshot();
      if (!mounted) return;
      setState(() {
        _snap = snap;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
    final ws = services.ws.pulseSocket();
    _ws = ws;
    _wsSub = ws.frames.listen(_onWsFrame);
    ws.connect();
  }

  void _onWsFrame(Map<String, dynamic> frame) {
    if (frame['channel'] != 'pulse') return;
    final data = frame['data'];
    if (data is! Map) return;
    if (!mounted) return;
    setState(() {
      _snap = PulseSnapshot.fromJson(Map<String, dynamic>.from(data));
    });
  }

  @override
  void dispose() {
    _wsSub?.cancel();
    _ws?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Live pulse',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: _loading || _snap == null
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent))
          : _buildBody(_snap!),
    );
  }

  Widget _buildBody(PulseSnapshot s) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.accent,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              'Live · updated ${DateFormat('h:mm:ss a').format(s.generatedAt.toLocal())}',
              style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
            ),
          ],
        ),
        const SizedBox(height: 14),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.35,
          children: [
            _metric('Users', '${s.totalUsers}', Icons.people_alt_rounded),
            _metric('Connections', '${s.totalAcceptedConnections}',
                Icons.link_rounded),
            _metric('Likes today', '${s.likesToday}',
                Icons.favorite_rounded),
            _metric('Reel likes today', '${s.reelLikesToday}',
                Icons.movie_creation_rounded),
            _metric('DM threads (24h)', '${s.activeDmThreadsLast24h}',
                Icons.chat_rounded),
            _metric('Avg interactions/event',
                s.avgInteractionsPerEvent.toStringAsFixed(2),
                Icons.trending_up_rounded),
          ],
        ),
        const SizedBox(height: 20),
        const Text(
          'Trending events',
          style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary),
        ),
        const SizedBox(height: 10),
        if (s.trendingEvents.isEmpty)
          Text(
            'No trending events yet.',
            style: TextStyle(color: AppColors.textTertiary),
          )
        else
          ...s.trendingEvents.map(
            (t) => Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.borderLg,
                border: Border.all(color: AppColors.borderLight),
              ),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.accentLight,
                      borderRadius: AppRadius.borderSm,
                    ),
                    child: Text('#${t.eventId}',
                        style: TextStyle(
                            color: AppColors.accentDark,
                            fontSize: 11,
                            fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      t.title,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ),
                  Text(
                    '${t.interactions}',
                    style: TextStyle(
                      color: AppColors.accent,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Icon(Icons.trending_up_rounded,
                      color: AppColors.accent, size: 16),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _metric(String label, String value, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.accent),
          const Spacer(),
          Text(
            value,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ),
    );
  }
}
