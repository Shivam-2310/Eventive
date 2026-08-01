import 'ai.dart';

enum AiChatRole { user, assistant }

/// One row in the client-side AI chat log.  Assistant rows accumulate
/// streaming [text] chunks and optional [citations] / [toolResult] / [sqlResult]
/// / [intent] side-signals from the SSE stream.
class AiChatMessage {
  final String id;
  final AiChatRole role;
  final DateTime timestamp;
  String text;
  String? intent;
  List<AiCitation> citations;
  Map<String, dynamic>? toolResult;
  Map<String, dynamic>? sqlResult;
  bool streaming;

  AiChatMessage({
    required this.id,
    required this.role,
    required this.timestamp,
    this.text = '',
    this.intent,
    List<AiCitation>? citations,
    this.toolResult,
    this.sqlResult,
    this.streaming = false,
  }) : citations = citations ?? <AiCitation>[];

  bool get isUser => role == AiChatRole.user;
}
