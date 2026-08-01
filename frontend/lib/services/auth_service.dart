import 'dart:async';

import '../models/auth.dart';
import '../models/user.dart';
import 'api_client.dart';
import 'session.dart';

/// Wraps `POST /auth/register|login|refresh|logout` and `GET /auth/me`.
///
/// Ties into [Session] so token pairs are persisted and every subsequent
/// [ApiClient] request automatically attaches the bearer token.
class AuthService {
  final ApiClient api;
  final Session session;

  /// Guard for a single in-flight refresh so parallel 401s don't storm the
  /// backend with duplicate refresh calls.
  Future<bool>? _pendingRefresh;

  AuthService(this.api, this.session);

  /// Wire the API client to read tokens from us and to trigger [refresh] on 401.
  void bind() {
    api.authTokenProvider = () => session.accessToken;
    api.refreshHandler = refresh;
  }

  Future<TokenPair> register({
    required String email,
    required String password,
    required String name,
    String? headline,
    String? company,
    String? role,
    String? timezone,
    String? blurb,
  }) async {
    final body = <String, dynamic>{
      'email': email.trim(),
      'password': password,
      'name': name.trim(),
      if (headline != null && headline.isNotEmpty) 'headline': headline,
      if (company != null && company.isNotEmpty) 'company': company,
      if (role != null && role.isNotEmpty) 'role': role,
      if (timezone != null && timezone.isNotEmpty) 'timezone': timezone,
      if (blurb != null && blurb.isNotEmpty) 'blurb': blurb,
    };
    final json = await api.post('/auth/register', body: body, auth: false);
    final pair = TokenPair.fromJson((json as Map).cast<String, dynamic>());
    await session.setTokens(
      accessToken: pair.accessToken,
      refreshToken: pair.refreshToken,
      user: pair.user,
    );
    return pair;
  }

  Future<TokenPair> login({required String email, required String password}) async {
    final json = await api.post(
      '/auth/login',
      body: {'email': email.trim(), 'password': password},
      auth: false,
    );
    final pair = TokenPair.fromJson((json as Map).cast<String, dynamic>());
    await session.setTokens(
      accessToken: pair.accessToken,
      refreshToken: pair.refreshToken,
      user: pair.user,
    );
    return pair;
  }

  Future<UserRead?> me() async {
    if (session.accessToken == null) return null;
    try {
      final json = await api.get('/auth/me');
      final user = UserRead.fromJson((json as Map).cast<String, dynamic>());
      await session.refreshUser(user);
      return user;
    } on Object {
      return null;
    }
  }

  Future<bool> refresh() {
    final pending = _pendingRefresh;
    if (pending != null) return pending;
    final f = _doRefresh();
    _pendingRefresh = f;
    f.whenComplete(() => _pendingRefresh = null);
    return f;
  }

  Future<bool> _doRefresh() async {
    final token = session.refreshToken;
    if (token == null || token.isEmpty) return false;
    try {
      final json = await api.post(
        '/auth/refresh',
        body: {'refresh_token': token},
        auth: false,
      );
      final pair = TokenPair.fromJson((json as Map).cast<String, dynamic>());
      await session.setTokens(
        accessToken: pair.accessToken,
        refreshToken: pair.refreshToken,
        user: pair.user,
      );
      return true;
    } catch (_) {
      await session.signOut();
      return false;
    }
  }

  Future<void> logout() async {
    final refreshToken = session.refreshToken;
    if (refreshToken != null && refreshToken.isNotEmpty) {
      try {
        await api.post(
          '/auth/logout',
          body: {'refresh_token': refreshToken},
          auth: false,
        );
      } catch (_) {
        // Server-side revocation failed — clear client-side session anyway.
      }
    }
    await session.signOut();
  }
}
