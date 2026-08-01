import 'package:flo_app/main.dart';
import 'package:flo_app/services/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('App renders without crashing', (WidgetTester tester) async {
    // `Services.build()` produces a real service locator; nothing fires a
    // network call until a widget actually asks for data, so the smoke pump
    // stays offline.
    final services = Services.build();
    await tester.pumpWidget(FloApp(services: services));
    expect(find.byType(FloApp), findsOneWidget);
  });
}
