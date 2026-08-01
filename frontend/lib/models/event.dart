import 'parse.dart';
import 'speaker.dart';

/// Backend-hydrated event tag as returned inside `EventRead.interests`.
class EventInterestTag {
  final int id;
  final String label;
  final String category;

  const EventInterestTag({
    required this.id,
    required this.label,
    required this.category,
  });

  factory EventInterestTag.fromJson(Map<String, dynamic> j) => EventInterestTag(
        id: parseIntOr(j['id'], 0),
        label: parseString(j['label']) ?? '',
        category: parseString(j['category']) ?? 'topic',
      );
}

/// Mirrors `EventRead` from API_CONTRACT §20.1.
class EventRead {
  final int id;
  final String? externalId;
  final String title;
  final String? description;
  final String? abstractText;
  final String? track;
  final DateTime? startTime;
  final DateTime? endTime;
  final String? timezone;
  final String? location;
  final String? room;
  final int? capacity;
  final String status;
  final String? coverImageUrl;
  final String? vibeText;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<SpeakerRead> speakers;
  final List<EventInterestTag> interests;

  const EventRead({
    required this.id,
    this.externalId,
    required this.title,
    this.description,
    this.abstractText,
    this.track,
    this.startTime,
    this.endTime,
    this.timezone,
    this.location,
    this.room,
    this.capacity,
    required this.status,
    this.coverImageUrl,
    this.vibeText,
    required this.createdAt,
    required this.updatedAt,
    required this.speakers,
    required this.interests,
  });

  factory EventRead.fromJson(Map<String, dynamic> j) => EventRead(
        id: parseIntOr(j['id'], 0),
        externalId: parseString(j['external_id']),
        title: parseString(j['title']) ?? '',
        description: parseString(j['description']),
        abstractText: parseString(j['abstract']),
        track: parseString(j['track']),
        startTime: parseDate(j['start_time']),
        endTime: parseDate(j['end_time']),
        timezone: parseString(j['timezone']),
        location: parseString(j['location']),
        room: parseString(j['room']),
        capacity: parseInt(j['capacity']),
        status: parseString(j['status']) ?? 'scheduled',
        coverImageUrl: parseString(j['cover_image_url']),
        vibeText: parseString(j['vibe_text']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
        updatedAt: parseDate(j['updated_at']) ?? DateTime.now().toUtc(),
        speakers: parseList(j['speakers'],
            (e) => SpeakerRead.fromJson(e as Map<String, dynamic>)),
        interests: parseList(j['interests'],
            (e) => EventInterestTag.fromJson(e as Map<String, dynamic>)),
      );

  String get locationSummary {
    if ((location ?? '').isEmpty && (room ?? '').isEmpty) return 'TBA';
    if ((location ?? '').isEmpty) return room!;
    if ((room ?? '').isEmpty) return location!;
    return '$location · $room';
  }
}

const eventStatuses = <String>[
  'scheduled',
  'live',
  'delayed',
  'finished',
  'canceled',
];

/// Body for POST `/events` and PATCH `/events/{id}`.
class EventCreate {
  final String? externalId;
  final String title;
  final String? description;
  final String? abstractText;
  final String? track;
  final DateTime? startTime;
  final DateTime? endTime;
  final String? timezone;
  final String? location;
  final String? room;
  final int? capacity;
  final String status;
  final String? coverImageUrl;

  const EventCreate({
    this.externalId,
    required this.title,
    this.description,
    this.abstractText,
    this.track,
    this.startTime,
    this.endTime,
    this.timezone,
    this.location,
    this.room,
    this.capacity,
    this.status = 'scheduled',
    this.coverImageUrl,
  });

  Map<String, dynamic> toJson() => {
        if (externalId != null) 'external_id': externalId,
        'title': title,
        if (description != null) 'description': description,
        if (abstractText != null) 'abstract': abstractText,
        if (track != null) 'track': track,
        if (startTime != null) 'start_time': startTime!.toUtc().toIso8601String(),
        if (endTime != null) 'end_time': endTime!.toUtc().toIso8601String(),
        if (timezone != null) 'timezone': timezone,
        if (location != null) 'location': location,
        if (room != null) 'room': room,
        if (capacity != null) 'capacity': capacity,
        'status': status,
        if (coverImageUrl != null) 'cover_image_url': coverImageUrl,
      };
}

/// One prompt slot inside an event discovery card.
class EventCardPrompt {
  final String promptType;
  final int? promptRefId;
  final String label;
  final String? body;
  final bool alreadyLiked;

  const EventCardPrompt({
    required this.promptType,
    this.promptRefId,
    required this.label,
    this.body,
    required this.alreadyLiked,
  });

  factory EventCardPrompt.fromJson(Map<String, dynamic> j) => EventCardPrompt(
        promptType: parseString(j['prompt_type']) ?? 'cover',
        promptRefId: parseInt(j['prompt_ref_id']),
        label: parseString(j['label']) ?? '',
        body: parseString(j['body']),
        alreadyLiked: parseBool(j['already_liked']),
      );
}

/// The full discovery card — see API_CONTRACT §7.3.
class EventCard {
  final EventRead event;
  final List<EventCardPrompt> prompts;
  final bool alreadyLikedSpeaker;

  const EventCard({
    required this.event,
    required this.prompts,
    required this.alreadyLikedSpeaker,
  });

  factory EventCard.fromJson(Map<String, dynamic> j) => EventCard(
        event: EventRead.fromJson(j['event'] as Map<String, dynamic>),
        prompts: parseList(j['prompts'],
            (e) => EventCardPrompt.fromJson(e as Map<String, dynamic>)),
        alreadyLikedSpeaker: parseBool(j['already_liked_speaker']),
      );
}

class EventDiscoverPage {
  final List<EventCard> cards;
  final int? nextCursor;

  const EventDiscoverPage({required this.cards, this.nextCursor});

  factory EventDiscoverPage.fromJson(Map<String, dynamic> j) => EventDiscoverPage(
        cards: parseList(j['cards'],
            (e) => EventCard.fromJson(e as Map<String, dynamic>)),
        nextCursor: parseInt(j['next_cursor']),
      );
}

const eventPromptTypes = <String>[
  'cover',
  'speaker',
  'topic',
  'when_where',
  'vibe',
  'who_is_going',
];

const eventReactionKinds = <String>['like', 'comment', 'pass'];

const eventInteractionTypes = <String>[
  'like',
  'save',
  'add_to_my_day',
  'mark_attended',
  'add_to_calendar',
  'rsvp',
];
