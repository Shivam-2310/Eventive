import '../models/interest.dart';
import 'api_client.dart';

class InterestService {
  final ApiClient _api;
  InterestService(this._api);

  Future<List<InterestRead>> list({String? category}) async {
    final j = await _api.get('/interests',
        query: category == null ? null : {'category': category});
    return (j as List)
        .map((e) => InterestRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<InterestRead> create(String label, {String category = 'topic'}) async {
    final j = await _api.post(
      '/interests',
      body: {'label': label, 'category': category},
    );
    return InterestRead.fromJson(j as Map<String, dynamic>);
  }

  Future<InterestRead> get(int interestId) async {
    final j = await _api.get('/interests/$interestId');
    return InterestRead.fromJson(j as Map<String, dynamic>);
  }
}
