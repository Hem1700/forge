import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/auth_api.dart';
import '../../core/api/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../../app.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  int _selectedIndex = 0;

  final _pages = const [
    _DashboardTab(),
    _EngagementsTab(),
    _FindingsTab(),
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
// Tab placeholders — each becomes its own file in Phase 2
// ---------------------------------------------------------------------------

class _DashboardTab extends StatelessWidget {
  const _DashboardTab();

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverAppBar(
          title: const Text('Dashboard'),
          floating: true,
          backgroundColor: ForgeColors.background,
          actions: [
            IconButton(
              icon: const Icon(Icons.notifications_outlined),
              onPressed: () {},
            ),
          ],
        ),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList(
            delegate: SliverChildListDelegate([
              _SummaryCard(
                label: 'Active Engagements',
                value: '—',
                icon: Icons.folder_open,
                color: ForgeColors.accent,
              ),
              const SizedBox(height: 12),
              _SummaryCard(
                label: 'Open Critical Findings',
                value: '—',
                icon: Icons.warning_amber_rounded,
                color: const Color(0xFFCF6679),
              ),
              const SizedBox(height: 12),
              _SummaryCard(
                label: 'Open High Findings',
                value: '—',
                icon: Icons.error_outline,
                color: const Color(0xFFE5A832),
              ),
              const SizedBox(height: 32),
              const Center(
                child: Text(
                  'Phase 2 — live data from server',
                  style: TextStyle(color: ForgeColors.textTertiary, fontSize: 13),
                ),
              ),
            ]),
          ),
        ),
      ],
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: ForgeColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: ForgeColors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(color: ForgeColors.textSecondary, fontSize: 13)),
                const SizedBox(height: 2),
                Text(value, style: const TextStyle(color: ForgeColors.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _EngagementsTab extends StatelessWidget {
  const _EngagementsTab();

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        const SliverAppBar(
          title: Text('Engagements'),
          floating: true,
          backgroundColor: ForgeColors.background,
        ),
        const SliverFillRemaining(
          child: Center(
            child: Text(
              'Phase 2 — engagement list',
              style: TextStyle(color: ForgeColors.textTertiary),
            ),
          ),
        ),
      ],
    );
  }
}

class _FindingsTab extends StatelessWidget {
  const _FindingsTab();

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        const SliverAppBar(
          title: Text('Findings'),
          floating: true,
          backgroundColor: ForgeColors.background,
        ),
        const SliverFillRemaining(
          child: Center(
            child: Text(
              'Phase 2 — findings list',
              style: TextStyle(color: ForgeColors.textTertiary),
            ),
          ),
        ),
      ],
    );
  }
}

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
