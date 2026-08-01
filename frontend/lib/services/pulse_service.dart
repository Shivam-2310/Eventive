import '../models/pulse.dart';
import 'api_client.dart';

class PulseService {
  final ApiClient _api;
  PulseService(this._api);

  Future<PulseSnapshot> snapshot() async {
    final j = await _api.get('/admin/pulse/snapshot');
    return PulseSnapshot.fromJson(j as Map<String, dynamic>);
  }
}
