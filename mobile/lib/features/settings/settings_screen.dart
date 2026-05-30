import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../app.dart';
import '../../core/api/api_client.dart';
import '../../core/api/auth_api.dart';
import '../../core/models/user.dart';
import '../../core/providers/user_provider.dart';
import '../../core/storage/secure_storage.dart';
import '../../core/theme/app_theme.dart';

// ── Notification preference keys ──────────────────────────────────────────────
const _kNotifCritical = 'notif_critical_findings';
const _kNotifScanComplete = 'notif_scan_complete';
const _kNotifBudget = 'notif_budget_warnings';
const _kNotifTeam = 'notif_team_activity';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  // Notification toggles
  bool _notifCritical = true;
  bool _notifScanComplete = true;
  bool _notifBudget = false;
  bool _notifTeam = false;

  // Security
  bool _biometricEnabled = false;

  // Dark mode (mirrors ThemeNotifier state)
  DarkModePreference _darkMode = DarkModePreference.system;

  bool _prefsLoaded = false;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final dm = await SecureStorage.instance.getDarkMode();
    final bio = await SecureStorage.instance.getBiometricEnabled();
    if (!mounted) return;
    setState(() {
      _notifCritical = prefs.getBool(_kNotifCritical) ?? true;
      _notifScanComplete = prefs.getBool(_kNotifScanComplete) ?? true;
      _notifBudget = prefs.getBool(_kNotifBudget) ?? false;
      _notifTeam = prefs.getBool(_kNotifTeam) ?? false;
      _biometricEnabled = bio;
      _darkMode = dm;
      _prefsLoaded = true;
    });
  }

  Future<void> _setNotif(String key, bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(key, value);
  }

  Future<void> _setDarkMode(DarkModePreference pref) async {
    setState(() => _darkMode = pref);
    await ref.read(themeModeProvider.notifier).setMode(pref);
  }

  Future<void> _signOut() async {
    final authApi = AuthApi(ApiClient.instance);
    await authApi.logout();
    ref.read(currentUserProvider.notifier).clear();
    ref.read(authNotifierProvider).setUnauthenticated();
    if (mounted) context.go('/login');
  }

  Future<void> _changeServer() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Change server'),
        content: const Text(
          'This will clear your saved server URL and credentials, and return you to the setup screen.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Continue', style: TextStyle(color: ForgeColors.error)),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    await SecureStorage.instance.clearAll();
    ref.read(currentUserProvider.notifier).clear();
    ref.read(authNotifierProvider).setUnauthenticated();
    if (mounted) context.go('/onboarding');
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider);

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          const SliverAppBar(
            title: Text('Settings'),
            floating: true,
          ),
          if (!_prefsLoaded)
            const SliverFillRemaining(
              child: Center(child: CircularProgressIndicator()),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  _buildSection('Account', [
                    _AccountTile(user: user),
                    const Divider(height: 1),
                    ListTile(
                      leading: const Icon(Icons.business_outlined),
                      title: Text(user?.organization ?? 'My organization'),
                      trailing: const Icon(Icons.chevron_right, size: 20),
                      onTap: () => context.go('/home'),
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSection('Appearance', [
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      child: Row(
                        children: [
                          Icon(Icons.dark_mode_outlined,
                              color: Theme.of(context).colorScheme.onSurfaceVariant),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Text('Dark mode',
                                style: TextStyle(color: Theme.of(context).colorScheme.onSurface)),
                          ),
                          _DarkModeSegment(
                            value: _darkMode,
                            onChanged: _setDarkMode,
                          ),
                        ],
                      ),
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSection('Notifications', [
                    _NotifTile(
                      icon: Icons.warning_amber_outlined,
                      label: 'Critical findings',
                      value: _notifCritical,
                      onChanged: (v) {
                        setState(() => _notifCritical = v);
                        _setNotif(_kNotifCritical, v);
                      },
                    ),
                    const Divider(height: 1),
                    _NotifTile(
                      icon: Icons.radar_outlined,
                      label: 'Scan complete / failed',
                      value: _notifScanComplete,
                      onChanged: (v) {
                        setState(() => _notifScanComplete = v);
                        _setNotif(_kNotifScanComplete, v);
                      },
                    ),
                    const Divider(height: 1),
                    _NotifTile(
                      icon: Icons.account_balance_wallet_outlined,
                      label: 'Budget warnings',
                      value: _notifBudget,
                      onChanged: (v) {
                        setState(() => _notifBudget = v);
                        _setNotif(_kNotifBudget, v);
                      },
                    ),
                    const Divider(height: 1),
                    _NotifTile(
                      icon: Icons.group_outlined,
                      label: 'Team activity',
                      value: _notifTeam,
                      onChanged: (v) {
                        setState(() => _notifTeam = v);
                        _setNotif(_kNotifTeam, v);
                      },
                    ),
                  ]),
                  const SizedBox(height: 24),
                  _buildSection('Security', [
                    _NotifTile(
                      icon: Icons.fingerprint,
                      label: 'Biometric login',
                      value: _biometricEnabled,
                      onChanged: (v) async {
                        setState(() => _biometricEnabled = v);
                        await SecureStorage.instance.setBiometricEnabled(v);
                      },
                    ),
                    const Divider(height: 1),
                    ListTile(
                      leading: const Icon(Icons.dns_outlined),
                      title: const Text('Change server'),
                      trailing: const Icon(Icons.chevron_right, size: 20),
                      onTap: _changeServer,
                    ),
                  ]),
                  if (user?.isPlatformAdmin == true) ...[
                    const SizedBox(height: 24),
                    _buildSection('Platform', [
                      ListTile(
                        leading: const Icon(Icons.admin_panel_settings_outlined,
                            color: ForgeColors.accent),
                        title: const Text('Platform admin',
                            style: TextStyle(color: ForgeColors.accent)),
                        trailing: const Icon(Icons.chevron_right, size: 20,
                            color: ForgeColors.accent),
                        onTap: () => context.push('/admin'),
                      ),
                    ]),
                  ],
                  const SizedBox(height: 32),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: OutlinedButton.icon(
                      onPressed: _signOut,
                      icon: const Icon(Icons.logout, size: 18),
                      label: const Text('Sign out'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: ForgeColors.error,
                        side: const BorderSide(color: ForgeColors.error),
                        minimumSize: const Size(double.infinity, 50),
                      ),
                    ),
                  ),
                ]),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildSection(String title, List<Widget> children) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(
            title,
            style: TextStyle(
              color: cs.onSurfaceVariant,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.5,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: cs.outline),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }
}

// ── Account tile ──────────────────────────────────────────────────────────────

class _AccountTile extends StatelessWidget {
  const _AccountTile({required this.user});
  final User? user;

  @override
  Widget build(BuildContext context) {
    final name = user?.name ?? '—';
    final email = user?.email ?? '—';
    final initials = user?.initials ?? '?';

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: CircleAvatar(
        backgroundColor: ForgeColors.accent,
        radius: 22,
        child: Text(
          initials,
          style: const TextStyle(
            color: ForgeColors.background,
            fontWeight: FontWeight.w700,
            fontSize: 16,
          ),
        ),
      ),
      title: Text(name,
          style: TextStyle(
              color: Theme.of(context).colorScheme.onSurface, fontWeight: FontWeight.w600)),
      subtitle: Text(email,
          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant, fontSize: 13)),
      trailing: const Icon(Icons.chevron_right, size: 20),
      onTap: () => _showEditProfileStub(context),
    );
  }

  void _showEditProfileStub(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Edit profile — coming soon')),
    );
  }
}

// ── Notification toggle row ───────────────────────────────────────────────────

class _NotifTile extends StatelessWidget {
  const _NotifTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final IconData icon;
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ListTile(
      leading: Icon(icon, color: cs.onSurfaceVariant),
      title: Text(label, style: TextStyle(color: cs.onSurface)),
      trailing: Switch(
        value: value,
        onChanged: onChanged,
        activeThumbColor: cs.primary,
      ),
    );
  }
}

// ── 3-segment dark mode control ───────────────────────────────────────────────

class _DarkModeSegment extends StatelessWidget {
  const _DarkModeSegment({required this.value, required this.onChanged});

  final DarkModePreference value;
  final ValueChanged<DarkModePreference> onChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SegmentedButton<DarkModePreference>(
      style: SegmentedButton.styleFrom(
        backgroundColor: cs.surfaceContainerHighest,
        foregroundColor: cs.onSurfaceVariant,
        selectedForegroundColor: cs.primary,
        selectedBackgroundColor: cs.primaryContainer,
        side: BorderSide(color: cs.outline),
        textStyle: const TextStyle(fontSize: 12),
        padding: const EdgeInsets.symmetric(horizontal: 10),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        visualDensity: VisualDensity.compact,
      ),
      showSelectedIcon: false,
      segments: const [
        ButtonSegment(value: DarkModePreference.system, label: Text('System')),
        ButtonSegment(value: DarkModePreference.on, label: Text('On')),
        ButtonSegment(value: DarkModePreference.off, label: Text('Off')),
      ],
      selected: {value},
      onSelectionChanged: (s) => onChanged(s.first),
    );
  }
}
