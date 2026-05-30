import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';
import '../../core/api/org_api.dart';
import '../../core/theme/app_theme.dart';

const _allRoles = ['viewer', 'analyst', 'admin', 'super_admin'];

class AdminScreen extends ConsumerStatefulWidget {
  const AdminScreen({super.key});

  @override
  ConsumerState<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends ConsumerState<AdminScreen> {
  final _api = OrgApi(ApiClient.instance);
  final _searchController = TextEditingController();

  List<OrgUser> _all = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _searchController.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final users = await _api.listAllUsers();
      if (!mounted) return;
      setState(() { _all = users; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  List<OrgUser> get _filtered {
    final q = _searchController.text.toLowerCase();
    if (q.isEmpty) return _all;
    return _all
        .where((u) =>
            u.email.toLowerCase().contains(q) ||
            (u.orgName?.toLowerCase().contains(q) ?? false))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final filtered = _filtered;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            const SliverAppBar(
              title: Text('Platform Admin'),
              floating: true,
            ),
            SliverPersistentHeader(
              pinned: true,
              delegate: _SearchBarDelegate(controller: _searchController),
            ),
            if (_loading)
              const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              SliverFillRemaining(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline,
                          color: ForgeColors.error, size: 48),
                      const SizedBox(height: 12),
                      Text(_error!,
                          style: TextStyle(
                              color: cs.onSurfaceVariant)),
                      const SizedBox(height: 16),
                      TextButton(onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                ),
              )
            else if (filtered.isEmpty)
              SliverFillRemaining(
                child: Center(
                  child: Text('No users found',
                      style: TextStyle(color: cs.onSurfaceVariant)),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (ctx, i) => _UserTile(
                      user: filtered[i],
                      onTap: () => _showUserSheet(context, filtered[i]),
                    ),
                    childCount: filtered.length,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _showUserSheet(BuildContext context, OrgUser user) {
    final cs = Theme.of(context).colorScheme;
    showModalBottomSheet(
      context: context,
      backgroundColor: cs.surface,
      isScrollControlled: true,
      shape: RoundedRectangleBorder(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        side: BorderSide(color: cs.outline),
      ),
      builder: (ctx) => _UserSheet(
        user: user,
        onRoleChanged: (role) async {
          Navigator.pop(ctx);
          await _changeRole(user, role);
        },
        onPlatformAdminToggle: () {
          Navigator.pop(ctx);
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                  'Platform admin flag must be managed via the backend CLI'),
            ),
          );
        },
      ),
    );
  }

  Future<void> _changeRole(OrgUser user, String role) async {
    try {
      final updated = await _api.setUserRole(user.id, role);
      setState(() {
        final idx = _all.indexWhere((u) => u.id == user.id);
        if (idx >= 0) _all = List.of(_all)..[idx] = updated;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${user.email} role set to $role')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('Failed: $e'),
              backgroundColor: ForgeColors.error),
        );
      }
    }
  }
}

// ── User tile ──────────────────────────────────────────────────────────────────

class _UserTile extends StatelessWidget {
  const _UserTile({required this.user, required this.onTap});
  final OrgUser user;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              _AdminAvatar(
                  initials: user.initials,
                  isPlatformAdmin: user.isPlatformAdmin),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            user.email,
                            style: TextStyle(
                                color: cs.onSurface,
                                fontWeight: FontWeight.w500,
                                fontSize: 14),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (user.isPlatformAdmin) ...[
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFFE5A832).withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text(
                              'PLATFORM',
                              style: TextStyle(
                                  color: Color(0xFFE5A832),
                                  fontSize: 9,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 0.5),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        _RoleBadgeSmall(role: user.role),
                        if (user.orgName != null) ...[
                          const SizedBox(width: 8),
                          Icon(Icons.business,
                              size: 11, color: cs.onSurfaceVariant),
                          const SizedBox(width: 3),
                          Expanded(
                            child: Text(
                              user.orgName!,
                              style: TextStyle(
                                  color: cs.onSurfaceVariant,
                                  fontSize: 12),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right,
                  size: 18, color: cs.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}

// ── User bottom sheet ─────────────────────────────────────────────────────────

class _UserSheet extends StatelessWidget {
  const _UserSheet({
    required this.user,
    required this.onRoleChanged,
    required this.onPlatformAdminToggle,
  });

  final OrgUser user;
  final ValueChanged<String> onRoleChanged;
  final VoidCallback onPlatformAdminToggle;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return DraggableScrollableSheet(
      initialChildSize: 0.6,
      minChildSize: 0.4,
      maxChildSize: 0.9,
      expand: false,
      builder: (ctx, scroll) => Column(
        children: [
          Container(
            width: 40,
            height: 4,
            margin: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: cs.outline,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: ListView(
              controller: scroll,
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
              children: [
                // User header
                Row(
                  children: [
                    _AdminAvatar(
                        initials: user.initials,
                        isPlatformAdmin: user.isPlatformAdmin,
                        radius: 24),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            user.email,
                            style: TextStyle(
                                color: cs.onSurface,
                                fontWeight: FontWeight.w600,
                                fontSize: 15),
                          ),
                          if (user.orgName != null)
                            Text(user.orgName!,
                                style: TextStyle(
                                    color: cs.onSurfaceVariant,
                                    fontSize: 13)),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                // Platform admin toggle (stub)
                Container(
                  decoration: BoxDecoration(
                    color: cs.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: cs.outline),
                  ),
                  child: ListTile(
                    leading: const Icon(Icons.admin_panel_settings_outlined,
                        color: ForgeColors.accent),
                    title: Text('Platform admin',
                        style: TextStyle(color: cs.onSurface)),
                    subtitle: Text('Grants access to this admin panel',
                        style: TextStyle(
                            color: cs.onSurfaceVariant, fontSize: 12)),
                    trailing: Switch(
                      value: user.isPlatformAdmin,
                      onChanged: (_) => onPlatformAdminToggle(),
                      activeThumbColor: ForgeColors.accent,
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'CHANGE ROLE',
                  style: TextStyle(
                    color: cs.onSurfaceVariant,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  decoration: BoxDecoration(
                    color: cs.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: cs.outline),
                  ),
                  child: ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _allRoles.length,
                    separatorBuilder: (_, _) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final r = _allRoles[i];
                      return ListTile(
                        title: Text(r,
                            style: TextStyle(
                                color: cs.onSurface)),
                        trailing: user.role == r
                            ? const Icon(Icons.check,
                                color: ForgeColors.accent)
                            : null,
                        onTap: () => onRoleChanged(r),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Shared helpers ─────────────────────────────────────────────────────────────

class _AdminAvatar extends StatelessWidget {
  const _AdminAvatar(
      {required this.initials, required this.isPlatformAdmin, this.radius = 18});
  final String initials;
  final bool isPlatformAdmin;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(
      backgroundColor:
          isPlatformAdmin ? const Color(0xFF3D2E00) : ForgeColors.accentDim,
      radius: radius,
      child: Text(
        initials,
        style: TextStyle(
          color: isPlatformAdmin
              ? const Color(0xFFE5A832)
              : ForgeColors.accent,
          fontWeight: FontWeight.w700,
          fontSize: radius * 0.65,
        ),
      ),
    );
  }
}

class _RoleBadgeSmall extends StatelessWidget {
  const _RoleBadgeSmall({required this.role});
  final String role;

  static Color _color(String role, Color fallback) => switch (role) {
        'super_admin' => const Color(0xFFE5A832),
        'admin' => ForgeColors.accent,
        'analyst' => ForgeColors.success,
        _ => fallback,
      };

  @override
  Widget build(BuildContext context) {
    final c = _color(role, Theme.of(context).colorScheme.onSurfaceVariant);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: c.withValues(alpha: 0.3)),
      ),
      child: Text(
        role,
        style: TextStyle(color: c, fontSize: 10, fontWeight: FontWeight.w600),
      ),
    );
  }
}

// ── Search bar persistent delegate ────────────────────────────────────────────

class _SearchBarDelegate extends SliverPersistentHeaderDelegate {
  _SearchBarDelegate({required this.controller});
  final TextEditingController controller;

  @override
  double get minExtent => 64;
  @override
  double get maxExtent => 64;

  @override
  Widget build(
      BuildContext context, double shrinkOffset, bool overlapsContent) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      color: cs.surface,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: TextField(
        controller: controller,
        style: TextStyle(color: cs.onSurface),
        decoration: InputDecoration(
          hintText: 'Search users or orgs…',
          prefixIcon: const Icon(Icons.search, size: 20),
          suffixIcon: controller.text.isNotEmpty
              ? IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: controller.clear,
                )
              : null,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        ),
      ),
    );
  }

  @override
  bool shouldRebuild(_SearchBarDelegate old) => old.controller != controller;
}
