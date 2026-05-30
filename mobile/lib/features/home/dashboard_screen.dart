import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/api/engagements_api.dart';
import '../../core/models/engagement.dart';
import '../../core/theme/app_theme.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = EngagementsApi(ApiClient.instance);
  List<Engagement>? _engagements;
  final Map<String, int> _findingCounts = {};
  bool _loading = true;
  String? _error;

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
      final list = await _api.list();
      if (!mounted) return;
      setState(() { _engagements = list; _loading = false; });
      _loadFindingCounts(list);
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _loadFindingCounts(List<Engagement> list) async {
    final complete = list
        .where((e) => e.status == EngagementStatus.complete)
        .take(5)
        .toList();
    final results = await Future.wait(
      complete.map((e) => _api.findings(e.id).then((f) => (e.id, f.length))),
      eagerError: false,
    ).catchError((_) => <(String, int)>[]);
    if (!mounted) return;
    setState(() {
      for (final (id, count) in results) {
        _findingCounts[id] = count;
      }
    });
  }

  int get _activeCount =>
      (_engagements ?? []).where((e) => e.status == EngagementStatus.running).length;

  int get _criticalCount => 0;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      children: [
        Expanded(
          child: RefreshIndicator(
            onRefresh: _load,
            color: ForgeColors.accent,
            backgroundColor: cs.surface,
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverAppBar(
                  title: const Text('Dashboard'),
                  floating: true,
                  actions: [
                    IconButton(
                      icon: const Icon(Icons.notifications_outlined),
                      onPressed: () {},
                    ),
                  ],
                ),
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                  sliver: SliverToBoxAdapter(
                    child: _loading
                        ? _buildSkeleton()
                        : _error != null
                            ? _buildError()
                            : _buildContent(),
                  ),
                ),
              ],
            ),
          ),
        ),
        _buildNewScanButton(),
      ],
    );
  }

  Widget _buildContent() {
    final cs = Theme.of(context).colorScheme;
    final engagements = _engagements ?? [];
    final recent = engagements.take(5).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _MetricGrid(activeCount: _activeCount, criticalCount: _criticalCount),
        const SizedBox(height: 24),
        Text(
          'Recent engagements',
          style: TextStyle(
            color: cs.onSurface,
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
        const SizedBox(height: 12),
        if (recent.isEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Text(
                'No scans yet.',
                style: TextStyle(color: cs.onSurfaceVariant),
              ),
            ),
          )
        else
          ...recent.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _EngagementCard(
                  engagement: e,
                  findingsCount: _findingCounts[e.id],
                  onTap: () => context.push('/engagement/${e.id}'),
                ),
              )),
      ],
    );
  }

  Widget _buildError() {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 60),
        child: GestureDetector(
          onTap: _load,
          child: Text(
            'Could not load engagements.\nTap to retry.',
            textAlign: TextAlign.center,
            style: TextStyle(color: cs.onSurfaceVariant, height: 1.5),
          ),
        ),
      ),
    );
  }

  Widget _buildSkeleton() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Metric grid skeleton
        Row(
          children: [
            Expanded(child: _ShimmerBox(height: 88)),
            const SizedBox(width: 12),
            Expanded(child: _ShimmerBox(height: 88)),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: _ShimmerBox(height: 88)),
            const SizedBox(width: 12),
            Expanded(child: _ShimmerBox(height: 88)),
          ],
        ),
        const SizedBox(height: 24),
        _ShimmerBox(height: 16, width: 140),
        const SizedBox(height: 12),
        _ShimmerBox(height: 76),
        const SizedBox(height: 10),
        _ShimmerBox(height: 76),
        const SizedBox(height: 10),
        _ShimmerBox(height: 76),
      ],
    );
  }

  Widget _buildNewScanButton() {
    final cs = Theme.of(context).colorScheme;
    return Container(
      color: cs.surface,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
      child: ForgeGlowButton(
        label: 'New scan',
        icon: Icons.add,
        onPressed: () => context.push('/new-scan'),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Metric grid
// ---------------------------------------------------------------------------

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({required this.activeCount, required this.criticalCount});
  final int activeCount;
  final int criticalCount;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _MetricTile(
                label: 'Active scans',
                value: '$activeCount',
                icon: Icons.radar,
                color: ForgeColors.accent,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _MetricTile(
                label: 'Findings today',
                value: '--',
                icon: Icons.bug_report_outlined,
                color: ForgeColors.warning,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _MetricTile(
                label: 'Budget used',
                value: '--',
                icon: Icons.account_balance_wallet_outlined,
                color: cs.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _MetricTile(
                label: 'Critical',
                value: '$criticalCount',
                icon: Icons.warning_amber_rounded,
                color: ForgeColors.error,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
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
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 10),
          Text(
            value,
            style: TextStyle(
              color: cs.onSurface,
              fontSize: 24,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Engagement card (shared with EngagementsScreen)
// ---------------------------------------------------------------------------

class _EngagementCard extends StatelessWidget {
  const _EngagementCard({required this.engagement, required this.onTap, this.findingsCount});
  final Engagement engagement;
  final VoidCallback onTap;
  final int? findingsCount;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: cs.outline),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    engagement.displayName,
                    style: TextStyle(
                      color: cs.onSurface,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      _StatusBadge(status: engagement.status),
                      const SizedBox(width: 6),
                      _TypeBadge(type: engagement.targetType),
                      if (findingsCount != null && findingsCount! > 0) ...[
                        const SizedBox(width: 6),
                        _Badge(
                          label: '$findingsCount findings',
                          color: ForgeColors.warning,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Text(
              _timeAgo(engagement.createdAt),
              style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12),
            ),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right, size: 16, color: cs.onSurfaceVariant),
          ],
        ),
      ),
    );
  }

  static String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inDays > 0) return '${diff.inDays}d ago';
    if (diff.inHours > 0) return '${diff.inHours}h ago';
    if (diff.inMinutes > 0) return '${diff.inMinutes}m ago';
    return 'just now';
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final EngagementStatus status;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final (label, color) = switch (status) {
      EngagementStatus.running => ('Running', ForgeColors.accent),
      EngagementStatus.complete => ('Complete', ForgeColors.success),
      EngagementStatus.pending => ('Queued', ForgeColors.warning),
      EngagementStatus.aborted => ('Failed', ForgeColors.error),
      EngagementStatus.pausedAtGate => ('Paused', cs.onSurfaceVariant),
    };
    return _Badge(label: label, color: color);
  }
}

class _TypeBadge extends StatelessWidget {
  const _TypeBadge({required this.type});
  final String type;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (type.toLowerCase()) {
      'os' => ('OS', ForgeColors.warning),
      'code' => ('Code', const Color(0xFF9C6ADE)),
      _ => ('Web', ForgeColors.accent),
    };
    return _Badge(label: label, color: color);
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shimmer placeholder
// ---------------------------------------------------------------------------

class _ShimmerBox extends StatefulWidget {
  const _ShimmerBox({required this.height, this.width = double.infinity});
  final double height;
  final double width;

  @override
  State<_ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<_ShimmerBox> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    );
    _anim = Tween<double>(begin: 0.3, end: 0.7).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut),
    );
    _ctrl.repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return FadeTransition(
      opacity: _anim,
      child: Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(
          color: cs.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
        ),
      ),
    );
  }
}
