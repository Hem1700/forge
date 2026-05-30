import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'core/api/api_client.dart';
import 'core/notifications/notification_service.dart';
import 'core/storage/secure_storage.dart';
import 'app.dart';

// Top-level FCM background handler — must be a non-anonymous top-level function.
@pragma('vm:entry-point')
Future<void> _fcmBackgroundHandler(RemoteMessage message) async {
  debugPrint('FCM background message: ${message.messageId}');
}

Future<void> _setupFCM() async {
  FirebaseMessaging.onBackgroundMessage(_fcmBackgroundHandler);
  await NotificationService.instance.setup();
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Hive.initFlutter();

  // Local notifications don't require Firebase; init unconditionally.
  await NotificationService.instance.initLocalNotifications();

  // Firebase + FCM: gracefully skip if google-services.json / GoogleService-Info.plist absent.
  try {
    await Firebase.initializeApp();
    await _setupFCM();
  } catch (e) {
    debugPrint('Firebase not configured: $e');
  }

  final serverUrl = await SecureStorage.instance.getServerUrl();
  final hasServer = serverUrl != null && serverUrl.isNotEmpty;

  String initialRoute;
  if (!hasServer) {
    initialRoute = '/onboarding';
  } else {
    await ApiClient.instance.init(serverUrl);
    final token = await SecureStorage.instance.getToken();
    final apiKey = await SecureStorage.instance.getApiKey();
    initialRoute = (token != null || apiKey != null) ? '/home' : '/login';
  }

  runApp(ProviderScope(child: _Bootstrap(initialRoute: initialRoute)));
}

class _Bootstrap extends ConsumerWidget {
  const _Bootstrap({required this.initialRoute});
  final String initialRoute;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authNotifier = ref.read(authNotifierProvider);
    if (authNotifier.status == AuthStatus.unknown) {
      authNotifier.checkAuth();
    }
    return ForgeApp(initialRoute: initialRoute);
  }
}
