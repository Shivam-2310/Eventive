/// Shared JSON parsing helpers for models.
///
/// The backend uses `int` primary keys and ISO-8601 datetime strings that may
/// or may not carry a timezone suffix.  Everything is nullable-tolerant.
library;

int? parseInt(dynamic v) {
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  if (v is String) return int.tryParse(v);
  return null;
}

int parseIntOr(dynamic v, int fallback) => parseInt(v) ?? fallback;

double? parseDouble(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

String? parseString(dynamic v) {
  if (v == null) return null;
  return v.toString();
}

bool parseBool(dynamic v, {bool fallback = false}) {
  if (v == null) return fallback;
  if (v is bool) return v;
  if (v is num) return v != 0;
  if (v is String) {
    final s = v.toLowerCase();
    if (s == 'true' || s == '1' || s == 'yes') return true;
    if (s == 'false' || s == '0' || s == 'no') return false;
  }
  return fallback;
}

DateTime? parseDate(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v.toUtc();
  if (v is String && v.isNotEmpty) {
    final normalized = v.endsWith('Z') || v.contains('+') || v.contains('-', 10)
        ? v
        : '${v}Z';
    return DateTime.tryParse(normalized)?.toUtc();
  }
  return null;
}

List<T> parseList<T>(dynamic v, T Function(dynamic) fromJson) {
  if (v is! List) return const [];
  return v.map(fromJson).toList(growable: false);
}

List<String> parseStringList(dynamic v) {
  if (v is! List) return const [];
  return v.map((e) => e?.toString() ?? '').toList(growable: false);
}
