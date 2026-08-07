import 'package:flutter/material.dart';

import '../../../models/recommendation.dart';
import '../../../theme/colors.dart';
import '../../../theme/radius.dart';

class PersonCardWidget extends StatelessWidget {
  final PersonRecommendation person;

  const PersonCardWidget({super.key, required this.person});

  @override
  Widget build(BuildContext context) {
    // The middle stop of the accent gradient used to be 70% alpha, which
    // made the top card partially transparent in the mid-band. Because the
    // deck renders the next 1-2 upcoming cards behind the active one, that
    // translucency let the next person's name/headline ghost through the
    // active card. We now paint an opaque black base first and layer the
    // gradient (with the same colors) on top, guaranteeing the card is
    // fully opaque regardless of the gradient's alpha values.
    return Container(
      color: Colors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    AppColors.accent,
                    AppColors.accent.withValues(alpha: 0.7),
                    const Color(0xFF0EA5E9),
                  ],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  stops: const [0.15, 0.45, 1.0],
                  colors: [
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.25),
                    Colors.black.withValues(alpha: 0.88),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            top: 130,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: 130,
                height: 130,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: 0.15),
                  border: Border.all(
                      color: Colors.white.withValues(alpha: 0.3), width: 2),
                ),
                child: Text(
                  _initials(person.name),
                  style: const TextStyle(
                    fontSize: 44,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    letterSpacing: -1,
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            top: 110,
            right: 16,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: AppRadius.borderFull,
                border:
                    Border.all(color: Colors.white.withValues(alpha: 0.3)),
              ),
              child: Text(
                'Score ${person.score.toStringAsFixed(2)}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          Positioned(
            left: 20,
            right: 20,
            bottom: 100,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  person.name,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    letterSpacing: -0.5,
                    height: 1.15,
                  ),
                ),
                if (person.headline != null &&
                    person.headline!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    person.headline!,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: Colors.white.withValues(alpha: 0.85),
                    ),
                  ),
                ],
                if (person.reasons.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  ...person.reasons.take(2).map(
                        (r) => Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Icon(Icons.check_circle_rounded,
                                  color: Colors.white, size: 14),
                              const SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  r,
                                  style: TextStyle(
                                    fontSize: 13,
                                    color: Colors.white.withValues(alpha: 0.9),
                                    height: 1.35,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first.characters.first.toUpperCase();
    return (parts.first.characters.first + parts.last.characters.first).toUpperCase();
  }
}
