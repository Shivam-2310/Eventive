import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../app_shell.dart';
import '../../models/interest.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';
import '../auth/sign_in_screen.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _pageController = PageController();
  int _currentPage = 0;

  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _headlineCtrl = TextEditingController();
  final _companyCtrl = TextEditingController();
  bool _obscurePassword = true;

  bool _loadingInterests = false;
  List<InterestRead> _interests = const [];
  final Set<int> _selectedInterestIds = <int>{};

  bool _submitting = false;

  static const _intros = [
    _IntroPage(
      icon: Icons.people_rounded,
      title: 'Flonnect',
      subtitle: 'Discover people who share your vibe.\nNetworking, but make it fun.',
      gradientColors: [Color(0xFF14B8A6), Color(0xFF06B6D4)],
    ),
    _IntroPage(
      icon: Icons.explore_rounded,
      title: 'Discover Events',
      subtitle: 'Find sessions, workshops, and parties\nthat match your interests.',
      gradientColors: [Color(0xFF8B5CF6), Color(0xFFA78BFA)],
    ),
    _IntroPage(
      icon: Icons.auto_awesome,
      title: 'Ask Flo Bot',
      subtitle: 'Your AI guide to everything Flo.\nSchedules, tips, recs — just ask.',
      gradientColors: [Color(0xFF0EA5E9), Color(0xFF38BDF8)],
    ),
  ];

  int get _totalPages => _intros.length + 2; // + profile + interests

  bool get _isProfilePage => _currentPage == _intros.length;
  bool get _isInterestsPage => _currentPage == _intros.length + 1;

  @override
  void dispose() {
    _pageController.dispose();
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _headlineCtrl.dispose();
    _companyCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadInterests() async {
    if (_interests.isNotEmpty || _loadingInterests) return;
    setState(() => _loadingInterests = true);
    try {
      final list = await ServiceScope.of(context).interests.list();
      if (!mounted) return;
      setState(() {
        _interests = list;
        _loadingInterests = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingInterests = false);
      showErrorSnack(context, e);
    }
  }

  void _next() {
    if (_isInterestsPage) {
      _submit();
      return;
    }
    if (_currentPage < _totalPages - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeOutCubic,
      );
    }
  }

  bool _canAdvance() {
    if (_isProfilePage) {
      return _nameCtrl.text.trim().isNotEmpty &&
          _emailCtrl.text.trim().contains('@') &&
          _passwordCtrl.text.length >= 6;
    }
    if (_isInterestsPage) {
      return true;
    }
    return true;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final services = ServiceScope.of(context);
    setState(() => _submitting = true);
    try {
      final pair = await services.auth.register(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
        name: _nameCtrl.text.trim(),
        headline: _headlineCtrl.text.trim().isEmpty
            ? null
            : _headlineCtrl.text.trim(),
        company: _companyCtrl.text.trim().isEmpty
            ? null
            : _companyCtrl.text.trim(),
      );
      if (_selectedInterestIds.isNotEmpty) {
        await services.users.setInterests(
          pair.user.id,
          _selectedInterestIds.toList(),
        );
      }
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        PageRouteBuilder(
          pageBuilder: (_, _, _) => const AppShell(),
          transitionsBuilder: (_, animation, _, child) =>
              FadeTransition(opacity: animation, child: child),
          transitionDuration: const Duration(milliseconds: 500),
        ),
        (_) => false,
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
      setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isLast = _currentPage == _totalPages - 1;
    return Scaffold(
      backgroundColor: AppColors.background,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding:
                  const EdgeInsets.fromLTRB(AppSpacing.lg, 12, AppSpacing.md, 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _wordmark(),
                  if (!_isProfilePage && !_isInterestsPage)
                    TextButton(
                      onPressed: () => _pageController.animateToPage(
                        _intros.length,
                        duration: const Duration(milliseconds: 400),
                        curve: Curves.easeOutCubic,
                      ),
                      child: Text(
                        'Skip',
                        style: TextStyle(
                          color: AppColors.textTertiary,
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                onPageChanged: (i) {
                  setState(() => _currentPage = i);
                  if (i == _intros.length + 1) _loadInterests();
                },
                itemCount: _totalPages,
                itemBuilder: (_, i) {
                  if (i < _intros.length) return _buildIntroPage(_intros[i]);
                  if (i == _intros.length) return _buildProfilePage();
                  return _buildInterestsPage();
                },
              ),
            ),
            Padding(
              padding:
                  const EdgeInsets.fromLTRB(AppSpacing.xl, 0, AppSpacing.xl, 32),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(_totalPages, (i) {
                      final active = i == _currentPage;
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        curve: Curves.easeOutCubic,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: active ? 24 : 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color:
                              active ? AppColors.accent : AppColors.surfaceMuted,
                          borderRadius: AppRadius.borderFull,
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 54,
                    child: GestureDetector(
                      onTap: !_canAdvance() || _submitting ? null : _next,
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: _canAdvance() && !_submitting
                                ? AppColors.accentGradient
                                : [
                                    AppColors.surfaceMuted,
                                    AppColors.surfaceMuted
                                  ],
                          ),
                          borderRadius: AppRadius.borderFull,
                          boxShadow: _canAdvance() && !_submitting
                              ? [
                                  BoxShadow(
                                    color:
                                        AppColors.accent.withValues(alpha: 0.3),
                                    blurRadius: 20,
                                    offset: const Offset(0, 8),
                                  ),
                                ]
                              : [],
                        ),
                        child: Center(
                          child: _submitting
                              ? const SizedBox(
                                  width: 22,
                                  height: 22,
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                    strokeWidth: 2.5,
                                  ),
                                )
                              : Text(
                                  isLast
                                      ? 'Get Started'
                                      : (_isProfilePage
                                          ? 'Continue'
                                          : 'Next'),
                                  style: GoogleFonts.plusJakartaSans(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                    color: Colors.white,
                                  ),
                                ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _wordmark() => ShaderMask(
        shaderCallback: (bounds) => const LinearGradient(
          colors: AppColors.accentGradient,
        ).createShader(bounds),
        child: Text(
          'flo',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 24,
            fontWeight: FontWeight.w800,
            color: Colors.white,
            letterSpacing: -1,
          ),
        ),
      );

  Widget _buildIntroPage(_IntroPage page) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: page.gradientColors,
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              boxShadow: [
                BoxShadow(
                  color: page.gradientColors.first.withValues(alpha: 0.3),
                  blurRadius: 30,
                  offset: const Offset(0, 12),
                ),
              ],
            ),
            child: Icon(page.icon, size: 52, color: Colors.white),
          ),
          const SizedBox(height: 40),
          Text(
            page.title,
            style: GoogleFonts.plusJakartaSans(
              fontSize: 30,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
              letterSpacing: -0.8,
            ),
          ),
          const SizedBox(height: 14),
          Text(
            page.subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 16,
              color: AppColors.textSecondary,
              height: 1.55,
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProfilePage() {
    return ListView(
      padding:
          const EdgeInsets.fromLTRB(AppSpacing.xl, 8, AppSpacing.xl, 24),
      children: [
        Text(
          'Tell us about you',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 26,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'We use this to help you connect with the right people.',
          style: TextStyle(
            fontSize: 14,
            color: AppColors.textTertiary,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 28),
        _labelledField(label: 'Name *', controller: _nameCtrl, hint: 'Alice Doe'),
        const SizedBox(height: 16),
        _labelledField(
          label: 'Email *',
          controller: _emailCtrl,
          hint: 'alice@example.com',
          keyboardType: TextInputType.emailAddress,
        ),
        const SizedBox(height: 16),
        _labelledField(
          label: 'Password *',
          controller: _passwordCtrl,
          hint: 'At least 6 characters',
          obscure: _obscurePassword,
          suffixIcon: IconButton(
            icon: Icon(
              _obscurePassword
                  ? Icons.visibility_rounded
                  : Icons.visibility_off_rounded,
              color: AppColors.textTertiary,
              size: 20,
            ),
            onPressed: () =>
                setState(() => _obscurePassword = !_obscurePassword),
          ),
        ),
        const SizedBox(height: 16),
        _labelledField(
          label: 'Headline',
          controller: _headlineCtrl,
          hint: 'AI Engineer building the future',
        ),
        const SizedBox(height: 16),
        _labelledField(
          label: 'Company',
          controller: _companyCtrl,
          hint: 'Flo Labs',
        ),
        const SizedBox(height: 20),
        Center(
          child: TextButton(
            onPressed: _submitting
                ? null
                : () {
                    Navigator.of(context).pushReplacement(
                      MaterialPageRoute(
                        builder: (_) => const SignInScreen(),
                      ),
                    );
                  },
            child: RichText(
              text: TextSpan(
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textTertiary,
                ),
                children: [
                  const TextSpan(text: 'Already have an account? '),
                  TextSpan(
                    text: 'Sign in',
                    style: TextStyle(
                      color: AppColors.accent,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _labelledField({
    required String label,
    required TextEditingController controller,
    required String hint,
    TextInputType? keyboardType,
    bool obscure = false,
    Widget? suffixIcon,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: AppColors.textSecondary,
          ),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          obscureText: obscure,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: hint,
            suffixIcon: suffixIcon,
          ),
        ),
      ],
    );
  }

  Widget _buildInterestsPage() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 8),
          Text(
            'Pick your interests',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 26,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Optional — we\'ll use these to tune your recs.',
            style: TextStyle(
              fontSize: 14,
              color: AppColors.textTertiary,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 20),
          Expanded(
            child: _loadingInterests
                ? const Center(
                    child:
                        CircularProgressIndicator(color: AppColors.accent),
                  )
                : _interests.isEmpty
                    ? Center(
                        child: Text(
                          'No interests yet. Skip to continue.',
                          style: TextStyle(color: AppColors.textTertiary),
                        ),
                      )
                    : SingleChildScrollView(
                        child: Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: _interests.map(_buildInterestChip).toList(),
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildInterestChip(InterestRead interest) {
    final selected = _selectedInterestIds.contains(interest.id);
    return GestureDetector(
      onTap: () {
        setState(() {
          if (selected) {
            _selectedInterestIds.remove(interest.id);
          } else {
            _selectedInterestIds.add(interest.id);
          }
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? AppColors.accent : AppColors.surface,
          border: Border.all(
            color:
                selected ? AppColors.accent : AppColors.borderLight,
          ),
          borderRadius: AppRadius.borderFull,
        ),
        child: Text(
          interest.label,
          style: TextStyle(
            color: selected ? Colors.white : AppColors.textPrimary,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _IntroPage {
  final IconData icon;
  final String title;
  final String subtitle;
  final List<Color> gradientColors;

  const _IntroPage({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.gradientColors,
  });
}
