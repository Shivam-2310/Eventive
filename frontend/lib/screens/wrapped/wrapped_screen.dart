import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../models/user.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// End-of-event summary — `GET /users/{id}/wrapped`.
class WrappedScreen extends StatefulWidget {
  const WrappedScreen({super.key});

  @override
  State<WrappedScreen> createState() => _WrappedScreenState();
}

class _WrappedScreenState extends State<WrappedScreen> {
  bool _loading = true;
  UserWrapped? _wrapped;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
    }
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loading = true);
    try {
      final w = await services.users.wrapped(userId);
      if (!mounted) return;
      setState(() {
        _wrapped = w;
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
        title: Text('Your Wrapped',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: _load,
        child: _loading
            ? const Center(
                child: CircularProgressIndicator(color: AppColors.accent))
            : _wrapped == null
                ? Center(
                    child: Text('Nothing to see yet.',
                        style: TextStyle(color: AppColors.textTertiary)),
                  )
                : _buildBody(_wrapped!),
      ),
    );
  }

  Widget _buildBody(UserWrapped w) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: AppColors.accentGradient),
            borderRadius: AppRadius.borderXl,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Your Eventive journey',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'A recap of what you got up to.',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.85)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.35,
          children: [
            _statCard('Sessions attended', '${w.sessionsAttended}',
                Icons.event_available_rounded),
            _statCard('Connections made', '${w.connectionsMade}',
                Icons.people_alt_rounded),
            _statCard('Reels posted', '${w.reelsPosted}',
                Icons.play_circle_rounded),
            _statCard('Rooms visited', '${w.uniqueRoomsVisited}',
                Icons.meeting_room_rounded),
            _statCard('Notifications', '${w.notificationsReceived}',
                Icons.notifications_active_rounded),
          ],
        ),
        const SizedBox(height: 20),
        if (w.favoriteSpeaker != null) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: AppRadius.borderLg,
              border: Border.all(color: AppColors.borderLight),
            ),
            child: Row(
              children: [
                Icon(Icons.star_rounded, color: AppColors.accent),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Favorite speaker',
                        style: TextStyle(
                          fontSize: 12,
                          color: AppColors.textTertiary,
                        ),
                      ),
                      Text(
                        w.favoriteSpeaker!,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        if (w.topTopics.isNotEmpty) ...[
          const Text(
            'Top topics',
            style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                color: AppColors.textPrimary),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: w.topTopics
                .map(
                  (t) => Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppColors.accentLight,
                      borderRadius: AppRadius.borderFull,
                    ),
                    child: Text(
                      t,
                      style: TextStyle(
                        color: AppColors.accentDark,
                        fontWeight: FontWeight.w700,
                        fontSize: 13,
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ],
      ],
    );
  }

  Widget _statCard(String label, String value, IconData icon) {
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
