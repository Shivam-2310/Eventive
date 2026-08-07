import 'package:flutter/material.dart';

import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../utils/haptics.dart';

/// A card the user can drag left/right to reject/accept.
///
/// Design notes:
/// - Rotation caps at ~4° during drag — feels like nudging a physical card.
/// - Softly-saturating rotation curve so early motion is responsive and the
///   card can never spin absurdly far even when yanked hard.
/// - Feedback while dragging is a low-opacity tint + a small floating pill
///   (no oversized "LIKE / NOPE" stamp).
/// - Snap-back uses `easeOutBack` for a subtle spring-like return.
/// - Fly-off duration scales with fling velocity so hard flings exit faster.
///
/// Callers keep the same API (`rightSwipeLabel` / `leftSwipeLabel`); the
/// labels are now rendered inside the floating pills instead of large
/// Tinder-style stamps. All swipe callbacks remain unchanged.
class SwipeableCard extends StatefulWidget {
  final Widget child;
  final VoidCallback onSwipeLeft;
  final VoidCallback onSwipeRight;
  final VoidCallback? onTap;

  /// Label shown in the "accept" pill during a right-swipe.
  /// Defaults preserve historical behaviour ("LIKE"); EventiveConnect's event deck
  /// overrides to "SAVE" to match its save-not-like semantics.
  final String rightSwipeLabel;

  /// Label shown in the "reject" pill during a left-swipe.
  final String leftSwipeLabel;

  final IconData rightSwipeIcon;
  final IconData leftSwipeIcon;

  /// Fires continuously while the card is being dragged.
  /// Positive → right-swipe intent, negative → left-swipe intent.
  final ValueChanged<double>? onSwipeProgressChanged;

  const SwipeableCard({
    super.key,
    required this.child,
    required this.onSwipeLeft,
    required this.onSwipeRight,
    this.onTap,
    this.rightSwipeLabel = 'LIKE',
    this.leftSwipeLabel = 'NOPE',
    this.rightSwipeIcon = Icons.check_rounded,
    this.leftSwipeIcon = Icons.close_rounded,
    this.onSwipeProgressChanged,
  });

  @override
  State<SwipeableCard> createState() => _SwipeableCardState();
}

class _SwipeableCardState extends State<SwipeableCard>
    with SingleTickerProviderStateMixin {
  final ValueNotifier<Offset> _position = ValueNotifier(Offset.zero);
  late final AnimationController _controller;
  Animation<Offset>? _offsetAnim;
  bool _hasTriggeredHaptic = false;

  static const double _threshold = 100.0;
  static const double _maxDragRotation = 0.070;
  static const double _maxFlyRotation = 0.105;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this);
    _controller.addListener(_syncFromAnimation);
  }

  @override
  void dispose() {
    _controller.removeListener(_syncFromAnimation);
    _controller.dispose();
    _position.dispose();
    super.dispose();
  }

  void _syncFromAnimation() {
    final anim = _offsetAnim;
    if (anim == null) return;
    _position.value = anim.value;
    widget.onSwipeProgressChanged?.call(_swipeProgress);
  }

  double get _swipeProgress =>
      (_position.value.dx / _threshold).clamp(-1.2, 1.2);

  double _rotationFor(double dx, {double cap = _maxDragRotation}) {
    final t = dx / _threshold;
    final normalized = t / (1 + t.abs() * 0.5);
    return (normalized * cap).clamp(-cap, cap);
  }

  double _scaleFor(double dx) {
    final t = (dx.abs() / _threshold).clamp(0.0, 1.0);
    return 1.0 + t * 0.02;
  }

  void _onPanStart(DragStartDetails _) {
    _controller.stop();
    _offsetAnim = null;
    _hasTriggeredHaptic = false;
  }

  void _onPanUpdate(DragUpdateDetails details) {
    _position.value += details.delta;
    widget.onSwipeProgressChanged?.call(_swipeProgress);
    if (!_hasTriggeredHaptic && _position.value.dx.abs() > _threshold) {
      AppHaptics.light();
      _hasTriggeredHaptic = true;
    }
  }

  void _onPanEnd(DragEndDetails details) {
    final dx = _position.value.dx;
    final vx = details.velocity.pixelsPerSecond.dx;
    final commit = dx.abs() > _threshold || vx.abs() > 800;

    if (commit) {
      _flyOff(dx > 0 || vx > 0, vx);
    } else {
      _snapBack();
    }
  }

  Future<void> _flyOff(bool toRight, double vx) async {
    AppHaptics.medium();

    final width = MediaQuery.sizeOf(context).width;
    final direction = toRight ? 1.0 : -1.0;
    final start = _position.value;
    final projected = (vx * 0.18).clamp(-160.0, 160.0);
    final endX = direction * (width + 120) + projected;
    final end = Offset(endX, start.dy * 0.15);

    final speed = vx.abs().clamp(200.0, 4000.0);
    final durationMs =
        (360 - ((speed - 200) / 3800) * 120).round().clamp(240, 380);

    _controller.duration = Duration(milliseconds: durationMs);
    _offsetAnim = Tween<Offset>(begin: start, end: end).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic),
    );

    await _controller.forward(from: 0);

    if (!mounted) return;
    if (toRight) {
      widget.onSwipeRight();
    } else {
      widget.onSwipeLeft();
    }
    _offsetAnim = null;
    _position.value = Offset.zero;
    widget.onSwipeProgressChanged?.call(0);
  }

  Future<void> _snapBack() async {
    final start = _position.value;
    if (start == Offset.zero) return;

    final travel = start.distance.clamp(0.0, 200.0);
    final durationMs = (280 + (travel / 200) * 100).round();
    _controller.duration = Duration(milliseconds: durationMs);

    _offsetAnim = Tween<Offset>(begin: start, end: Offset.zero).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutBack),
    );

    await _controller.forward(from: 0);
    if (!mounted) return;
    _position.value = Offset.zero;
    widget.onSwipeProgressChanged?.call(0);
    _offsetAnim = null;
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      onTap: widget.onTap,
      behavior: HitTestBehavior.opaque,
      child: ValueListenableBuilder<Offset>(
        valueListenable: _position,
        builder: (context, pos, child) {
          final drag = (pos.dx.abs() / _threshold).clamp(0.0, 1.0);
          final isAnimatingOff = _offsetAnim != null;
          final rot = _rotationFor(
            pos.dx,
            cap: isAnimatingOff ? _maxFlyRotation : _maxDragRotation,
          );
          final scale = _scaleFor(pos.dx);
          final progress = _swipeProgress;

          return Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..translate(pos.dx, pos.dy)
              ..rotateZ(rot)
              ..scale(scale),
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppRadius.xl),
                boxShadow: _dragShadow(drag),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppRadius.xl),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (child != null) child,
                    IgnorePointer(child: _buildTint(progress)),
                    IgnorePointer(child: _buildPills(progress)),
                  ],
                ),
              ),
            ),
          );
        },
        child: widget.child,
      ),
    );
  }

  List<BoxShadow> _dragShadow(double drag) {
    final t = Curves.easeOut.transform(drag);
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: 0.10 + 0.10 * t),
        blurRadius: 20 + 20 * t,
        offset: Offset(0, 8 + 8 * t),
      ),
    ];
  }

  Widget _buildTint(double progress) {
    final isLike = progress >= 0;
    final magnitude = progress.abs().clamp(0.0, 1.0);
    final tint = isLike ? AppColors.like : AppColors.textSecondary;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
      color: tint.withValues(alpha: 0.18 * magnitude),
    );
  }

  Widget _buildPills(double progress) {
    final rightProgress = progress > 0 ? progress.clamp(0.0, 1.0) : 0.0;
    final leftProgress = progress < 0 ? (-progress).clamp(0.0, 1.0) : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Align(
        alignment: Alignment.center,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _SwipePill(
              label: widget.rightSwipeLabel,
              icon: widget.rightSwipeIcon,
              progress: rightProgress,
              variant: _PillVariant.accept,
              rotation: -0.12,
            ),
            _SwipePill(
              label: widget.leftSwipeLabel,
              icon: widget.leftSwipeIcon,
              progress: leftProgress,
              variant: _PillVariant.reject,
              rotation: 0.12,
            ),
          ],
        ),
      ),
    );
  }
}

enum _PillVariant { accept, reject }

class _SwipePill extends StatelessWidget {
  final String label;
  final IconData icon;
  final double progress;
  final _PillVariant variant;
  final double rotation;

  const _SwipePill({
    required this.label,
    required this.icon,
    required this.progress,
    required this.variant,
    required this.rotation,
  });

  @override
  Widget build(BuildContext context) {
    // Slight delay before showing (needs ~10% intent) so the pill doesn't
    // flash on tiny nudges, then eases in with a springy over-scale.
    final gated = ((progress - 0.05) / 0.95).clamp(0.0, 1.0);
    final t = Curves.easeOutCubic.transform(gated);
    // Elastic-ish: over-shoots slightly past 1.0, then settles.
    final scale = 0.55 + t * 0.55;
    // Rotation eases from 2x → 1x of the resting angle for a soft "settle".
    final settleRotation = rotation * (1.7 - t * 0.7);

    final isAccept = variant == _PillVariant.accept;
    final accentColor = isAccept ? AppColors.accent : AppColors.textSecondary;
    final gradient = isAccept
        ? const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: AppColors.accentGradient,
          )
        : const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF64748B), Color(0xFF334155)],
          );

    return IgnorePointer(
      child: Opacity(
        opacity: t,
        child: Transform.rotate(
          angle: settleRotation,
          child: Transform.scale(
            scale: scale,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
              decoration: BoxDecoration(
                gradient: gradient,
                borderRadius: AppRadius.borderFull,
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.55),
                  width: 2,
                ),
                boxShadow: [
                  // Colored glow — sells the "committed" feeling.
                  BoxShadow(
                    color: accentColor.withValues(alpha: 0.45 * t),
                    blurRadius: 28,
                    spreadRadius: 1,
                    offset: const Offset(0, 6),
                  ),
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.18),
                    blurRadius: 14,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, size: 22, color: Colors.white),
                  const SizedBox(width: 8),
                  Text(
                    label,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.2,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
