import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/auth_api.dart';
import '../../core/api/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../../app.dart';
import 'dashboard_screen.dart';
import '../engagements/engagements_screen.dart';
import '../findings/findings_screen.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _selectedIndex = 0;

  final _pages = const [
    DashboardScreen(),
    EngagementsScreen(),
    AllFindingsTab(),
    _ProfileTab(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ForgeColors.background,
      body: IndexedStack(index: _selectedIndex, children: _pages),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: ForgeColors.surface,
          border: Border(top: BorderSide(color: ForgeColors.border)),
        ),
        child: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: (i) => setState(() => _selectedIndex = i),
          backgroundColor: ForgeColors.surface,
          surfaceTintColor: Colors.transparent,
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.dashboard_outlined),
              selectedIcon: Icon(Icons.dashboard),
              label: 'Dashboard',
            ),
            NavigationDestination(
              icon: Icon(Icons.folder_outlined),
              selectedIcon: Icon(Icons.folder),
              label: 'Engagements',
            ),
            NavigationDestination(
              icon: Icon(Icons.bug_report_outlined),
              selectedIcon: Icon(Icons.bug_report),
              label: 'Findings',
            ),
            NavigationDestination(
              icon: Icon(Icons.person_outlined),
              selectedIcon: Icon(Icons.person),
              label: 'Profile',
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Profile tab
// ---------------------------------------------------------------------------

class _ProfileTab extends ConsumerWidget {
  const _ProfileTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return CustomScrollView(
      slivers: [
        const SliverAppBar(
          title: Text('Profile'),
          floating: true,
          backgroundColor: ForgeColors.background,
        ),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              ListTile(
                leading: const Icon(Icons.settings_outlined),
                title: const Text('Settings'),
                trailing: const Icon(Icons.chevron_right, size: 20),
                onTap: () => context.push('/settings'),
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.logout, color: ForgeColors.error),
                title: const Text('Sign out', style: TextStyle(color: ForgeColors.error)),
                onTap: () async {
                  final authApi = AuthApi(ApiClient.instance);
                  await authApi.logout();
                  ref.read(authNotifierProvider).setUnauthenticated();
                  if (context.mounted) context.go('/login');
                },
              ),
            ]),
          ),
        ),
      ],
    );
  }
}
