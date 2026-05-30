import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';
import '../../core/api/org_api.dart';
import '../../core/models/user.dart';
import '../../core/providers/user_provider.dart';
import '../../core/theme/app_theme.dart';

const _roles = ['viewer', 'analyst', 'admin', 'super_admin'];

class OrgScreen extends ConsumerStatefulWidget {
  const OrgScreen({super.key});

  @override
  ConsumerState<OrgScreen> createState() => _OrgScreenState();
}

class _OrgScreenState extends ConsumerState<OrgScreen> {
  final _api = OrgApi(ApiClient.instance);

  List<OrgUser> _members = [];
  bool _loading = true;
  String? _error;

  Map<String, dynamic> _usage = {};
  Map<String, dynamic> _budget = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        _api.listUsers(),
        _api.getUsage(),
        _api.getBudget(),
      ]);
      if (!mounted) return;
      setState(() {
        _members = results[0] as List<OrgUser>;
        _usage = results[1] as Map<String, dynamic>;
        _budget = results[2] as Map<String, dynamic>;
        _loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final currentUser = ref.watch(currentUserProvider);
    final canManage = currentUser?.isAdmin ?? false;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              title: Text(
                currentUser?.organization ?? 'Organization',
                style: TextStyle(color: cs.onSurface),
              ),
              floating: true,
              bottom: PreferredSize(
                preferredSize: const Size.fromHeight(1),
                child: Container(height: 1, color: cs.outline),
              ),
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
                          style: TextStyle(color: cs.onSurfaceVariant)),
                      const SizedBox(height: 16),
                      TextButton(onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    // Members header
                    _SectionHeader(
                      title: 'Members',
                      trailing: Text(
                        '${_members.length}',
                        style: const TextStyle(
                          color: ForgeColors.accent,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    _MembersList(
                      members: _members,
                      currentUser: currentUser,
                      canManage: canManage,
                      onRoleChanged: (user, role) => _changeRole(user, role),
                    ),
                    const SizedBox(height: 24),
                    // LLM usage section
                    const _SectionHeader(title: 'LLM Usage'),
                    const SizedBox(height: 8),
                    _LlmUsageCard(usage: _usage, budget: _budget),
                  ]),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: canManage
          ? FloatingActionButton(
              onPressed: _showInviteDialog,
              backgroundColor: ForgeColors.accent,
              foregroundColor: cs.onPrimary,
              child: const Icon(Icons.person_add),
            )
          : null,
    );
  }

  Future<void> _changeRole(OrgUser target, String role) async {
    try {
      final updated = await _api.updateUserRole(target.id, role);
      setState(() {
        final idx = _members.indexWhere((m) => m.id == target.id);
        if (idx >= 0) {
          _members = List.of(_members)..[idx] = updated;
        }
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${target.email} role updated to $role')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e'),
              backgroundColor: ForgeColors.error),
        );
      }
    }
  }

  Future<void> _showInviteDialog() async {
    final messenger = ScaffoldMessenger.of(context);
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => _InviteDialog(
        initialRole: 'viewer',
        onSubmit: (role) async {
          final data = await _api.invite(role);
          return data['invite_url'] as String? ?? '';
        },
      ),
    );
    if (result == null) return;
    await Clipboard.setData(ClipboardData(text: result));
    messenger.showSnackBar(
      const SnackBar(content: Text('Invite link copied to clipboard')),
    );
  }
}

// ── Members list ──────────────────────────────────────────────────────────────

class _MembersList extends StatelessWidget {
  const _MembersList({
    required this.members,
    required this.currentUser,
    required this.canManage,
    required this.onRoleChanged,
  });

  final List<OrgUser> members;
  final User? currentUser;
  final bool canManage;
  final void Function(OrgUser, String) onRoleChanged;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (members.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: cs.outline),
        ),
        child: Center(
          child: Text('No members found',
              style: TextStyle(color: cs.onSurfaceVariant)),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: cs.outline),
      ),
      child: ListView.separated(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: members.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (ctx, i) {
          final m = members[i];
          final isSelf = m.id == currentUser?.id;
          return ListTile(
            leading: _AvatarCircle(initials: m.initials),
            title: Text(
              m.displayName,
              style: TextStyle(
                  color: cs.onSurface, fontWeight: FontWeight.w500),
            ),
            subtitle: Text(m.email,
                style: TextStyle(
                    color: cs.onSurfaceVariant, fontSize: 12)),
            trailing: _RoleBadge(role: m.role),
            onLongPress: (canManage && !isSelf)
                ? () => _showRoleSheet(ctx, m)
                : null,
          );
        },
      ),
    );
  }

  void _showRoleSheet(BuildContext context, OrgUser member) {
    final cs = Theme.of(context).colorScheme;
    showModalBottomSheet(
      context: context,
      backgroundColor: cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        side: BorderSide(color: cs.outline),
      ),
      builder: (ctx) => _RoleSheet(
        member: member,
        onRoleSelected: (role) {
          Navigator.pop(ctx);
          onRoleChanged(member, role);
        },
      ),
    );
  }
}

class _RoleSheet extends StatelessWidget {
  const _RoleSheet({required this.member, required this.onRoleSelected});
  final OrgUser member;
  final ValueChanged<String> onRoleSelected;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Change role — ${member.email}',
            style: TextStyle(
                color: cs.onSurface,
                fontWeight: FontWeight.w600,
                fontSize: 16),
          ),
          const SizedBox(height: 16),
          ..._roles.map((role) => ListTile(
                leading: _RoleBadge(role: role),
                title: Text(role,
                    style: TextStyle(color: cs.onSurface)),
                trailing: member.role == role
                    ? const Icon(Icons.check, color: ForgeColors.accent)
                    : null,
                onTap: () => onRoleSelected(role),
              )),
        ],
      ),
    );
  }
}

// ── LLM Usage card ────────────────────────────────────────────────────────────

class _LlmUsageCard extends StatelessWidget {
  const _LlmUsageCard({required this.usage, required this.budget});
  final Map<String, dynamic> usage;
  final Map<String, dynamic> budget;

  @override
  Widget build(BuildContext context) {
    final rows = (usage['rows'] as List<dynamic>? ?? [])
        .cast<Map<String, dynamic>>()
        .map(LlmUsageRow.fromJson)
        .toList()
      ..sort((a, b) => b.totalTokens.compareTo(a.totalTokens));

    final totalCost = (usage['total_cost_usd'] as num?)?.toDouble() ?? 0.0;
    final hasBudget = budget['configured'] == true;
    final budgetLimit =
        (budget['monthly_limit_usd'] as num?)?.toDouble() ?? 0.0;
    final budgetUsed =
        (budget['current_spend_usd'] as num?)?.toDouble() ?? totalCost;
    final pctUsed = hasBudget && budgetLimit > 0
        ? (budgetUsed / budgetLimit).clamp(0.0, 1.0)
        : 0.0;

    final maxTokens = rows.isEmpty
        ? 1
        : rows.map((r) => r.totalTokens).reduce((a, b) => a > b ? a : b);

    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: cs.outline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Budget bar
          if (hasBudget) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Monthly budget',
                    style: TextStyle(
                        color: cs.onSurfaceVariant, fontSize: 13)),
                Text(
                  '\$${budgetUsed.toStringAsFixed(2)} / \$${budgetLimit.toStringAsFixed(2)}',
                  style: TextStyle(
                      color: cs.onSurface,
                      fontWeight: FontWeight.w600,
                      fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _BarFill(
              fraction: pctUsed,
              color: pctUsed > 0.8 ? ForgeColors.error : ForgeColors.accent,
              height: 8,
            ),
            const SizedBox(height: 16),
          ] else ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Total cost (all time)',
                    style: TextStyle(
                        color: cs.onSurfaceVariant, fontSize: 13)),
                Text(
                  '\$${totalCost.toStringAsFixed(4)}',
                  style: TextStyle(
                      color: cs.onSurface,
                      fontWeight: FontWeight.w600,
                      fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          // Task breakdown
          if (rows.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text('No usage data',
                    style: TextStyle(color: cs.onSurfaceVariant)),
              ),
            )
          else ...[
            Text('Top tasks by token usage',
                style: TextStyle(
                    color: cs.onSurfaceVariant,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.4)),
            const SizedBox(height: 10),
            ...rows.take(6).map((r) => _TaskUsageRow(
                  row: r,
                  maxTokens: maxTokens,
                )),
          ],
        ],
      ),
    );
  }
}

class _TaskUsageRow extends StatelessWidget {
  const _TaskUsageRow({required this.row, required this.maxTokens});
  final LlmUsageRow row;
  final int maxTokens;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fraction = maxTokens > 0 ? row.totalTokens / maxTokens : 0.0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  row.task.replaceAll('_', ' '),
                  style: TextStyle(
                      color: cs.onSurface, fontSize: 13),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                '${_formatTokens(row.totalTokens)} tokens',
                style: TextStyle(
                    color: cs.onSurfaceVariant, fontSize: 12),
              ),
            ],
          ),
          const SizedBox(height: 4),
          _BarFill(fraction: fraction, color: ForgeColors.accentMid, height: 5),
        ],
      ),
    );
  }

  String _formatTokens(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}K';
    return n.toString();
  }
}

class _BarFill extends StatelessWidget {
  const _BarFill(
      {required this.fraction, required this.color, this.height = 6});
  final double fraction;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return LayoutBuilder(builder: (ctx, constraints) {
      return Container(
        height: height,
        decoration: BoxDecoration(
          color: cs.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(4),
        ),
        child: FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: fraction.clamp(0.0, 1.0),
          child: Container(
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        ),
      );
    });
  }
}

// ── Invite dialog ─────────────────────────────────────────────────────────────

class _InviteDialog extends StatefulWidget {
  const _InviteDialog({required this.initialRole, required this.onSubmit});
  final String initialRole;
  final Future<String> Function(String role) onSubmit;

  @override
  State<_InviteDialog> createState() => _InviteDialogState();
}

class _InviteDialogState extends State<_InviteDialog> {
  late String _role;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _role = widget.initialRole;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Invite member'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Select a role for the invite link. Anyone with the link can join your org.',
            style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: _role,
            dropdownColor: cs.surfaceContainerHighest,
            decoration: const InputDecoration(labelText: 'Role'),
            items: _roles
                .map((r) => DropdownMenuItem(
                      value: r,
                      child: Text(r,
                          style: TextStyle(
                              color: cs.onSurface)),
                    ))
                .toList(),
            onChanged: (v) => setState(() => _role = v ?? _role),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!,
                style: const TextStyle(color: ForgeColors.error, fontSize: 12)),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: _loading ? null : _submit,
          child: _loading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Generate link'),
        ),
      ],
    );
  }

  Future<void> _submit() async {
    setState(() { _loading = true; _error = null; });
    try {
      final url = await widget.onSubmit(_role);
      if (mounted) Navigator.pop(context, url);
    } catch (e) {
      setState(() { _loading = false; _error = e.toString(); });
    }
  }
}

// ── Shared UI helpers ─────────────────────────────────────────────────────────

class _AvatarCircle extends StatelessWidget {
  const _AvatarCircle({required this.initials});
  final String initials;

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(
      backgroundColor: ForgeColors.accentDim,
      radius: 18,
      child: Text(
        initials,
        style: const TextStyle(
          color: ForgeColors.accent,
          fontWeight: FontWeight.w700,
          fontSize: 13,
        ),
      ),
    );
  }
}

class _RoleBadge extends StatelessWidget {
  const _RoleBadge({required this.role});
  final String role;

  static Color _color(String role, Color fallback) => switch (role) {
        'super_admin' => const Color(0xFFE5A832),
        'admin' => ForgeColors.accent,
        'analyst' => ForgeColors.success,
        _ => fallback,
      };

  @override
  Widget build(BuildContext context) {
    final color = _color(role, Theme.of(context).colorScheme.onSurfaceVariant);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        role,
        style: TextStyle(
            color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, this.trailing});
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        Text(
          title.toUpperCase(),
          style: TextStyle(
            color: cs.onSurfaceVariant,
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        ),
        if (trailing != null) ...[
          const SizedBox(width: 8),
          trailing!,
        ],
      ],
    );
  }
}
