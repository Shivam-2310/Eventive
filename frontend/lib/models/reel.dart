import 'parse.dart';

/// Mirrors `ReelRead` from API_CONTRACT §9.6.
class ReelRead {
  final int id;
  final int userId;
  final int? eventId;
  final int? speakerId;
  final String? caption;
  final String? videoUrl;
  final String? thumbnailUrl;
  final double? durationSeconds;
  final String status;
  final String? transcript;
  final String? error;
  final DateTime createdAt;

  const ReelRead({
    required this.id,
    required this.userId,
    this.eventId,
    this.speakerId,
    this.caption,
    this.videoUrl,
    this.thumbnailUrl,
    this.durationSeconds,
    required this.status,
    this.transcript,
    this.error,
    required this.createdAt,
  });

  factory ReelRead.fromJson(Map<String, dynamic> j) => ReelRead(
        id: parseIntOr(j['id'], 0),
        userId: parseIntOr(j['user_id'], 0),
        eventId: parseInt(j['event_id']),
        speakerId: parseInt(j['speaker_id']),
        caption: parseString(j['caption']),
        videoUrl: parseString(j['video_url']),
        thumbnailUrl: parseString(j['thumbnail_url']),
        durationSeconds: parseDouble(j['duration_seconds']),
        status: parseString(j['status']) ?? 'processing',
        transcript: parseString(j['transcript']),
        error: parseString(j['error']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
      );

  bool get isReady => status == 'ready';
  bool get isProcessing => status == 'processing';
  bool get isFailed => status == 'failed';
}

/// One row of `GET /reels/feed`.
class ReelFeedItem {
  final ReelRead reel;
  final double score;
  final int likes;

  const ReelFeedItem({
    required this.reel,
    required this.score,
    required this.likes,
  });

  factory ReelFeedItem.fromJson(Map<String, dynamic> j) => ReelFeedItem(
        reel: ReelRead.fromJson(j['reel'] as Map<String, dynamic>),
        score: parseDouble(j['score']) ?? 0.0,
        likes: parseIntOr(j['likes'], 0),
      );
}

const reelInteractionTypes = <String>[
  'view',
  'like',
  'share',
  'save',
  'skip',
  'complete_watch',
];
