import 'parse.dart';

/// One canned starter prompt from `GET /ai/suggestions`.
class AiSuggestion {
  final String prompt;
  final String intent;

  const AiSuggestion({required this.prompt, required this.intent});

  factory AiSuggestion.fromJson(Map<String, dynamic> j) => AiSuggestion(
        prompt: parseString(j['prompt']) ?? '',
        intent: parseString(j['intent']) ?? 'semantic_search',
      );
}

/// A single SSE frame from `POST /ai/chat`.
///
/// See API_CONTRACT §14.2 for the shape / ordering guarantees.
class AiChatFrame {
  final String event;
  final Map<String, dynamic> data;

  const AiChatFrame({required this.event, required this.data});

  static AiChatFrame fromRaw(Map<String, dynamic> raw) {
    final data = raw['data'];
    return AiChatFrame(
      event: raw['event']?.toString() ?? 'message',
      data: data is Map<String, dynamic>
          ? data
          : data is Map
              ? Map<String, dynamic>.from(data)
              : <String, dynamic>{'value': data},
    );
  }
}

/// One "sources" tray citation, produced by an SSE `citation` frame.
class AiCitation {
  final String citation;
  final String? title;
  final String? url;

  const AiCitation({required this.citation, this.title, this.url});

  factory AiCitation.fromFrame(Map<String, dynamic> data) => AiCitation(
        citation: parseString(data['citation']) ?? '',
        title: parseString(data['title']),
        url: parseString(data['url']),
      );
}

const aiIntents = <String>['semantic_search', 'structured_query', 'action'];
