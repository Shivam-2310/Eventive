import 'parse.dart';

/// Mirrors `InterestRead` from API_CONTRACT §5.
class InterestRead {
  final int id;
  final String label;
  final String slug;
  final String category;
  final bool isPredefined;

  const InterestRead({
    required this.id,
    required this.label,
    required this.slug,
    required this.category,
    required this.isPredefined,
  });

  factory InterestRead.fromJson(Map<String, dynamic> j) => InterestRead(
        id: parseIntOr(j['id'], 0),
        label: parseString(j['label']) ?? '',
        slug: parseString(j['slug']) ?? '',
        category: parseString(j['category']) ?? 'topic',
        isPredefined: parseBool(j['is_predefined']),
      );
}

/// The user's per-interest row from `GET /users/{id}/interests`.
class UserInterestRead {
  final int interestId;
  final String label;
  final String category;
  final double weight;
  final String source;

  const UserInterestRead({
    required this.interestId,
    required this.label,
    required this.category,
    required this.weight,
    required this.source,
  });

  factory UserInterestRead.fromJson(Map<String, dynamic> j) => UserInterestRead(
        interestId: parseIntOr(j['interest_id'], 0),
        label: parseString(j['label']) ?? '',
        category: parseString(j['category']) ?? 'topic',
        weight: parseDouble(j['weight']) ?? 1.0,
        source: parseString(j['source']) ?? 'self',
      );
}

const interestCategories = <String>[
  'topic',
  'language',
  'framework',
  'infra',
  'role',
  'domain',
];
