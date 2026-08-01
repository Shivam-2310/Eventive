import '../models/ingestion.dart';
import 'api_client.dart';

class IngestService {
  final ApiClient _api;
  IngestService(this._api);

  Future<Map<String, dynamic>> uploadEventsCsv({
    required List<int> bytes,
    required String filename,
  }) async {
    final j = await _api.uploadMultipart(
      '/ingest/events',
      fileField: 'file',
      bytes: bytes,
      filename: filename,
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> uploadSpeakersCsv({
    required List<int> bytes,
    required String filename,
  }) async {
    final j = await _api.uploadMultipart(
      '/ingest/speakers',
      fileField: 'file',
      bytes: bytes,
      filename: filename,
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<Map<String, dynamic>> uploadJson({
    required List<int> bytes,
    required String filename,
  }) async {
    final j = await _api.uploadMultipart(
      '/ingest/json',
      fileField: 'file',
      bytes: bytes,
      filename: filename,
    );
    return Map<String, dynamic>.from(j as Map);
  }

  Future<List<IngestionJobRead>> jobs() async {
    final j = await _api.get('/ingest/jobs');
    return (j as List)
        .map((e) => IngestionJobRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<IngestionJobRead> job(int id) async {
    final j = await _api.get('/ingest/jobs/$id');
    return IngestionJobRead.fromJson(j as Map<String, dynamic>);
  }
}
