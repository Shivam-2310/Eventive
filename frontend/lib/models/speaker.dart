import 'parse.dart';

/// Mirrors `SpeakerRead` from API_CONTRACT §6/20.2.
class SpeakerRead {
  final int id;
  final String name;
  final String? bio;
  final String? headshotUrl;
  final String? company;
  final String? title;
  final dynamic socialLinks;

  const SpeakerRead({
    required this.id,
    required this.name,
    this.bio,
    this.headshotUrl,
    this.company,
    this.title,
    this.socialLinks,
  });

  factory SpeakerRead.fromJson(Map<String, dynamic> j) => SpeakerRead(
        id: parseIntOr(j['id'], 0),
        name: parseString(j['name']) ?? '',
        bio: parseString(j['bio']),
        headshotUrl: parseString(j['headshot_url']),
        company: parseString(j['company']),
        title: parseString(j['title']),
        socialLinks: j['social_links'],
      );

  /// Flattens `social_links` into `{platform: url}` regardless of whether the
  /// backend stored it as a list or a map. Returns an empty map when absent.
  Map<String, String> get socialLinksMap {
    final links = <String, String>{};
    final raw = socialLinks;
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v != null) links[k.toString()] = v.toString();
      });
    } else if (raw is List) {
      for (var i = 0; i < raw.length; i++) {
        final item = raw[i];
        if (item is Map && item.containsKey('platform') && item['url'] != null) {
          links[item['platform'].toString()] = item['url'].toString();
        } else if (item is String) {
          links['link_${i + 1}'] = item;
        }
      }
    }
    return links;
  }
}
