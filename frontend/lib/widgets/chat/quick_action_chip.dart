import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';

class QuickActionChip extends StatefulWidget {
  final String label;
  final VoidCallback onTap;

  const QuickActionChip({
    super.key,
    required this.label,
    required this.onTap,
  });

  @override
  State<QuickActionChip> createState() => _QuickActionChipState();
}

class _QuickActionChipState extends State<QuickActionChip> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: _pressed ? 0.95 : 1.0,
        duration: const Duration(milliseconds: 100),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.accentLight,
            borderRadius: AppRadius.borderFull,
            border: Border.all(
              color: AppColors.accent.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: Text(
            widget.label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: AppColors.accentDark,
              letterSpacing: -0.1,
            ),
          ),
        ),
      ),
    );
  }
}
