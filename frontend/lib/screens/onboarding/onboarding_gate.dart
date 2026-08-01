import 'package:flutter/material.dart';

import '../../app_shell.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../auth/sign_in_screen.dart';

/// Validates the persisted access token by calling `/auth/me`. On any failure
/// bounces us back to [SignInScreen].
class OnboardingGate extends StatefulWidget {
  const OnboardingGate({super.key});

  @override
  State<OnboardingGate> createState() => _OnboardingGateState();
}

class _OnboardingGateState extends State<OnboardingGate> {
  bool _loading = true;
  bool _bounce = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_loading) _hydrate();
  }

  Future<void> _hydrate() async {
    final services = ServiceScope.of(context);
    if (!services.session.isAuthenticated) {
      setState(() {
        _loading = false;
        _bounce = true;
      });
      return;
    }
    final user = await services.auth.me();
    if (!mounted) return;
    if (user == null) {
      setState(() {
        _loading = false;
        _bounce = true;
      });
      return;
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppColors.background,
        body: Center(
          child: CircularProgressIndicator(color: AppColors.accent),
        ),
      );
    }
    if (_bounce) return const SignInScreen();
    return const AppShell();
  }
}
