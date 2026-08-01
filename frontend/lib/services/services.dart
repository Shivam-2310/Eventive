/// One-stop service locator.
///
/// All UI code goes through `Services.of(context)` (or `Services.instance`
/// once bootstrapped) to grab a typed backend client — no direct
/// `ApiClient` calls in widgets.
library;

import 'package:flutter/widgets.dart';

import 'admin_service.dart';
import 'ai_service.dart';
import 'api_client.dart';
import 'auth_service.dart';
import 'chat_service.dart';
import 'event_interactions_store.dart';
import 'event_service.dart';
import 'ingest_service.dart';
import 'interest_service.dart';
import 'mission_service.dart';
import 'notification_service.dart';
import 'pulse_service.dart';
import 'recommendation_service.dart';
import 'reel_service.dart';
import 'session.dart';
import 'speaker_service.dart';
import 'user_service.dart';
import 'ws_service.dart';

class Services {
  final ApiClient api;
  final Session session;
  final AuthService auth;

  final UserService users;
  final InterestService interests;
  final SpeakerService speakers;
  final EventService events;
  final EventInteractionsStore eventInteractions;
  final ReelService reels;
  final RecommendationService recommendations;
  final ChatService chat;
  final NotificationService notifications;
  final AiService ai;
  final MissionService missions;
  final IngestService ingest;
  final AdminService admin;
  final PulseService pulse;
  final WsService ws;

  Services._({
    required this.api,
    required this.session,
    required this.auth,
    required this.users,
    required this.interests,
    required this.speakers,
    required this.events,
    required this.eventInteractions,
    required this.reels,
    required this.recommendations,
    required this.chat,
    required this.notifications,
    required this.ai,
    required this.missions,
    required this.ingest,
    required this.admin,
    required this.pulse,
    required this.ws,
  });

  factory Services.build({ApiClient? apiOverride, Session? sessionOverride}) {
    final api = apiOverride ?? ApiClient();
    final session = sessionOverride ?? Session();
    final auth = AuthService(api, session);
    auth.bind();
    final events = EventService(api);
    final eventInteractions = EventInteractionsStore(events);
    // Keep the interactions store aligned with the signed-in user: hydrate
    // when they log in, clear on sign-out. Session extends ChangeNotifier
    // so we just subscribe here at construction and let it fire naturally.
    session.addListener(() {
      final uid = session.userId;
      if (uid == null) {
        eventInteractions.clear();
      } else {
        eventInteractions.refresh(uid);
      }
    });
    return Services._(
      api: api,
      session: session,
      auth: auth,
      users: UserService(api),
      interests: InterestService(api),
      speakers: SpeakerService(api),
      events: events,
      eventInteractions: eventInteractions,
      reels: ReelService(api),
      recommendations: RecommendationService(api),
      chat: ChatService(api),
      notifications: NotificationService(api),
      ai: AiService(api),
      missions: MissionService(api),
      ingest: IngestService(api),
      admin: AdminService(api),
      pulse: PulseService(api),
      ws: WsService(api),
    );
  }
}

/// Simple `InheritedWidget` scope so any descendant can grab [Services].
class ServiceScope extends InheritedWidget {
  final Services services;

  const ServiceScope({
    super.key,
    required this.services,
    required super.child,
  });

  static Services of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<ServiceScope>();
    assert(scope != null, 'ServiceScope missing above this widget.');
    return scope!.services;
  }

  @override
  bool updateShouldNotify(ServiceScope oldWidget) =>
      oldWidget.services != services;
}
