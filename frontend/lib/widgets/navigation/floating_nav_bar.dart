import 'dart:ui';
import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';

class FloatingNavBar extends StatelessWidget {
  final int currentIndex;
  final ValueChanged<int> onTap;

  const FloatingNavBar({
    super.key,
    required this.currentIndex,
    required this.onTap,
  });

  static const _items = [
    _NavItem(icon: Icons.play_circle_outline_rounded, activeIcon: Icons.play_circle_rounded, label: 'Feels'),
    _NavItem(icon: Icons.people_outline_rounded, activeIcon: Icons.people_rounded, label: 'EventiveConnect'),
    _NavItem(icon: Icons.auto_awesome_outlined, activeIcon: Icons.auto_awesome, label: 'Eventive Bot'),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(40, 0, 40, 28),
      child: ClipRRect(
        borderRadius: AppRadius.borderFull,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
          child: Container(
            height: 60,
            decoration: BoxDecoration(
              color: AppColors.navBarBg,
              borderRadius: AppRadius.borderFull,
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.8),
                width: 0.5,
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.accent.withValues(alpha: 0.08),
                  blurRadius: 30,
                  spreadRadius: 0,
                  offset: const Offset(0, 8),
                ),
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 20,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: List.generate(_items.length, (i) {
                return _NavBarButton(
                  item: _items[i],
                  isActive: i == currentIndex,
                  onTap: () => onTap(i),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;

  const _NavItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
  });
}

class _NavBarButton extends StatefulWidget {
  final _NavItem item;
  final bool isActive;
  final VoidCallback onTap;

  const _NavBarButton({
    required this.item,
    required this.isActive,
    required this.onTap,
  });

  @override
  State<_NavBarButton> createState() => _NavBarButtonState();
}

class _NavBarButtonState extends State<_NavBarButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scaleAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 150),
    );
    _scaleAnim = Tween<double>(begin: 1.0, end: 0.85).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => _controller.forward(),
      onTapUp: (_) {
        _controller.reverse();
        widget.onTap();
      },
      onTapCancel: () => _controller.reverse(),
      behavior: HitTestBehavior.opaque,
      child: ScaleTransition(
        scale: _scaleAnim,
        child: SizedBox(
          width: 64,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Icon with glow
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeOut,
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: widget.isActive
                      ? AppColors.accent.withValues(alpha: 0.12)
                      : Colors.transparent,
                ),
                child: Icon(
                  widget.isActive ? widget.item.activeIcon : widget.item.icon,
                  size: 22,
                  color: widget.isActive
                      ? AppColors.accent
                      : AppColors.textTertiary,
                ),
              ),
              const SizedBox(height: 2),
              // Dot indicator instead of text
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeOut,
                width: widget.isActive ? 4 : 0,
                height: widget.isActive ? 4 : 0,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.accent,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
