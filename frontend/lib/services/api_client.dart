import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'api_exception.dart';

/// Centralized HTTP client for the Eventive backend.
///
/// - Base URL comes from `--dart-define=API_BASE_URL=...`, defaulting to
///   `http://localhost:8000`.
/// - Passing `--dart-define=API_BASE_URL=""` (as the production Docker image
///   does) puts the client in "same-origin" mode: HTTP requests use relative
///   URIs so the browser resolves them against the page origin, and WebSocket
///   URIs are derived from `Uri.base` at runtime (see [_httpToWs]).
/// - Attaches `Authorization: Bearer <access>` whenever [authTokenProvider]
///   returns a non-null value.
/// - On a 401 response, calls [refreshHandler] (once per request) and retries
///   the request with the new token. If refresh fails, the 401 is surfaced to
///   the caller as an [ApiException] so higher layers can force a sign-out.
class ApiClient {
  static const _defaultBaseUrl = 'http://localhost:8000';

  final String baseUrl;
  final String wsBaseUrl;
  final http.Client _client;

  /// Returns the current access token (or null if signed out).
  String? Function()? authTokenProvider;

  /// Attempts to refresh the access token. Returns true on success.
  Future<bool> Function()? refreshHandler;

  ApiClient({String? baseUrl, http.Client? client})
      : baseUrl = _resolveBaseUrl(baseUrl),
        wsBaseUrl = _httpToWs(_resolveBaseUrl(baseUrl)),
        _client = client ?? http.Client();

  static String _resolveBaseUrl(String? override) {
    if (override != null && override.isNotEmpty) return override;
    return const String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: _defaultBaseUrl,
    );
  }

  static String _httpToWs(String url) {
    if (url.startsWith('https://')) return url.replaceFirst('https://', 'wss://');
    if (url.startsWith('http://')) return url.replaceFirst('http://', 'ws://');
    // Same-origin build (API_BASE_URL=""): on Flutter web derive ws(s):// from
    // the current page location so WebSocketChannel receives an absolute URI.
    // Browsers technically accept relative WS URLs but support is inconsistent
    // across older engines, so we always hand it a fully-qualified one.
    if (kIsWeb && url.isEmpty) {
      final here = Uri.base;
      final scheme = here.scheme == 'https' ? 'wss' : 'ws';
      return '$scheme://${here.authority}';
    }
    return url;
  }

  Uri uri(String path, [Map<String, dynamic>? query]) {
    final cleanQuery = <String, String>{};
    if (query != null) {
      for (final entry in query.entries) {
        final v = entry.value;
        if (v == null) continue;
        cleanQuery[entry.key] = v.toString();
      }
    }
    return Uri.parse('$baseUrl$path').replace(
      queryParameters: cleanQuery.isEmpty ? null : cleanQuery,
    );
  }

  Uri wsUri(String path, [Map<String, dynamic>? query]) {
    final cleanQuery = <String, String>{};
    if (query != null) {
      for (final entry in query.entries) {
        final v = entry.value;
        if (v == null) continue;
        cleanQuery[entry.key] = v.toString();
      }
    }
    return Uri.parse('$wsBaseUrl$path').replace(
      queryParameters: cleanQuery.isEmpty ? null : cleanQuery,
    );
  }

  @visibleForTesting
  String get resolvedBaseUrl => baseUrl;

  Future<dynamic> get(String path, {Map<String, dynamic>? query, bool auth = true}) =>
      _send('GET', path, query: query, auth: auth);

  Future<dynamic> post(
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool auth = true,
  }) =>
      _send('POST', path, query: query, body: body, auth: auth);

  Future<dynamic> patch(
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool auth = true,
  }) =>
      _send('PATCH', path, query: query, body: body, auth: auth);

  Future<dynamic> put(
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool auth = true,
  }) =>
      _send('PUT', path, query: query, body: body, auth: auth);

  Future<dynamic> delete(String path, {Map<String, dynamic>? query, bool auth = true}) =>
      _send('DELETE', path, query: query, auth: auth);

  Future<dynamic> _send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool auth = true,
    bool didRefresh = false,
  }) async {
    final u = uri(path, query);
    final request = http.Request(method, u);
    request.headers['accept'] = 'application/json';
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    if (auth) {
      final token = authTokenProvider?.call();
      if (token != null && token.isNotEmpty) {
        request.headers['authorization'] = 'Bearer $token';
      }
    }
    http.StreamedResponse streamed;
    try {
      streamed = await _client.send(request);
    } catch (e) {
      throw ApiException(
        statusCode: 0,
        message: 'Network error: $e',
        uri: u,
      );
    }
    final resp = await http.Response.fromStream(streamed);
    if (auth && resp.statusCode == 401 && !didRefresh && refreshHandler != null) {
      final ok = await refreshHandler!();
      if (ok) {
        return _send(method, path, query: query, body: body, auth: auth, didRefresh: true);
      }
    }
    return _decode(resp, u);
  }

  Future<dynamic> uploadMultipart(
    String path, {
    Map<String, dynamic>? query,
    required String fileField,
    required List<int> bytes,
    required String filename,
    String? contentType,
    Map<String, String> fields = const {},
    bool auth = true,
    bool didRefresh = false,
  }) async {
    final u = uri(path, query);
    final request = http.MultipartRequest('POST', u);
    request.fields.addAll(fields);
    request.files.add(
      http.MultipartFile.fromBytes(
        fileField,
        bytes,
        filename: filename,
      ),
    );
    if (auth) {
      final token = authTokenProvider?.call();
      if (token != null && token.isNotEmpty) {
        request.headers['authorization'] = 'Bearer $token';
      }
    }
    http.StreamedResponse streamed;
    try {
      streamed = await _client.send(request);
    } catch (e) {
      throw ApiException(
        statusCode: 0,
        message: 'Upload failed: $e',
        uri: u,
      );
    }
    final resp = await http.Response.fromStream(streamed);
    if (auth && resp.statusCode == 401 && !didRefresh && refreshHandler != null) {
      final ok = await refreshHandler!();
      if (ok) {
        return uploadMultipart(
          path,
          query: query,
          fileField: fileField,
          bytes: bytes,
          filename: filename,
          contentType: contentType,
          fields: fields,
          auth: auth,
          didRefresh: true,
        );
      }
    }
    return _decode(resp, u);
  }

  Stream<Map<String, dynamic>> sseStreamPost(
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    bool auth = true,
  }) async* {
    final u = uri(path, query);
    final request = http.Request('POST', u);
    request.headers['accept'] = 'text/event-stream';
    request.headers['content-type'] = 'application/json';
    if (auth) {
      final token = authTokenProvider?.call();
      if (token != null && token.isNotEmpty) {
        request.headers['authorization'] = 'Bearer $token';
      }
    }
    if (body != null) request.body = jsonEncode(body);
    final http.StreamedResponse streamed;
    try {
      streamed = await _client.send(request);
    } catch (e) {
      throw ApiException(
        statusCode: 0,
        message: 'SSE network error: $e',
        uri: u,
      );
    }
    if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
      final bodyStr = await streamed.stream.bytesToString();
      throw _errorFromBody(streamed.statusCode, bodyStr, u);
    }

    final lines = streamed.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter());

    String? eventName;
    final dataBuf = StringBuffer();

    Map<String, dynamic> flush() {
      final rawData = dataBuf.toString();
      dynamic parsed;
      try {
        parsed = rawData.isEmpty ? null : jsonDecode(rawData);
      } catch (_) {
        parsed = rawData;
      }
      final frame = <String, dynamic>{
        'event': eventName ?? 'message',
        'data': parsed,
      };
      eventName = null;
      dataBuf.clear();
      return frame;
    }

    await for (final line in lines) {
      if (line.isEmpty) {
        if (dataBuf.isNotEmpty || eventName != null) {
          yield flush();
        }
        continue;
      }
      if (line.startsWith(':')) continue;
      if (line.startsWith('event:')) {
        eventName = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        if (dataBuf.isNotEmpty) dataBuf.write('\n');
        dataBuf.write(line.substring(5).trimLeft());
      }
    }
    if (dataBuf.isNotEmpty || eventName != null) {
      yield flush();
    }
  }

  dynamic _decode(http.Response resp, Uri u) {
    final status = resp.statusCode;
    final bodyStr = resp.body;
    if (status >= 200 && status < 300) {
      if (bodyStr.isEmpty) return null;
      try {
        return jsonDecode(bodyStr);
      } catch (e) {
        throw ApiException(
          statusCode: status,
          message: 'Failed to decode response: $e',
          uri: u,
        );
      }
    }
    throw _errorFromBody(status, bodyStr, u);
  }

  ApiException _errorFromBody(int status, String bodyStr, Uri u) {
    dynamic detail;
    String message;
    try {
      final parsed = jsonDecode(bodyStr);
      if (parsed is Map && parsed['detail'] != null) {
        detail = parsed['detail'];
        if (detail is String) {
          message = detail;
        } else if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] is String) {
            message = first['msg'] as String;
          } else {
            message = detail.toString();
          }
        } else {
          message = detail.toString();
        }
      } else {
        message = bodyStr;
      }
    } catch (_) {
      message = bodyStr.isEmpty ? 'HTTP $status' : bodyStr;
    }
    return ApiException(
      statusCode: status,
      message: message,
      detail: detail,
      uri: u,
    );
  }

  void close() => _client.close();
}
