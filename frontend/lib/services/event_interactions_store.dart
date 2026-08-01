import 'package:flutter/foundation.dart';

import 'event_service.dart';

/// Canonical, app-wide store of the current user's event interactions.
///
/// The store exposes `Map<eventId, Set<type>>` and mutates optimistically so
/// every screen (Event Details sheet, Event Card, Discover, Profile activity
/// tabs, Search results, …) can read/write against the same source of truth.
/// Persistence lives in the backend — the store just caches the last known
/// state and re-hydrates on `refresh()`.
class EventInteractionsStore extends ChangeNotifier {
  static const knownTypes = <String>{
    'like',
    'save',
    'add_to_my_day',
    'mark_attended',
    'add_to_calendar',
    'rsvp',
  };

  final EventService _events;
  int? _userId;
  bool _loaded = false;
  bool _loading = false;
  Object? _error;
  final Map<int, Set<String>> _byEvent = <int, Set<String>>{};

  EventInteractionsStore(this._events);

  bool get isLoaded => _loaded;
  bool get isLoading => _loading;
  Object? get error => _error;

  /// Types active for the given event. Returns an *unmodifiable* view.
  Set<String> typesFor(int eventId) =>
      Set.unmodifiable(_byEvent[eventId] ?? const <String>{});

  bool isActive(int eventId, String type) =>
      _byEvent[eventId]?.contains(type) ?? false;

  /// Total event IDs the user has interacted with. Useful for empty-state
  /// heuristics on the Profile screen.
  Iterable<int> get touchedEventIds => List<int>.unmodifiable(_byEvent.keys);

  /// Reset when signing out or switching accounts.
  void clear() {
    _byEvent.clear();
    _loaded = false;
    _userId = null;
    _error = null;
    notifyListeners();
  }

  /// Hydrate from `GET /users/{id}/event-interactions`. Safe to call
  /// repeatedly — later calls just refresh the cache in place. Passing a
  /// different `userId` clears the previous user's state first.
  Future<void> refresh(int userId) async {
    if (_userId != null && _userId != userId) {
      _byEvent.clear();
      _loaded = false;
    }
    _userId = userId;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final fresh = await _events.userInteractionMap(userId);
      _byEvent
        ..clear()
        ..addAll(fresh);
      _loaded = true;
    } catch (e) {
      _error = e;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Optimistically flip `type` on/off for `eventId`, then persist. On
  /// failure the local state is rolled back and the error is rethrown so
  /// the caller can surface it via the standard snackbar helpers.
  Future<bool> toggle({
    required int userId,
    required int eventId,
    required String type,
  }) async {
    if (!knownTypes.contains(type)) {
      throw ArgumentError.value(type, 'type', 'unknown interaction type');
    }
    final active = isActive(eventId, type);
    _mutate(eventId, type, !active);
    try {
      if (active) {
        await _events.removeInteraction(eventId, userId: userId, type: type);
        return false;
      } else {
        await _events.interaction(eventId, userId: userId, type: type);
        return true;
      }
    } catch (e) {
      _mutate(eventId, type, active);
      rethrow;
    }
  }

  /// Force-set a specific state — used by non-toggle sites (e.g. the swipe
  /// deck's "like" gesture) so the store reflects the intent even when the
  /// user cannot see the sheet.
  Future<void> setActive({
    required int userId,
    required int eventId,
    required String type,
    required bool active,
  }) async {
    if (!knownTypes.contains(type)) {
      throw ArgumentError.value(type, 'type', 'unknown interaction type');
    }
    final was = isActive(eventId, type);
    if (was == active) return;
    _mutate(eventId, type, active);
    try {
      if (active) {
        await _events.interaction(eventId, userId: userId, type: type);
      } else {
        await _events.removeInteraction(eventId, userId: userId, type: type);
      }
    } catch (e) {
      _mutate(eventId, type, was);
      rethrow;
    }
  }

  void _mutate(int eventId, String type, bool active) {
    final set = _byEvent.putIfAbsent(eventId, () => <String>{});
    if (active) {
      set.add(type);
    } else {
      set.remove(type);
      if (set.isEmpty) _byEvent.remove(eventId);
    }
    notifyListeners();
  }
}
