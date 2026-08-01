import 'package:flutter/material.dart';
import '../../theme/colors.dart';

class ProfileAvatar extends StatefulWidget {
  final double size;
  final VoidCallback? onTap;
  final String? imageUrl;
  final String heroTag;

  const ProfileAvatar({
    super.key,
    this.size = 36,
    this.onTap,
    this.imageUrl,
    this.heroTag = 'profile-avatar',
  });

  @override
  State<ProfileAvatar> createState() => _ProfileAvatarState();
}

class _ProfileAvatarState extends State<ProfileAvatar> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return Hero(
      tag: widget.heroTag,
      child: GestureDetector(
        onTapDown: (_) => setState(() => _pressed = true),
        onTapUp: (_) {
          setState(() => _pressed = false);
          widget.onTap?.call();
        },
        onTapCancel: () => setState(() => _pressed = false),
        child: AnimatedScale(
          scale: _pressed ? 0.9 : 1.0,
          duration: const Duration(milliseconds: 100),
          child: Container(
            width: widget.size,
            height: widget.size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const LinearGradient(
                colors: AppColors.accentGradient,
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.accent.withValues(alpha: 0.25),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            padding: const EdgeInsets.all(2),
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.background,
              ),
              padding: const EdgeInsets.all(1.5),
              child: ClipOval(
                child: widget.imageUrl != null
                    ? Image.network(
                        widget.imageUrl!,
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) => _placeholder,
                      )
                    : _placeholder,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget get _placeholder => Container(
        color: AppColors.accentLight,
        child: Center(
          child: Icon(
            Icons.person_rounded,
            size: widget.size * 0.45,
            color: AppColors.accentDark,
          ),
        ),
      );
}
