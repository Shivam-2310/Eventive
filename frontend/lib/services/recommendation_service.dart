import '../models/recommendation.dart';
import 'api_client.dart';

class RecommendationService {
  final ApiClient _api;
  RecommendationService(this._api);

  Future<List<PersonRecommendation>> people(int userId, {int limit = 20}) async {
    final j = await _api.get('/recommendations/people/$userId',
        query: {'limit': limit});
    return (j as List)
        .map((e) => PersonRecommendation.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<int> refreshPeople(int userId) async {
    final j = await _api.post('/recommendations/people/$userId/refresh');
    return (j as Map<String, dynamic>)['generated'] as int? ?? 0;
  }

  Future<List<EventRecommendation>> events(int userId, {int limit = 10}) async {
    final j = await _api.get('/recommendations/events/$userId',
        query: {'limit': limit});
    return (j as List)
        .map((e) => EventRecommendation.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
