import 'parse.dart';

/// Mirrors `MessageRead` from API_CONTRACT §20.7.
class MessageRead {
  final int id;
  final int threadId;
  final int? senderId;
  final String? body;
  final String kind;
  final Map<String, dynamic>? payload;
  final DateTime createdAt;

  const MessageRead({
    required this.id,
    required this.threadId,
    this.senderId,
    this.body,
    required this.kind,
    this.payload,
    required this.createdAt,
  });

  factory MessageRead.fromJson(Map<String, dynamic> j) => MessageRead(
        id: parseIntOr(j['id'], 0),
        threadId: parseIntOr(j['thread_id'], 0),
        senderId: parseInt(j['sender_id']),
        body: parseString(j['body']),
        kind: parseString(j['kind']) ?? 'text',
        payload: j['payload'] is Map
            ? Map<String, dynamic>.from(j['payload'] as Map)
            : null,
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
      );

  bool get isSystem => kind == 'system' || kind == 'icebreaker';
  bool get isAttendTogetherInvite => kind == 'attend_together_invite';
  bool get isAttendTogetherAccepted => kind == 'attend_together_accepted';
}

const messageKinds = <String>[
  'text',
  'attend_together_invite',
  'attend_together_accepted',
  'system',
  'icebreaker',
];
