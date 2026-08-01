import 'parse.dart';

/// Mirrors `IngestionJobRead` from API_CONTRACT §8.4.
class IngestionJobRead {
  final int id;
  final String sourceType;
  final String? filename;
  final String status;
  final Map<String, dynamic>? stats;
  final String? error;
  final DateTime createdAt;
  final DateTime? finishedAt;

  const IngestionJobRead({
    required this.id,
    required this.sourceType,
    this.filename,
    required this.status,
    this.stats,
    this.error,
    required this.createdAt,
    this.finishedAt,
  });

  factory IngestionJobRead.fromJson(Map<String, dynamic> j) => IngestionJobRead(
        id: parseIntOr(j['id'], 0),
        sourceType: parseString(j['source_type']) ?? 'events_csv',
        filename: parseString(j['filename']),
        status: parseString(j['status']) ?? 'queued',
        stats: j['stats'] is Map
            ? Map<String, dynamic>.from(j['stats'] as Map)
            : null,
        error: parseString(j['error']),
        createdAt: parseDate(j['created_at']) ?? DateTime.now().toUtc(),
        finishedAt: parseDate(j['finished_at']),
      );

  bool get isTerminal => status == 'success' || status == 'failed';
}

const ingestionSourceTypes = <String>['events_csv', 'speakers_csv', 'json'];
