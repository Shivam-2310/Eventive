import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import 'models/notification.dart';
import 'screens/connections/threads_screen.dart';
import 'screens/feels/feels_screen.dart';
import 'screens/eventivebot/eventivebot_screen.dart';
import 'screens/eventiveconnect/eventiveconnect_screen.dart';
import 'screens/notifications/notifications_screen.dart';
import 'screens/profile/profile_screen.dart';
import 'services/services.dart';
import 'services/ws_service.dart';
import 'theme/colors.dart';
import 'widgets/common/profile_avatar.dart';
import 'widgets/navigation/floating_nav_bar.dart';

/// Height of the sticky app header (excluding the OS status-bar / notch).
///
/// Exposed as a top-level constant so every top-level screen (eventivebot,
/// eventiveconnect, feels, …) can pad its own content with
/// `MediaQuery.of(context).padding.top + kAppHeaderHeight` and never
/// collide with the header buttons.
const double kAppHeaderHeight = 58;

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 1;
  int _unreadNotifs = 0;
  ReconnectingWebSocket? _notifWs;
  StreamSubscription<Map<String, dynamic>>? _notifSub;
  bool _hydrated = false;

  final _screens = const [
    FeelsScreen(),
    EventiveConnectScreen(),
    EventiveBotScreen(),
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _bootstrapNotifications();
    }
  }

  @override
  void dispose() {
    _notifSub?.cancel();
    _notifWs?.close();
    super.dispose();
  }

  Future<void> _bootstrapNotifications() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    try {
      final list = await services.notifications.list(userId: userId);
      if (!mounted) return;
      setState(() {
        _unreadNotifs = list.where((n) => !n.isRead).length;
      });
    } catch (_) {}
    final ws = services.ws.notificationsSocket(userId);
    _notifWs = ws;
    _notifSub = ws.frames.listen((frame) {
      if (frame['channel'] != 'notification') return;
      final data = frame['data'];
      if (data is! Map) return;
      final n = NotificationRead.fromJson(Map<String, dynamic>.from(data));
      if (!n.isRead && mounted) {
        setState(() => _unreadNotifs++);
      }
    });
    ws.connect();
  }

  void _onTabChanged(int index) {
    if (index != _currentIndex) {
      HapticFeedback.selectionClick();
      setState(() => _currentIndex = index);
    }
  }

  Future<void> _openProfile() async {
    await Navigator.push(
      context,
      PageRouteBuilder(
        pageBuilder: (_, _, _) => const ProfileScreen(),
        transitionsBuilder: (_, animation, _, child) {
          return SlideTransition(
            position: Tween<Offset>(
              begin: const Offset(0, 0.05),
              end: Offset.zero,
            ).animate(CurvedAnimation(
              parent: animation,
              curve: Curves.easeOut,
            )),
            child: FadeTransition(opacity: animation, child: child),
          );
        },
        transitionDuration: const Duration(milliseconds: 350),
      ),
    );
  }

  Future<void> _openNotifications() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const NotificationsScreen()),
    );
    if (!mounted) return;
    _refreshUnreadCount();
  }

  Future<void> _openThreads() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const ThreadsScreen()),
    );
  }

  Future<void> _refreshUnreadCount() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    try {
      final list = await services.notifications
          .list(userId: userId, unreadOnly: true);
      if (!mounted) return;
      setState(() => _unreadNotifs = list.length);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;
    final user = ServiceScope.of(context).session.user;
    final isFeelsTab = _currentIndex == 0;
    return Scaffold(
      body: Stack(
        children: [
          IndexedStack(
            index: _currentIndex,
            children: _screens,
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: _buildTopBar(
              topPadding,
              user?.avatarUrl,
              isFeelsTab: isFeelsTab,
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: FloatingNavBar(
              currentIndex: _currentIndex,
              onTap: _onTabChanged,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopBar(
    double topPadding,
    String? avatarUrl, {
    required bool isFeelsTab,
  }) {
    // Solid, light-themed header container that acts as a proper app bar on
    // every tab. Previously this was fully transparent, which worked on the
    // EventiveConnect hinge deck but left the buttons floating over (and colliding
    // with) light content on the Ask Eventive chat and the Events list.
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: const Border(
          bottom: BorderSide(color: AppColors.borderLight, width: 1),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      padding: EdgeInsets.only(
        top: topPadding + 10,
        left: 20,
        right: 20,
        bottom: 10,
      ),
      child: Row(
        children: [
          // The Feels (reel/video) tab shows "Waves" as its wordmark;
          // every other tab keeps the plain "eventive" wordmark.
          ShaderMask(
            shaderCallback: (bounds) => const LinearGradient(
              colors: AppColors.accentGradient,
            ).createShader(bounds),
            child: Text(
              isFeelsTab ? 'Waves' : 'eventive',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 26,
                fontWeight: FontWeight.w800,
                color: Colors.white,
                letterSpacing: -1.5,
              ),
            ),
          ),
          const Spacer(),
          // Networking used to live buried inside Profile. Promoted to the
          // top bar as a labelled pill so the primary "who's here / talk to
          // someone" surface is one tap from every screen.
          _networkingPill(_openThreads),
          const SizedBox(width: 8),
          _iconButton(
            icon: Icons.notifications_none_rounded,
            badge: _unreadNotifs,
            onTap: _openNotifications,
          ),
          const SizedBox(width: 8),
          ProfileAvatar(onTap: _openProfile, imageUrl: avatarUrl),
        ],
      ),
    );
  }

  Widget _networkingPill(VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(19),
        child: Container(
          height: 38,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: AppColors.surfaceVariant,
            borderRadius: BorderRadius.circular(19),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.people_alt_rounded,
                size: 17,
                color: AppColors.textPrimary,
              ),
              const SizedBox(width: 6),
              Text(
                'Networking',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                  letterSpacing: -0.1,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _iconButton({
    required IconData icon,
    required VoidCallback onTap,
    int badge = 0,
  }) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            customBorder: const CircleBorder(),
            child: Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.surfaceVariant,
                border: Border.all(color: AppColors.border),
              ),
              child: Icon(
                icon,
                size: 19,
                color: AppColors.textPrimary,
              ),
            ),
          ),
        ),
        if (badge > 0)
          Positioned(
            top: -4,
            right: -4,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              decoration: BoxDecoration(
                color: AppColors.accent,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: AppColors.surface, width: 1.5),
              ),
              constraints:
                  const BoxConstraints(minWidth: 18, minHeight: 18),
              child: Center(
                child: Text(
                  badge > 99 ? '99+' : '$badge',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
