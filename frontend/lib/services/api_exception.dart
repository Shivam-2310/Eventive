/// Thrown by [ApiClient] for any non-2xx response or network failure.
///
/// The backend follows FastAPI conventions:
///   - `{"detail": "human string"}` for most errors, or
///   - `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` for 422.
///
/// [message] is the user-facing string extracted from [detail]. [statusCode]
/// is 0 for network / decode errors.
class ApiException implements Exception {
  final int statusCode;
  final String message;
  final dynamic detail;
  final Uri? uri;

  ApiException({
    required this.statusCode,
    required this.message,
    this.detail,
    this.uri,
  });

  /// Whether it is worth retrying this error. 4xx/validation errors are not.
  bool get retryable => statusCode == 0 || statusCode >= 500;

  @override
  String toString() =>
      'ApiException($statusCode ${uri?.path ?? ''}): $message';
}
