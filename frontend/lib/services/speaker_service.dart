import '../models/speaker.dart';
import 'api_client.dart';

class SpeakerService {
  final ApiClient _api;
  SpeakerService(this._api);

  Future<List<SpeakerRead>> list() async {
    final j = await _api.get('/speakers');
    return (j as List)
        .map((e) => SpeakerRead.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<SpeakerRead> get(int id) async {
    final j = await _api.get('/speakers/$id');
    return SpeakerRead.fromJson(j as Map<String, dynamic>);
  }

  Future<SpeakerRead> create(Map<String, dynamic> body) async {
    final j = await _api.post('/speakers', body: body);
    return SpeakerRead.fromJson(j as Map<String, dynamic>);
  }

  Future<SpeakerRead> update(int id, Map<String, dynamic> body) async {
    final j = await _api.patch('/speakers/$id', body: body);
    return SpeakerRead.fromJson(j as Map<String, dynamic>);
  }

  Future<void> delete(int id) async {
    await _api.delete('/speakers/$id');
  }
}
