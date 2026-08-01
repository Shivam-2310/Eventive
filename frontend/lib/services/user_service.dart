import '../models/interest.dart';
import '../models/user.dart';
import 'api_client.dart';

/// Wraps the `/users` and `/users/{id}/*` endpoints (§4).
class UserService {
  final ApiClient _api;
  UserService(this._api);

  Future<UserRead> create(UserCreate body) async {
    final j = await _api.post('/users', body: body.toJson());
    return UserRead.fromJson(j as Map<String, dynamic>);
  }

  Future<List<UserRead>> list({int limit = 100, int offset = 0}) async {
    final j = await _api.get('/users', query: {'limit': limit, 'offset': offset});
    return (j as List)
        .map((e) => UserRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<UserRead> get(int userId) async {
    final j = await _api.get('/users/$userId');
    return UserRead.fromJson(j as Map<String, dynamic>);
  }

  Future<UserRead> update(int userId, UserUpdate body) async {
    final j = await _api.patch('/users/$userId', body: body.toJson());
    return UserRead.fromJson(j as Map<String, dynamic>);
  }

  Future<void> delete(int userId) async {
    await _api.delete('/users/$userId');
  }

  Future<int> setInterests(int userId, List<int> interestIds, {String? blurb}) async {
    final j = await _api.put(
      '/users/$userId/interests',
      body: {
        'interest_ids': interestIds,
        'blurb': ?blurb,
      },
    );
    return (j as Map<String, dynamic>)['count'] as int? ?? 0;
  }

  Future<List<UserInterestRead>> listInterests(int userId) async {
    final j = await _api.get('/users/$userId/interests');
    return (j as List)
        .map((e) => UserInterestRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<UserWrapped> wrapped(int userId) async {
    final j = await _api.get('/users/$userId/wrapped');
    return UserWrapped.fromJson(j as Map<String, dynamic>);
  }
}
