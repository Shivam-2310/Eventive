import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'api_client.dart';

typedef WsFrame = Map<String, dynamic>;

/// Thin reconnect-with-backoff wrapper around a single WebSocket channel.
///
/// Emits **only** the app-level envelopes (§18) as decoded maps. Ping frames
/// are swallowed automatically. Errors bubble via [errors].
class ReconnectingWebSocket {
  final Uri uri;
  final Duration initialDelay;
  final Duration maxDelay;
  final bool logDebug;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  final _frameController = StreamController<WsFrame>.broadcast();
  final _errorController = StreamController<Object>.broadcast();
  bool _closed = false;
  int _retryAttempt = 0;
  Timer? _keepAliveTimer;

  ReconnectingWebSocket(
    this.uri, {
    this.initialDelay = const Duration(seconds: 1),
    this.maxDelay = const Duration(seconds: 30),
    this.logDebug = false,
  });

  /// Server-sent envelopes, one per `{channel, data}` frame. Ping frames are
  /// suppressed.
  Stream<WsFrame> get frames => _frameController.stream;
  Stream<Object> get errors => _errorController.stream;

  Future<void> connect() async {
    if (_closed) return;
    try {
      _channel = WebSocketChannel.connect(uri);
      _retryAttempt = 0;
      _startKeepAlive();
      _sub = _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
        cancelOnError: true,
      );
    } catch (e) {
      _onError(e);
    }
  }

  void _startKeepAlive() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      try {
        _channel?.sink.add('ping');
      } catch (_) {}
    });
  }

  void _onMessage(dynamic raw) {
    try {
      final text = raw is String ? raw : utf8.decode(raw as List<int>);
      final parsed = jsonDecode(text);
      if (parsed is Map<String, dynamic>) {
        if (parsed['channel'] == 'ping') return;
        _frameController.add(parsed);
      }
    } catch (e) {
      _errorController.add(e);
    }
  }

  void _onError(Object error) {
    _errorController.add(error);
    _scheduleReconnect();
  }

  void _onDone() {
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _keepAliveTimer?.cancel();
    _sub?.cancel();
    _sub = null;
    _channel = null;
    if (_closed) return;
    final attempts = _retryAttempt++;
    final delay = Duration(
      milliseconds: (initialDelay.inMilliseconds * (1 << attempts))
          .clamp(0, maxDelay.inMilliseconds),
    );
    Future.delayed(delay, connect);
  }

  Future<void> close() async {
    _closed = true;
    _keepAliveTimer?.cancel();
    try {
      await _sub?.cancel();
    } catch (_) {}
    try {
      await _channel?.sink.close(ws_status.normalClosure);
    } catch (_) {}
    if (!_frameController.isClosed) await _frameController.close();
    if (!_errorController.isClosed) await _errorController.close();
  }
}

/// Factories for the app's three end-user WebSocket channels (§18).
class WsService {
  final ApiClient _api;
  WsService(this._api);

  ReconnectingWebSocket chatSocket(int userId) => ReconnectingWebSocket(
        _api.wsUri('/ws/chat', {'user_id': userId}),
      );

  ReconnectingWebSocket notificationsSocket(int userId) => ReconnectingWebSocket(
        _api.wsUri('/ws/notifications', {'user_id': userId}),
      );

  ReconnectingWebSocket pulseSocket() => ReconnectingWebSocket(
        _api.wsUri('/ws/admin/pulse'),
      );
}
