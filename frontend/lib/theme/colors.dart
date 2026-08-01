import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  // Primary teal gradient
  static const accent = Color(0xFF14B8A6);
  static const accentLight = Color(0xFFCCFBF1);
  static const accentDark = Color(0xFF0F766E);
  static const accentGradient = [Color(0xFF14B8A6), Color(0xFF06B6D4)];

  // Surfaces — layered depth
  static const background = Color(0xFFF8FAFC);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceElevated = Color(0xFFFFFFFF);
  static const surfaceVariant = Color(0xFFF1F5F9);
  static const surfaceMuted = Color(0xFFE2E8F0);

  // Text — slate palette for warmth
  static const textPrimary = Color(0xFF0F172A);
  static const textSecondary = Color(0xFF475569);
  static const textTertiary = Color(0xFF94A3B8);
  static const textOnAccent = Color(0xFFFFFFFF);

  // Borders
  static const border = Color(0xFFE2E8F0);
  static const borderLight = Color(0xFFF1F5F9);

  // Semantics
  static const like = Color(0xFF14B8A6);
  static const dislike = Color(0xFFCBD5E1);
  static const error = Color(0xFFEF4444);
  static const success = Color(0xFF22C55E);

  // Nav
  static const navBarBg = Color(0xF5FFFFFF);

  // Card overlays
  static const shimmerBase = Color(0xFFE2E8F0);
  static const shimmerHighlight = Color(0xFFF8FAFC);
}
