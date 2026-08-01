import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../theme/colors.dart';

/// Animated splash shown before the app boots into its first real screen.
///
/// Layered sine waves slide in from the top and bottom, then part outward to
/// reveal the "flo" wordmark, which itself scales/fades in with an elastic
/// pop. After the sequence finishes we fade-through into [destination].
///
/// This is purely presentational — no session/auth logic lives here; the
/// caller decides which screen to route to.
class SplashScreen extends StatefulWidget {
  final Widget destination;
  const SplashScreen({super.key, required this.destination});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  late final AnimationController _waveController;
  late final AnimationController _revealController;
  late final AnimationController _textController;

  late final Animation<double> _wavePhase;
  late final Animation<double> _revealSlide;
  late final Animation<double> _textOpacity;
  late final Animation<double> _textScale;
  late final Animation<double> _bgFade;

  bool _navigated = false;

  @override
  void initState() {
    super.initState();

    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
      ),
    );

    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2500),
    )..repeat();

    _revealController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    );

    _textController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    _wavePhase = Tween(begin: 0.0, end: 2 * pi).animate(_waveController);

    _revealSlide = CurvedAnimation(
      parent: _revealController,
      curve: const Interval(0.0, 0.7, curve: Curves.easeOutCubic),
    );

    _bgFade = CurvedAnimation(
      parent: _revealController,
      curve: const Interval(0.0, 0.4, curve: Curves.easeOut),
    );

    _textOpacity = CurvedAnimation(
      parent: _textController,
      curve: Curves.easeIn,
    );

    _textScale = Tween(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _textController, curve: Curves.elasticOut),
    );

    _startSequence();
  }

  Future<void> _startSequence() async {
    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    _revealController.forward();
    await Future.delayed(const Duration(milliseconds: 1200));
    if (!mounted) return;
    _textController.forward();
    await Future.delayed(const Duration(milliseconds: 2200));
    if (!mounted || _navigated) return;
    _navigated = true;

    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
      ),
    );

    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 600),
        pageBuilder: (_, __, ___) => widget.destination,
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
      ),
    );
  }

  @override
  void dispose() {
    _waveController.dispose();
    _revealController.dispose();
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0F1C),
      body: AnimatedBuilder(
        animation: Listenable.merge([
          _waveController,
          _revealController,
          _textController,
        ]),
        builder: (context, _) {
          return Stack(
            children: [
              Positioned.fill(
                child: Opacity(
                  opacity: _bgFade.value,
                  child: Container(
                    decoration: const BoxDecoration(
                      gradient: RadialGradient(
                        center: Alignment(0, 0.2),
                        radius: 1.2,
                        colors: [
                          Color(0xFF0D3D56),
                          Color(0xFF0A0F1C),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              Positioned.fill(
                child: CustomPaint(
                  painter: _WavePainter(
                    phase: _wavePhase.value * 0.7,
                    direction: -1,
                    revealProgress: _revealSlide.value,
                    color1: AppColors.accentDark.withValues(alpha: 0.35),
                    color2: const Color(0xFF06B6D4).withValues(alpha: 0.2),
                    amplitude: 28,
                    frequency: 1.2,
                    verticalOffset: 0.08,
                  ),
                ),
              ),

              Positioned.fill(
                child: CustomPaint(
                  painter: _WavePainter(
                    phase: _wavePhase.value,
                    direction: 1,
                    revealProgress: _revealSlide.value,
                    color1: AppColors.accent.withValues(alpha: 0.55),
                    color2: const Color(0xFF06B6D4).withValues(alpha: 0.4),
                    amplitude: 22,
                    frequency: 1.5,
                    verticalOffset: 0.0,
                  ),
                ),
              ),

              Positioned.fill(
                child: CustomPaint(
                  painter: _WavePainter(
                    phase: _wavePhase.value * 1.3,
                    direction: -1,
                    revealProgress: _revealSlide.value,
                    color1: const Color(0xFF2DD4BF).withValues(alpha: 0.3),
                    color2: AppColors.accent.withValues(alpha: 0.15),
                    amplitude: 16,
                    frequency: 2.0,
                    verticalOffset: -0.06,
                  ),
                ),
              ),

              Center(
                child: Opacity(
                  opacity: _textOpacity.value,
                  child: Transform.scale(
                    scale: _textScale.value,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'flo',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 72,
                            fontWeight: FontWeight.w800,
                            color: Colors.white,
                            letterSpacing: -3,
                            height: 1.0,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'find your flow',
                          style: GoogleFonts.plusJakartaSans(
                            fontSize: 14,
                            fontWeight: FontWeight.w400,
                            color: Colors.white.withValues(alpha: 0.6),
                            letterSpacing: 4,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// Paints one horizontal sine-wave band that:
///   1. Slides in vertically from the nearest screen edge as [revealProgress]
///      grows from 0 → ~0.5.
///   2. Parts outward from the center to open a "gap" as it approaches 1.0,
///      revealing whatever is behind the waves.
class _WavePainter extends CustomPainter {
  final double phase;
  final int direction;
  final double revealProgress;
  final Color color1;
  final Color color2;
  final double amplitude;
  final double frequency;
  final double verticalOffset;

  _WavePainter({
    required this.phase,
    required this.direction,
    required this.revealProgress,
    required this.color1,
    required this.color2,
    required this.amplitude,
    required this.frequency,
    required this.verticalOffset,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final midY = h / 2;

    final slideIn = Curves.easeOutCubic.transform(revealProgress.clamp(0, 1));

    final partAmount = revealProgress > 0.5
        ? Curves.easeInOutCubic
            .transform(((revealProgress - 0.5) * 2).clamp(0, 1))
        : 0.0;
    final gapHalf = partAmount * h * 0.18;

    final paint = Paint()..style = PaintingStyle.fill;

    _drawWaveHalf(
      canvas: canvas,
      paint: paint,
      isTop: true,
      midY: midY,
      slideIn: slideIn,
      gapHalf: gapHalf,
      w: w,
      h: h,
    );

    _drawWaveHalf(
      canvas: canvas,
      paint: paint,
      isTop: false,
      midY: midY,
      slideIn: slideIn,
      gapHalf: gapHalf,
      w: w,
      h: h,
    );
  }

  void _drawWaveHalf({
    required Canvas canvas,
    required Paint paint,
    required bool isTop,
    required double midY,
    required double slideIn,
    required double gapHalf,
    required double w,
    required double h,
  }) {
    final path = Path();
    final offsetY = verticalOffset * h;

    if (isTop) {
      final edgeY = -h * (1 - slideIn);
      final waveBaseY = midY - gapHalf + offsetY + edgeY;

      path.moveTo(0, 0);
      for (double x = 0; x <= w; x += 2) {
        final normalizedX = x / w;
        final y = waveBaseY +
            sin((normalizedX * frequency * 2 * pi) + (phase * direction)) *
                amplitude *
                slideIn;
        path.lineTo(x, y);
      }
      path.lineTo(w, 0);
      path.close();

      paint.shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [color2, color1],
      ).createShader(Rect.fromLTWH(0, 0, w, waveBaseY + amplitude));
    } else {
      final edgeY = h * (1 - slideIn);
      final waveBaseY = midY + gapHalf + offsetY + edgeY;

      path.moveTo(0, h);
      for (double x = 0; x <= w; x += 2) {
        final normalizedX = x / w;
        final y = waveBaseY +
            sin((normalizedX * frequency * 2 * pi) +
                    (phase * direction) +
                    pi) *
                amplitude *
                slideIn;
        path.lineTo(x, y);
      }
      path.lineTo(w, h);
      path.close();

      paint.shader = LinearGradient(
        begin: Alignment.bottomCenter,
        end: Alignment.topCenter,
        colors: [color2, color1],
      ).createShader(
        Rect.fromLTWH(0, waveBaseY - amplitude, w, h - waveBaseY + amplitude),
      );
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _WavePainter oldDelegate) => true;
}
