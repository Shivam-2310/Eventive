import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../models/reel.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';

/// One reel in the Feels feed.
///
/// If [item.reel.status == 'ready'] and a signed [videoUrl] is present, the
/// card actually plays the video. Otherwise we show a static gradient with a
/// status badge so processing / failed reels are still legible.
class FeelCard extends StatefulWidget {
  final ReelFeedItem item;
  final String? absoluteVideoUrl;
  final bool isActive;
  final VoidCallback? onLike;
  final VoidCallback? onShare;
  final VoidCallback? onDelete;
  final bool likedOptimistic;

  const FeelCard({
    super.key,
    required this.item,
    this.absoluteVideoUrl,
    this.isActive = false,
    this.onLike,
    this.onShare,
    this.onDelete,
    this.likedOptimistic = false,
  });

  @override
  State<FeelCard> createState() => _FeelCardState();
}

class _FeelCardState extends State<FeelCard> {
  VideoPlayerController? _controller;
  bool _initFailed = false;

  @override
  void initState() {
    super.initState();
    _maybeInitVideo();
  }

  @override
  void didUpdateWidget(covariant FeelCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.absoluteVideoUrl != widget.absoluteVideoUrl) {
      _disposeVideo();
      _maybeInitVideo();
    } else if (oldWidget.isActive != widget.isActive && _controller != null) {
      if (widget.isActive) {
        _controller!.play();
      } else {
        _controller!.pause();
      }
    }
  }

  Future<void> _maybeInitVideo() async {
    final url = widget.absoluteVideoUrl;
    if (url == null || !widget.item.reel.isReady) return;
    try {
      final c = VideoPlayerController.networkUrl(Uri.parse(url));
      _controller = c;
      await c.initialize();
      if (!mounted) {
        c.dispose();
        return;
      }
      c.setLooping(true);
      if (widget.isActive) c.play();
      setState(() {});
    } catch (_) {
      if (!mounted) return;
      setState(() => _initFailed = true);
    }
  }

  void _disposeVideo() {
    final c = _controller;
    _controller = null;
    c?.dispose();
  }

  @override
  void dispose() {
    _disposeVideo();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          _buildBackground(),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  stops: const [0.4, 1.0],
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.6),
                  ],
                ),
              ),
            ),
          ),
          if (!widget.item.reel.isReady)
            Positioned(
              top: 120,
              left: 0,
              right: 0,
              child: Center(child: _statusChip()),
            ),
          Positioned(
            right: 16,
            bottom: 180,
            child: Column(
              children: [
                _GlassAction(
                  icon: widget.likedOptimistic
                      ? Icons.favorite_rounded
                      : Icons.favorite_outline_rounded,
                  label: '${widget.item.likes + (widget.likedOptimistic ? 1 : 0)}',
                  active: widget.likedOptimistic,
                  onTap: widget.onLike,
                ),
                const SizedBox(height: 20),
                _GlassAction(
                  icon: Icons.share_rounded,
                  label: 'Share',
                  onTap: widget.onShare,
                ),
                if (widget.onDelete != null) ...[
                  const SizedBox(height: 20),
                  _GlassAction(
                    icon: Icons.delete_outline_rounded,
                    label: 'Delete',
                    onTap: widget.onDelete,
                  ),
                ],
              ],
            ),
          ),
          Positioned(
            left: 16,
            right: 80,
            bottom: 110,
            child: ClipRRect(
              borderRadius: AppRadius.borderLg,
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.12),
                    borderRadius: AppRadius.borderLg,
                    border: Border.all(
                        color: Colors.white.withValues(alpha: 0.15)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.item.reel.caption?.isNotEmpty == true
                            ? widget.item.reel.caption!
                            : 'A moment from Flo',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          height: 1.35,
                        ),
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                      if (widget.item.reel.transcript != null &&
                          widget.item.reel.transcript!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          widget.item.reel.transcript!,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.7),
                            fontSize: 11,
                            fontStyle: FontStyle.italic,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBackground() {
    if (_controller?.value.isInitialized == true) {
      return FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(
          width: _controller!.value.size.width,
          height: _controller!.value.size.height,
          child: VideoPlayer(_controller!),
        ),
      );
    }
    // Fallback: gradient with the reel id imprinted for a distinct look.
    final seed = widget.item.reel.id;
    final palette = [
      [0xFF14B8A6, 0xFF06B6D4],
      [0xFF7C3AED, 0xFFA78BFA],
      [0xFF059669, 0xFF34D399],
      [0xFF2563EB, 0xFF60A5FA],
      [0xFFDB2777, 0xFFF472B6],
    ];
    final colors = palette[seed.abs() % palette.length];
    final w = Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors.map((c) => Color(c)).toList(),
        ),
      ),
      alignment: Alignment.center,
      child: Icon(
        _initFailed ? Icons.error_outline_rounded : Icons.play_circle_rounded,
        size: 72,
        color: Colors.white.withValues(alpha: 0.85),
      ),
    );
    return w;
  }

  Widget _statusChip() {
    final reel = widget.item.reel;
    final label = reel.isFailed
        ? 'Failed'
        : reel.isProcessing
            ? 'Processing…'
            : reel.status;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: reel.isFailed ? AppColors.error : Colors.black54,
        borderRadius: AppRadius.borderFull,
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
          fontSize: 12,
        ),
      ),
    );
  }
}

class _GlassAction extends StatefulWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final bool active;

  const _GlassAction({
    required this.icon,
    required this.label,
    this.onTap,
    this.active = false,
  });

  @override
  State<_GlassAction> createState() => _GlassActionState();
}

class _GlassActionState extends State<_GlassAction> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap?.call();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.9 : 1.0,
        duration: const Duration(milliseconds: 100),
        child: Column(
          children: [
            ClipOval(
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                child: Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: widget.active
                        ? AppColors.accent.withValues(alpha: 0.35)
                        : Colors.white.withValues(alpha: 0.15),
                    border: Border.all(
                        color: Colors.white.withValues(alpha: 0.2)),
                  ),
                  child: Icon(widget.icon, color: Colors.white, size: 22),
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              widget.label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.9),
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
