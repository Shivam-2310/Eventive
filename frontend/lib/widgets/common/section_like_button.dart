import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../utils/haptics.dart';

class SectionLikeButton extends StatefulWidget {
  const SectionLikeButton({super.key});

  @override
  State<SectionLikeButton> createState() => _SectionLikeButtonState();
}

class _SectionLikeButtonState extends State<SectionLikeButton>
    with SingleTickerProviderStateMixin {
  bool _liked = false;
  late final AnimationController _controller;
  late final Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _scaleAnimation = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 1.0, end: 1.3), weight: 50),
      TweenSequenceItem(tween: Tween(begin: 1.3, end: 1.0), weight: 50),
    ]).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOut));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _toggle() {
    AppHaptics.light();
    setState(() => _liked = !_liked);
    if (_liked) {
      _controller.forward(from: 0);
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _toggle,
      child: ScaleTransition(
        scale: _scaleAnimation,
        child: Icon(
          _liked ? Icons.favorite_rounded : Icons.favorite_outline_rounded,
          color: _liked ? AppColors.accent : AppColors.textTertiary,
          size: 22,
        ),
      ),
    );
  }
}
