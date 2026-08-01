import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/connection.dart';
import '../../models/thread.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';
import 'chat_screen.dart';
import 'connections_screen.dart';

/// Shows two lists side by side (tabbed): current DM threads and the
/// pending / accepted / declined connections graph.
///
/// [initialTab] lets deep-linked notifications open the correct tab
/// straight away — 0 = Threads, 1 = Connections. Anything out of range
/// falls back to 0.
class ThreadsScreen extends StatefulWidget {
  final int initialTab;

  const ThreadsScreen({super.key, this.initialTab = 0});

  @override
  State<ThreadsScreen> createState() => _ThreadsScreenState();
}

class _ThreadsScreenState extends State<ThreadsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  bool _hydrated = false;

  List<ThreadRead> _threads = const [];
  List<ConnectionRead> _connections = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    final startIdx = widget.initialTab.clamp(0, 1);
    _tabController =
        TabController(length: 2, vsync: this, initialIndex: startIdx);
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
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loading = true);
    try {
      final r = await Future.wait([
        services.chat.listThreads(userId),
        services.chat.listConnections(userId),
      ]);
      if (!mounted) return;
      setState(() {
        _threads = r[0] as List<ThreadRead>;
        _connections = r[1] as List<ConnectionRead>;
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
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          title: Text('Networking',
              style: GoogleFonts.plusJakartaSans(
                fontSize: 18,
                fontWeight: FontWeight.w800,
                color: AppColors.textPrimary,
              )),
          backgroundColor: AppColors.background,
          bottom: TabBar(
            controller: _tabController,
            labelColor: AppColors.accent,
            unselectedLabelColor: AppColors.textTertiary,
            indicatorColor: AppColors.accent,
            labelStyle: const TextStyle(fontWeight: FontWeight.w700),
            tabs: const [
              Tab(text: 'Threads'),
              Tab(text: 'Connections'),
            ],
          ),
        ),
        body: TabBarView(
          controller: _tabController,
          children: [
            RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _load,
              child: _threadsList(),
            ),
            RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _load,
              child: ConnectionsScreen(
                connections: _connections,
                loading: _loading,
                onChanged: _load,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _threadsList() {
    if (_loading && _threads.isEmpty) {
      return const Center(
          child: CircularProgressIndicator(color: AppColors.accent));
    }
    if (_threads.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 80),
          Center(
            child: Icon(Icons.chat_bubble_outline_rounded,
                size: 42, color: AppColors.textTertiary),
          ),
          const SizedBox(height: 12),
          Center(
            child: Text(
              'No threads yet.',
              style: TextStyle(fontSize: 15, color: AppColors.textSecondary),
            ),
          ),
          const SizedBox(height: 6),
          Center(
            child: Text(
              'Accept a connection to start chatting.',
              style: TextStyle(color: AppColors.textTertiary),
            ),
          ),
        ],
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: 8),
      itemCount: _threads.length,
      itemBuilder: (_, i) => _threadTile(_threads[i]),
    );
  }

  Widget _threadTile(ThreadRead t) {
    final createdAgo = DateFormat('MMM d · h:mm a').format(t.createdAt.toLocal());
    final selfName = ServiceScope.of(context).session.user?.name;
    final displayTitle = _displayTitle(t, selfName);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: AppColors.accentGradient),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.chat_bubble_rounded, color: Colors.white, size: 18),
        ),
        title: Text(
          displayTitle,
          style: const TextStyle(
              fontWeight: FontWeight.w700, color: AppColors.textPrimary),
        ),
        subtitle: Text(
          createdAgo,
          style: TextStyle(fontSize: 12, color: AppColors.textTertiary),
        ),
        trailing: const Icon(Icons.chevron_right_rounded,
            color: AppColors.textTertiary),
        onTap: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => ChatScreen(thread: t)),
          );
          _load();
        },
      ),
    );
  }

  /// Backend serialises DM threads as `"Alice · Bob"`. In the current
  /// user's inbox we only want to see the counterparty — hearing your own
  /// name back is noise. Split on the ` · ` separator, drop anything that
  /// matches the signed-in user's display name, and rejoin. Falls back to
  /// the raw title if we can't confidently strip.
  String _displayTitle(ThreadRead t, String? selfName) {
    final raw = (t.title ?? '').trim();
    if (raw.isEmpty) return 'Thread #${t.id}';
    if (selfName == null || selfName.trim().isEmpty) return raw;
    final self = selfName.trim().toLowerCase();
    final parts = raw
        .split(' · ')
        .map((p) => p.trim())
        .where((p) => p.isNotEmpty && p.toLowerCase() != self)
        .toList();
    if (parts.isEmpty) return raw;
    return parts.join(' · ');
  }
}
