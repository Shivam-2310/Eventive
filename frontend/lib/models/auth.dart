import 'parse.dart';
import 'user.dart';

class TokenPair {
  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;
  final UserRead user;

  const TokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.tokenType,
    required this.expiresIn,
    required this.user,
  });

  factory TokenPair.fromJson(Map<String, dynamic> json) {
    return TokenPair(
      accessToken: parseString(json['access_token']) ?? '',
      refreshToken: parseString(json['refresh_token']) ?? '',
      tokenType: parseString(json['token_type']) ?? 'bearer',
      expiresIn: parseInt(json['expires_in']) ?? 0,
      user: UserRead.fromJson(
        (json['user'] as Map).cast<String, dynamic>(),
      ),
    );
  }
}
