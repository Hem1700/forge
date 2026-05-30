import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';
import '../api/auth_api.dart';
import '../models/user.dart';

class CurrentUserNotifier extends StateNotifier<User?> {
  CurrentUserNotifier() : super(null);

  Future<void> load() async {
    try {
      final user = await AuthApi(ApiClient.instance).me();
      state = user;
    } catch (_) {}
  }

  void set(User user) => state = user;
  void clear() => state = null;
}

final currentUserProvider =
    StateNotifierProvider<CurrentUserNotifier, User?>((ref) {
  final notifier = CurrentUserNotifier();
  notifier.load();
  return notifier;
});
