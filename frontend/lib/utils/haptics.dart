import 'package:flutter/services.dart';

class AppHaptics {
  AppHaptics._();

  static void light() => HapticFeedback.lightImpact();
  static void medium() => HapticFeedback.mediumImpact();
  static void selection() => HapticFeedback.selectionClick();
  static void heavy() => HapticFeedback.heavyImpact();
}
