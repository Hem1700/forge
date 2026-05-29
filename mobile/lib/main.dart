import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'core/api/api_client.dart';
import 'core/storage/secure_storage.dart';
import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Hive.initFlutter();

  // Firebase init deferred to Phase 2 when google-services.json is added
  // await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);

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
