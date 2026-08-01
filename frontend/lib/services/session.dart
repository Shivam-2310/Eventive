import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/user.dart';

/// Holds the current user + auth tokens for the whole app.
///
/// Persisted to `SharedPreferences` — survives browser reloads / cold starts.
class Session extends ChangeNotifier {
  static const _kUserIdKey = 'flo.user_id';
  static const _kAdminModeKey = 'flo.admin_mode';
  static const _kAccessTokenKey = 'flo.access_token';
  static const _kRefreshTokenKey = 'flo.refresh_token';

  int? _userId;
  UserRead? _user;
  bool _adminMode = false;
  String? _accessToken;
  String? _refreshToken;

  int? get userId => _userId;
  UserRead? get user => _user;
  bool get isAuthenticated => _userId != null && _accessToken != null;
  bool get adminMode => _adminMode;
  String? get accessToken => _accessToken;
  String? get refreshToken => _refreshToken;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _userId = prefs.getInt(_kUserIdKey);
    _adminMode = prefs.getBool(_kAdminModeKey) ?? false;
    _accessToken = prefs.getString(_kAccessTokenKey);
    _refreshToken = prefs.getString(_kRefreshTokenKey);
    notifyListeners();
  }

  Future<void> setTokens({
    required String accessToken,
    required String refreshToken,
    required UserRead user,
  }) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    _user = user;
    _userId = user.id;
    if (user.isAdmin) _adminMode = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAccessTokenKey, accessToken);
    await prefs.setString(_kRefreshTokenKey, refreshToken);
    await prefs.setInt(_kUserIdKey, user.id);
    notifyListeners();
  }

  Future<void> updateAccessToken(String accessToken, {String? refreshToken}) async {
    _accessToken = accessToken;
    if (refreshToken != null) _refreshToken = refreshToken;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kAccessTokenKey, accessToken);
    if (refreshToken != null) {
      await prefs.setString(_kRefreshTokenKey, refreshToken);
    }
    notifyListeners();
  }

  Future<void> setUser(UserRead user) async {
    _user = user;
    _userId = user.id;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_kUserIdKey, user.id);
    if (user.isAdmin) _adminMode = true;
    notifyListeners();
  }

  Future<void> refreshUser(UserRead user) async {
    _user = user;
    notifyListeners();
  }

  Future<void> setAdminMode(bool value) async {
    _adminMode = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kAdminModeKey, value);
    notifyListeners();
  }

  Future<void> signOut() async {
    _userId = null;
    _user = null;
    _adminMode = false;
    _accessToken = null;
    _refreshToken = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUserIdKey);
    await prefs.remove(_kAdminModeKey);
    await prefs.remove(_kAccessTokenKey);
    await prefs.remove(_kRefreshTokenKey);
    notifyListeners();
  }
}
