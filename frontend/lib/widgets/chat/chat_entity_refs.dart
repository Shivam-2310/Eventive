import '../../models/ai.dart';

/// One entity reference the chatbot mentioned in an assistant message.
///
/// Refs are extracted from two sources and deduped by [key]:
///   * Inline tokens the agent writes into the streaming text —
///     `[event:12]`, `[speaker:3]`, `[user:22]`.
///   * `citation` SSE frames the backend emits when the `search_catalog`
///     tool returns event / speaker rows.
class ChatEntityRef {
  final ChatEntityKind kind;
  final int id;

  /// Optional title we already know (e.g. from a `citation` frame). Cards
  /// use this to show *something* immediately while the full record loads.
  final String? preloadedTitle;

  const ChatEntityRef({
    required this.kind,
    required this.id,
    this.preloadedTitle,
  });

  String get key => '${kind.name}:$id';
}

enum ChatEntityKind { event, user, speaker }

/// `[event:12]` / `[user:22]` / `[speaker:3]`. Case-insensitive, tolerates
/// surrounding whitespace inside the brackets.
final RegExp _tokenRe = RegExp(
  r'\[\s*(event|user|speaker)\s*:\s*(\d+)\s*\]',
  caseSensitive: false,
);

/// Extract [ChatEntityRef]s that are *actually relevant* to what the
/// assistant said. Two-stage strategy:
///
/// 1. **Inline `[kind:id]` tokens** — the agent explicitly cited these
///    entities. Highest confidence; if we find any we trust them and
///    ignore any other signal.
/// 2. **Backend-supplied candidates** — we combine two sources:
///      * `citation` SSE frames (`{citation: "event:12", title, url}`),
///      * the raw rows from the `search_catalog` SQL result payload
///        (`sqlResult.rows`) — these carry `id + title` (or `name`) even
///        when the backend didn't fire a citation frame (aggregate SQLs,
///        speaker/user views, …).
///    Both sources feed the same filter: keep only candidates whose
///    **title / name actually appears in the visible answer text**
///    (full string, or its leader up to the first colon / first 4 words,
///    case-insensitive). This kills the "answer talks about event 5 but
///    a card for event 8 pops up because the SQL row was in scope" bug.
///
/// The list is capped by [maxRefs] to avoid a runaway answer spawning
/// dozens of network hydration calls.
List<ChatEntityRef> extractChatRefs(
  String text,
  List<AiCitation> citations, {
  Map<String, dynamic>? sqlResult,
  int maxRefs = 8,
}) {
  final seen = <String>{};
  final tokenRefs = <ChatEntityRef>[];

  for (final m in _tokenRe.allMatches(text)) {
    final kind = _parseKind(m.group(1));
    final id = int.tryParse(m.group(2) ?? '');
    if (kind == null || id == null) continue;
    final ref = ChatEntityRef(kind: kind, id: id);
    if (seen.add(ref.key)) tokenRefs.add(ref);
    if (tokenRefs.length >= maxRefs) return tokenRefs;
  }

  // If the agent explicitly cited entities, trust those and stop —
  // don't dilute with unrelated tool-call rows.
  if (tokenRefs.isNotEmpty) return tokenRefs;

  final candidates = <_Candidate>[];
  for (final c in citations) {
    final parts = c.citation.split(':');
    if (parts.length != 2) continue;
    final kind = _parseKind(parts[0]);
    final id = int.tryParse(parts[1]);
    final title = c.title?.trim();
    if (kind == null || id == null || title == null || title.isEmpty) continue;
    candidates.add(_Candidate(kind: kind, id: id, title: title));
  }
  candidates.addAll(_candidatesFromSqlRows(sqlResult));

  final lowerText = text.toLowerCase();
  final out = <ChatEntityRef>[];
  for (final c in candidates) {
    if (!_titleMentionedIn(lowerText, c.title)) continue;
    final key = '${c.kind.name}:${c.id}';
    if (!seen.add(key)) continue;
    out.add(ChatEntityRef(kind: c.kind, id: c.id, preloadedTitle: c.title));
    if (out.length >= maxRefs) break;
  }
  return out;
}

/// One candidate ref pulled off a citation frame or an sql-result row.
class _Candidate {
  final ChatEntityKind kind;
  final int id;
  final String title;

  const _Candidate({required this.kind, required this.id, required this.title});
}

/// Best-effort mining of `{event|speaker|user}` refs out of the `sqlResult`
/// payload the backend sent after `search_catalog`. The row shape depends
/// on the view the NL2SQL layer picked, so we sniff by columns:
///   * `track` or `start_time` present → `ai_public_events` → event.
///   * `bio` or `headshot_url` or `speaker`-ish `title` present → speaker.
///   * `headline` or `email` present → user.
/// Rows without a recognizable id + title/name are silently skipped.
List<_Candidate> _candidatesFromSqlRows(Map<String, dynamic>? sqlResult) {
  if (sqlResult == null) return const [];
  final rows = sqlResult['rows'];
  if (rows is! List) return const [];
  final out = <_Candidate>[];
  for (final r in rows) {
    if (r is! Map) continue;
    final row = Map<String, dynamic>.from(r);
    final title = _rowTitle(row);
    final id = _rowId(row);
    if (title == null || title.isEmpty || id == null) continue;
    final kind = _kindFromRow(row);
    if (kind == null) continue;
    out.add(_Candidate(kind: kind, id: id, title: title));
  }
  return out;
}

int? _rowId(Map<String, dynamic> row) {
  for (final key in const ['id', 'event_id', 'speaker_id', 'user_id']) {
    final v = row[key];
    if (v is int) return v;
    if (v is String) {
      final parsed = int.tryParse(v);
      if (parsed != null) return parsed;
    }
  }
  return null;
}

String? _rowTitle(Map<String, dynamic> row) {
  for (final key in const ['title', 'name', 'label']) {
    final v = row[key];
    if (v is String && v.trim().isNotEmpty) return v.trim();
  }
  return null;
}

ChatEntityKind? _kindFromRow(Map<String, dynamic> row) {
  if (row.containsKey('track') ||
      row.containsKey('start_time') ||
      row.containsKey('end_time') ||
      row.containsKey('room')) {
    return ChatEntityKind.event;
  }
  if (row.containsKey('bio') || row.containsKey('headshot_url')) {
    return ChatEntityKind.speaker;
  }
  if (row.containsKey('headline') ||
      row.containsKey('email') ||
      row.containsKey('company')) {
    // Speakers also carry `company`, but they'd have been caught above by
    // `bio`/`headshot_url`. Anything reaching here is a user row.
    return ChatEntityKind.user;
  }
  return null;
}

/// True iff [title] (or its distinguishing leader) is present in
/// [lowerText]. `lowerText` must already be lower-cased.
///
/// Event titles usually look like "Alignment 101: Making LLMs Do What You
/// Mean". Agents love to shorten those to just "Alignment 101" in prose,
/// which is why a straight substring match on the full title misses.
bool _titleMentionedIn(String lowerText, String title) {
  final t = title.toLowerCase();
  if (t.length < 3) return false;
  if (lowerText.contains(t)) return true;

  // Prefix up to the first colon, if any — the "Alignment 101" leader.
  final colon = t.indexOf(':');
  if (colon >= 3 && lowerText.contains(t.substring(0, colon).trim())) {
    return true;
  }

  // First 4 words for names / titles without a colon. 4 words is enough
  // to disambiguate "RAG Deep Dive" from other RAG-related titles without
  // demanding a full 8-word match.
  final words = t.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
  if (words.length >= 2) {
    final leader = words.take(4).join(' ');
    if (leader.length >= 6 && lowerText.contains(leader)) return true;
  }

  return false;
}

ChatEntityKind? _parseKind(String? raw) {
  switch (raw?.toLowerCase()) {
    case 'event':
      return ChatEntityKind.event;
    case 'user':
      return ChatEntityKind.user;
    case 'speaker':
      return ChatEntityKind.speaker;
  }
  return null;
}

/// Remove `[event:5]` / `[user:22]` / `[speaker:3]` tokens from the chat
/// text so the bubble reads as plain prose. Also tidies up any double
/// spaces or stray whitespace around punctuation left behind.
String stripEntityTokens(String text) {
  if (text.isEmpty) return text;
  var out = text.replaceAll(_tokenRe, '');
  // Collapse the "  , " / "  ." / "  !" left when a token sat between
  // punctuation, and any runs of whitespace inside a line.
  out = out.replaceAll(RegExp(r' +([,.;:!?])'), r'$1');
  out = out.replaceAll(RegExp(r'[ \t]{2,}'), ' ');
  // Never trim newlines — the agent uses them for bulleted lists.
  return out.replaceAll(RegExp(r' *\n *'), '\n').trim();
}
