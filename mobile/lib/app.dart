import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme/app_theme.dart';
import 'core/storage/secure_storage.dart';
import 'features/auth/login_screen.dart';
import 'features/auth/register_screen.dart';
import 'features/engagements/engagement_detail_screen.dart';
import 'features/engagements/new_scan_screen.dart';
import 'features/findings/findings_screen.dart';
import 'features/home/home_screen.dart';
import 'features/onboarding/onboarding_screen.dart';

// ---------------------------------------------------------------------------
// Providers
// ---------------------------------------------------------------------------

enum AuthStatus { unknown, unauthenticated, authenticated }

class AuthNotifier extends ChangeNotifier {
  AuthStatus _status = AuthStatus.unknown;
  AuthStatus get status => _status;

  Future<void> checkAuth() async {
    final token = await SecureStorage.instance.getToken();
    final apiKey = await SecureStorage.instance.getApiKey();
    _status = (token != null || apiKey != null)
        ? AuthStatus.authenticated
        : AuthStatus.unauthenticated;
    notifyListeners();
  }

  void setAuthenticated() {
    _status = AuthStatus.authenticated;
    notifyListeners();
  }

  void setUnauthenticated() {
    _status = AuthStatus.unauthenticated;
    notifyListeners();
  }
}

final authNotifierProvider = ChangeNotifierProvider<AuthNotifier>((ref) {
  return AuthNotifier();
});

class ThemeNotifier extends StateNotifier<ThemeMode> {
  ThemeNotifier() : super(ThemeMode.dark) {
    _load();
  }

  Future<void> _load() async {
    final pref = await SecureStorage.instance.getDarkMode();
    state = switch (pref) {
      DarkModePreference.on => ThemeMode.dark,
      DarkModePreference.off => ThemeMode.light,
      DarkModePreference.system => ThemeMode.system,
    };
  }

  Future<void> setMode(DarkModePreference pref) async {
    await SecureStorage.instance.setDarkMode(pref);
    state = switch (pref) {
      DarkModePreference.on => ThemeMode.dark,
      DarkModePreference.off => ThemeMode.light,
      DarkModePreference.system => ThemeMode.system,
    };
  }
}

final themeModeProvider = StateNotifierProvider<ThemeNotifier, ThemeMode>((ref) {
  return ThemeNotifier();
});

// Holds initial route derived at startup (set in main.dart)
final initialRouteProvider = Provider<String>((ref) => '/onboarding');

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

GoRouter _buildRouter(WidgetRef ref, AuthNotifier authNotifier, String initialLocation) {
  return GoRouter(
    initialLocation: initialLocation,
    refreshListenable: authNotifier,
    redirect: (context, state) async {
      final serverUrl = await SecureStorage.instance.getServerUrl();
      final hasServer = serverUrl != null && serverUrl.isNotEmpty;

      if (!hasServer) {
        return state.matchedLocation == '/onboarding' ? null : '/onboarding';
      }

      final status = authNotifier.status;
      if (status == AuthStatus.unknown) return null;

      final onAuth = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register' ||
          state.matchedLocation == '/onboarding';
      if (status == AuthStatus.unauthenticated && !onAuth) return '/login';
      if (status == AuthStatus.authenticated && onAuth) return '/home';

      return null;
    },
    routes: [
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => const HomeScreen(),
      ),
      GoRoute(
        path: '/new-scan',
        builder: (context, state) => const NewScanScreen(),
      ),
      GoRoute(
        path: '/engagement/:id',
        builder: (context, state) => EngagementDetailScreen(
          engagementId: state.pathParameters['id']!,
        ),
        routes: [
          GoRoute(
            path: 'findings',
            builder: (context, state) => FindingsScreen(
              engagementId: state.pathParameters['id']!,
              targetUrl: state.extra as String?,
            ),
          ),
        ],
      ),
      GoRoute(
        path: '/settings',
        builder: (context, state) => const _SettingsPlaceholder(),
      ),
    ],
  );
}

// ---------------------------------------------------------------------------
// Root App widget
// ---------------------------------------------------------------------------

class ForgeApp extends ConsumerStatefulWidget {
  const ForgeApp({super.key, required this.initialRoute});
  final String initialRoute;

  @override
  ConsumerState<ForgeApp> createState() => _ForgeAppState();
}

class _ForgeAppState extends ConsumerState<ForgeApp> {
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    final authNotifier = ref.read(authNotifierProvider);
    _router = _buildRouter(ref, authNotifier, widget.initialRoute);
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp.router(
      title: 'FORGE',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      darkTheme: AppTheme.dark,
      themeMode: themeMode,
      routerConfig: _router,
    );
  }
}

// ---------------------------------------------------------------------------
// Placeholders
// ---------------------------------------------------------------------------

class _SettingsPlaceholder extends StatelessWidget {
  const _SettingsPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: const Center(child: Text('Phase 2 — Settings')),
    );
  }
}
