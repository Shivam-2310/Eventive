import 'package:flutter/material.dart';

import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import 'swipeable_card.dart';

class CardStack<T> extends StatelessWidget {
  final List<T> items;
  final Widget Function(T item) cardBuilder;
  final ValueChanged<T> onLike;
  final ValueChanged<T> onDislike;
  final ValueChanged<T>? onTap;
  final Widget? emptyState;

  /// Drag-stamp labels forwarded to [SwipeableCard]. Defaults preserve
  /// the existing behaviour for the People deck (LIKE / NOPE); the
  /// events deck overrides to SAVE / PASS.
  final String rightSwipeLabel;
  final String leftSwipeLabel;

  const CardStack({
    super.key,
    required this.items,
    required this.cardBuilder,
    required this.onLike,
    required this.onDislike,
    this.onTap,
    this.emptyState,
    this.rightSwipeLabel = 'LIKE',
    this.leftSwipeLabel = 'NOPE',
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return emptyState ?? _defaultEmpty(context);
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        for (int i = (items.length.clamp(0, 3)) - 1; i >= 0; i--)
          _buildStackedCard(context, i, items[i], i == 0),
      ],
    );
  }

  Widget _buildStackedCard(BuildContext context, int index, T item, bool isTop) {
    final card = SizedBox.expand(child: cardBuilder(item));
    if (isTop) {
      return SwipeableCard(
        onSwipeRight: () => onLike(item),
        onSwipeLeft: () => onDislike(item),
        onTap: onTap != null ? () => onTap!(item) : null,
        rightSwipeLabel: rightSwipeLabel,
        leftSwipeLabel: leftSwipeLabel,
        child: card,
      );
    }
    final scale = 1.0 - (index * 0.02);
    return Transform.scale(
      scale: scale,
      child: Opacity(
        opacity: 1.0 - (index * 0.3),
        child: card,
      ),
    );
  }

  Widget _defaultEmpty(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.accentLight,
              ),
              child: Icon(Icons.check_rounded,
                  size: 40, color: AppColors.accent),
            ),
            AppSpacing.verticalLg,
            Text(
              'You\'re all caught up!',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            AppSpacing.verticalSm,
            Text(
              'Check back later for more',
              style: TextStyle(fontSize: 14, color: AppColors.textTertiary),
            ),
          ],
        ),
      );
}
