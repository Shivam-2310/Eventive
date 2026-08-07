import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../models/event.dart';
import '../../models/interest.dart';
import '../../models/mission.dart';
import '../../models/user.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';
import '../../widgets/common/profile_avatar.dart';
import '../admin/admin_screen.dart';
import '../interests/edit_interests_screen.dart';
import '../missions/missions_screen.dart';
import '../notifications/notifications_screen.dart';
import '../auth/sign_in_screen.dart';
import '../wrapped/wrapped_screen.dart';
import 'my_events_screen.dart';

/// Signed-in user's profile — hydrated from `GET /users/{id}` and
/// `GET /users/{id}/interests`, plus a light `GET /missions/me` summary.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _loading = true;
  UserRead? _user;
  List<UserInterestRead> _interests = const [];
  List<MissionProgress> _missions = const [];
  // Server-truth bucket counts (`upcoming_rsvp`, `save`, `mark_attended`, …)
  // — same source `MyEventsScreen` uses, so the chips here and the tab
  // counts on that screen always agree. `store.isActive('rsvp')` would
  // over-count Upcoming because it can't tell past RSVPs from future ones.
  Map<String, int> _bucketCounts = const {};
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
      final results = await Future.wait([
        services.users.get(userId),
        services.users.listInterests(userId),
        services.missions.me(userId),
        // refresh the shared interactions cache so the activity chips on
        // the tile row below are always in sync with the server.
        services.eventInteractions.refresh(userId),
        services.events.userEventBuckets(userId),
      ]);
      if (!mounted) return;
      final user = results[0] as UserRead;
      await services.session.refreshUser(user);
      final buckets = results[4] as Map<String, List<EventRead>>;
      setState(() {
        _user = user;
        _interests = results[1] as List<UserInterestRead>;
        _missions = results[2] as List<MissionProgress>;
        _bucketCounts = {
          for (final entry in buckets.entries) entry.key: entry.value.length,
        };
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  /// Refetches just the activity bucket counts (cheap: one GET). Called on
  /// return from `MyEventsScreen` so if the user un-RSVPed or un-saved from
  /// inside that screen, the chip counts here update immediately.
  Future<void> _refreshBucketCounts() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    try {
      final buckets = await services.events.userEventBuckets(userId);
      if (!mounted) return;
      setState(() {
        _bucketCounts = {
          for (final entry in buckets.entries) entry.key: entry.value.length,
        };
      });
    } catch (_) {
      // Silent — the counts stay at their last known value and the next
      // pull-to-refresh will retry.
    }
  }

  Future<void> _signOut() async {
    final services = ServiceScope.of(context);
    await services.auth.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const SignInScreen()),
      (_) => false,
    );
  }

  int get _completedMissions => _missions.where((m) => m.isCompleted).length;

  int get _totalPoints =>
      _missions.fold<int>(0, (sum, m) => sum + m.pointsAwarded);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              backgroundColor: AppColors.background,
              leading: IconButton(
                icon: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceVariant,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.arrow_back_rounded, size: 20),
                ),
                onPressed: () => Navigator.pop(context),
              ),
              pinned: true,
              expandedHeight: 0,
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                child: _loading
                    ? const Padding(
                        padding: EdgeInsets.symmetric(vertical: 80),
                        child: Center(
                          child:
                              CircularProgressIndicator(color: AppColors.accent),
                        ),
                      )
                    : _buildBody(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    final user = _user;
    if (user == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 60),
        child: Text('User not found.'),
      );
    }
    return Column(
      children: [
        const SizedBox(height: 8),
        ProfileAvatar(size: 100, imageUrl: user.avatarUrl),
        const SizedBox(height: 20),
        Text(
          user.name,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 24,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          user.email,
          style: TextStyle(
            fontSize: 14,
            color: AppColors.textTertiary,
            fontWeight: FontWeight.w400,
          ),
        ),
        if (user.headline != null && user.headline!.isNotEmpty) ...[
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: AppRadius.borderFull,
            ),
            child: Text(
              user.headline!,
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        ],
        const SizedBox(height: 28),
        Container(
          padding: const EdgeInsets.symmetric(vertical: 18),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: AppRadius.borderXl,
            border: Border.all(color: AppColors.borderLight),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _statItem('${_interests.length}', 'Interests'),
              _divider(),
              _statItem('$_completedMissions', 'Missions'),
              _divider(),
              _statItem('$_totalPoints', 'Points'),
            ],
          ),
        ),
        const SizedBox(height: 24),
        _buildActivityCard(),
        const SizedBox(height: 24),
        _buildTile(
          Icons.timeline_rounded,
          'My activity',
          AppColors.accent,
          onTap: () => _openMyEvents(),
        ),
        _buildTile(
          Icons.notifications_none_rounded,
          'Notifications',
          AppColors.accent,
          onTap: () => _push(const NotificationsScreen()),
        ),
        _buildTile(
          Icons.emoji_events_rounded,
          'Missions',
          AppColors.textSecondary,
          onTap: () => _push(const MissionsScreen()),
        ),
        _buildTile(
          Icons.card_giftcard_rounded,
          'My Wrapped',
          AppColors.textSecondary,
          onTap: () => _push(const WrappedScreen()),
        ),
        _buildTile(
          Icons.tune_rounded,
          'Edit Interests',
          AppColors.textSecondary,
          onTap: () async {
            final updated = await Navigator.of(context).push<bool>(
              MaterialPageRoute(builder: (_) => const EditInterestsScreen()),
            );
            if (updated == true) _load();
          },
        ),
        if (ServiceScope.of(context).session.adminMode || user.isAdmin)
          _buildTile(
            Icons.shield_moon_rounded,
            'Admin console',
            AppColors.textSecondary,
            onTap: () => _push(const AdminScreen()),
          ),
        _buildTile(
          Icons.info_outline_rounded,
          'About Eventive',
          AppColors.textSecondary,
          onTap: _showAbout,
        ),
        const SizedBox(height: 8),
        _buildTile(
          Icons.logout_rounded,
          'Sign Out',
          AppColors.error,
          isDestructive: true,
          onTap: _signOut,
        ),
        const SizedBox(height: 40),
      ],
    );
  }

  void _push(Widget screen) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
  }

  Widget _buildActivityCard() {
    // Mirrors the three buckets exposed by `MyEventsScreen`:
    //   Upcoming (upcoming_rsvp)  Saved (save)  Attended (mark_attended)
    // `like` is an implicit taste signal from the swipe deck — users
    // don't manage it, so it doesn't get a chip. `add_to_my_day` and
    // `add_to_calendar` overlap with Save/RSVP and stay off too.
    final entries = <_ActivityEntry>[
      _ActivityEntry(
        bucket: 'upcoming_rsvp',
        label: 'Upcoming',
        icon: Icons.event_available_rounded,
        count: _bucketCounts['upcoming_rsvp'] ?? 0,
      ),
      _ActivityEntry(
        bucket: 'save',
        label: 'Saved',
        icon: Icons.bookmark_rounded,
        count: _bucketCounts['save'] ?? 0,
      ),
      _ActivityEntry(
        bucket: 'mark_attended',
        label: 'Attended',
        icon: Icons.check_circle_rounded,
        count: _bucketCounts['mark_attended'] ?? 0,
      ),
    ];
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderXl,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.timeline_rounded,
                  size: 18, color: AppColors.accentDark),
              const SizedBox(width: 8),
              Text(
                'My activity',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                ),
              ),
              const Spacer(),
              TextButton(
                onPressed: _openMyEvents,
                child: Text(
                  'See all',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: AppColors.accentDark,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Every RSVP, save, and attended session lives here — synced across every screen.',
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textTertiary,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: entries.map((e) => _activityChip(e)).toList(),
          ),
        ],
      ),
    );
  }

  Future<void> _openMyEvents({String? initialBucket}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => MyEventsScreen(
          initialBucket: initialBucket ?? 'upcoming_rsvp',
        ),
      ),
    );
    if (!mounted) return;
    _refreshBucketCounts();
  }

  Widget _activityChip(_ActivityEntry entry) {
    return InkWell(
      borderRadius: AppRadius.borderFull,
      onTap: () => _openMyEvents(initialBucket: entry.bucket),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: entry.count > 0
              ? AppColors.accentLight
              : AppColors.surfaceVariant,
          borderRadius: AppRadius.borderFull,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              entry.icon,
              size: 14,
              color: entry.count > 0
                  ? AppColors.accentDark
                  : AppColors.textSecondary,
            ),
            const SizedBox(width: 6),
            Text(
              entry.label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: entry.count > 0
                    ? AppColors.accentDark
                    : AppColors.textPrimary,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
              decoration: BoxDecoration(
                color: entry.count > 0
                    ? AppColors.accent
                    : AppColors.borderLight,
                borderRadius: AppRadius.borderFull,
              ),
              child: Text(
                '${entry.count}',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  color: entry.count > 0
                      ? Colors.white
                      : AppColors.textTertiary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showAbout() {
    showAboutDialog(
      context: context,
      applicationName: 'Eventive Companion',
      applicationVersion: '0.1.0',
      applicationLegalese:
          'Backend base URL:\n${ServiceScope.of(context).api.baseUrl}',
    );
  }

  Widget _divider() => Container(
        width: 1,
        height: 32,
        color: AppColors.borderLight,
      );

  Widget _statItem(String value, String label) {
    return Column(
      children: [
        Text(
          value,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 20,
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
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildTile(
    IconData icon,
    String title,
    Color iconColor, {
    bool isDestructive = false,
    VoidCallback? onTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 2),
        leading: Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            color: iconColor.withValues(alpha: 0.1),
            borderRadius: AppRadius.borderMd,
          ),
          child: Icon(icon, color: iconColor, size: 20),
        ),
        title: Text(
          title,
          style: TextStyle(
            color: isDestructive ? AppColors.error : AppColors.textPrimary,
            fontWeight: FontWeight.w600,
            fontSize: 15,
          ),
        ),
        trailing: Icon(
          Icons.chevron_right_rounded,
          color: AppColors.textTertiary.withValues(alpha: 0.5),
          size: 20,
        ),
        onTap: onTap,
      ),
    );
  }
}

class _ActivityEntry {
  final String bucket;
  final String label;
  final IconData icon;
  final int count;
  const _ActivityEntry({
    required this.bucket,
    required this.label,
    required this.icon,
    required this.count,
  });
}
