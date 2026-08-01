import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/auth/sign_in_screen.dart';
import 'screens/onboarding/onboarding_gate.dart';
import 'screens/splash/splash_screen.dart';
import 'services/services.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      statusBarBrightness: Brightness.dark,
    ),
  );

  final services = Services.build();
  await services.session.load();
  runApp(FloApp(services: services));
}

class FloApp extends StatelessWidget {
  final Services services;

  const FloApp({super.key, required this.services});

  @override
  Widget build(BuildContext context) {
    return ServiceScope(
      services: services,
      child: MaterialApp(
        title: 'Flo',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        home: SplashScreen(
          destination: ListenableBuilder(
            listenable: services.session,
            builder: (context, _) {
              if (services.session.isAuthenticated) {
                return const OnboardingGate();
              }
              return const SignInScreen();
            },
          ),
        ),
      ),
    );
  }
}
