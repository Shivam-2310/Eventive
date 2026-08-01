import 'package:flutter/material.dart';

import '../../app_shell.dart' show kAppHeaderHeight;
import '../../models/reel.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../utils/haptics.dart';
import '../../utils/ui_errors.dart';
import '../../widgets/cards/feel_card.dart';
import 'create_feel_sheet.dart';

class FeelsScreen extends StatefulWidget {
  const FeelsScreen({super.key});

  @override
  State<FeelsScreen> createState() => _FeelsScreenState();
}

class _FeelsScreenState extends State<FeelsScreen> {
  final _pageController = PageController();
  final List<ReelFeedItem> _feed = [];
  final Set<int> _optimisticallyLiked = <int>{};

  int _activeIndex = 0;
  bool _loading = false;
  bool _error = false;
  bool _exhausted = false;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _loadMore(reset: true);
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _loadMore({bool reset = false}) async {
    if (_loading) return;
    if (_exhausted && !reset) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() {
      _loading = true;
      _error = false;
      if (reset) {
        _feed.clear();
        _exhausted = false;
      }
    });
    final cursor = _feed.isNotEmpty ? _feed.last.reel.id : null;
    try {
      final items = await services.reels.feed(
        userId: userId,
        cursor: reset ? null : cursor,
        limit: 20,
      );
      if (!mounted) return;
      setState(() {
        _feed.addAll(items);
        _loading = false;
        if (items.isEmpty) _exhausted = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = true;
      });
      showErrorSnack(context, e);
    }
  }

  Future<void> _like(ReelFeedItem item) async {
    AppHaptics.light();
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    final alreadyOpt = _optimisticallyLiked.contains(item.reel.id);
    setState(() {
      if (alreadyOpt) {
        _optimisticallyLiked.remove(item.reel.id);
      } else {
        _optimisticallyLiked.add(item.reel.id);
      }
    });
    try {
      await services.reels.interaction(
        item.reel.id,
        userId: userId,
        type: 'like',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (alreadyOpt) {
          _optimisticallyLiked.add(item.reel.id);
        } else {
          _optimisticallyLiked.remove(item.reel.id);
        }
      });
      showErrorSnack(context, e);
    }
  }

  Future<void> _share(ReelFeedItem item) async {
    AppHaptics.selection();
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId != null) {
      try {
        await services.reels.interaction(
          item.reel.id,
          userId: userId,
          type: 'share',
        );
      } catch (_) {}
    }
    if (!mounted) return;
    showInfoSnack(context, 'Link copied!');
  }

  Future<void> _delete(ReelFeedItem item) async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    if (item.reel.userId != userId) return;
    try {
      await services.reels.delete(item.reel.id, userId: userId);
      if (!mounted) return;
      setState(() => _feed.remove(item));
      showInfoSnack(context, 'Reel deleted');
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    }
  }

  void _onPageChanged(int index) {
    setState(() => _activeIndex = index);
    if (index == _feed.length - 3 && !_exhausted) {
      _loadMore();
    }
    // record a view interaction
    final userId = ServiceScope.of(context).session.userId;
    if (userId != null && index < _feed.length) {
      final reel = _feed[index].reel;
      ServiceScope.of(context)
          .reels
          .interaction(reel.id, userId: userId, type: 'view')
          .catchError((_) => <String, dynamic>{});
    }
  }

  Future<void> _openCreateSheet() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const CreateFeelSheet(),
    );
    if (created == true) _loadMore(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (_loading && _feed.isEmpty) {
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: const CircularProgressIndicator(color: AppColors.accent),
      );
    }
    if (_error && _feed.isEmpty) {
      return _feedError(onRetry: () => _loadMore(reset: true));
    }
    if (_feed.isEmpty) {
      return _emptyFeed(onCreate: _openCreateSheet);
    }
    return Stack(
      children: [
        PageView.builder(
          controller: _pageController,
          scrollDirection: Axis.vertical,
          itemCount: _feed.length,
          onPageChanged: _onPageChanged,
          itemBuilder: (context, index) {
            final item = _feed[index];
            final absolute = item.reel.videoUrl == null
                ? null
                : services.reels.absoluteMediaUrl(item.reel.videoUrl!);
            return FeelCard(
              item: item,
              absoluteVideoUrl: absolute,
              isActive: index == _activeIndex,
              likedOptimistic: _optimisticallyLiked.contains(item.reel.id),
              onLike: () => _like(item),
              onShare: () => _share(item),
              onDelete: item.reel.userId == userId ? () => _delete(item) : null,
            );
          },
        ),
        Positioned(
          right: AppSpacing.md,
          top: MediaQuery.of(context).padding.top + kAppHeaderHeight + 12,
          child: GestureDetector(
            onTap: _openCreateSheet,
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppColors.accent,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: AppColors.accent.withValues(alpha: 0.3),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: const Icon(
                Icons.add_rounded,
                color: Colors.white,
                size: 24,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _feedError({required VoidCallback onRetry}) {
    return Container(
      color: Colors.black,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off_rounded,
              size: 42, color: Colors.white54),
          const SizedBox(height: 12),
          const Text(
            "Couldn't load Feels.",
            style: TextStyle(color: Colors.white70, fontSize: 15),
          ),
          const SizedBox(height: 16),
          ElevatedButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }

  Widget _emptyFeed({required VoidCallback onCreate}) {
    return Container(
      color: Colors.black,
      alignment: Alignment.center,
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.movie_creation_outlined,
              size: 42, color: Colors.white54),
          const SizedBox(height: 12),
          const Text(
            'No Feels yet.',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Be the first to post one!',
            style: TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: onCreate,
            child: const Text('Create a Feel'),
          ),
        ],
      ),
    );
  }
}
