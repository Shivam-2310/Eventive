import '../models/mission.dart';
import 'api_client.dart';

class MissionService {
  final ApiClient _api;
  MissionService(this._api);

  Future<MissionRead> create({
    required String title,
    String? description,
    required Map<String, dynamic> rule,
    int points = 0,
    String? badgeIconUrl,
    bool active = true,
  }) async {
    final j = await _api.post('/missions', body: {
      'title': title,
      'description': ?description,
      'rule': rule,
      'points': points,
      'badge_icon_url': ?badgeIconUrl,
      'active': active,
    });
    return MissionRead.fromJson(j as Map<String, dynamic>);
  }

  Future<List<MissionRead>> list() async {
    final j = await _api.get('/missions');
    return (j as List)
        .map((e) => MissionRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<MissionProgress>> me(int userId) async {
    final j = await _api.get('/missions/me', query: {'user_id': userId});
    return (j as List)
        .map((e) => MissionProgress.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
