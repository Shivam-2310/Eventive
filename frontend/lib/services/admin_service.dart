import '../models/pulse.dart';
import 'api_client.dart';

class AdminService {
  final ApiClient _api;
  AdminService(this._api);

  Future<void> deleteReel(int reelId) async {
    await _api.delete('/admin/reels/$reelId');
  }

  Future<List<AuditLogEntry>> auditLog() async {
    final j = await _api.get('/admin/audit-log');
    return (j as List)
        .map((e) => AuditLogEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
