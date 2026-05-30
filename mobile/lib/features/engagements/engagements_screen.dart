import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/api/engagements_api.dart';
import '../../core/models/engagement.dart';
import '../../core/theme/app_theme.dart';

class EngagementsScreen extends StatefulWidget {
  const EngagementsScreen({super.key});

  @override
  State<EngagementsScreen> createState() => _EngagementsScreenState();
}

class _EngagementsScreenState extends State<EngagementsScreen> {
  final _api = EngagementsApi(ApiClient.instance);
  final _searchController = TextEditingController();

  List<Engagement> _all = [];
  bool _loading = true;
  String? _error;
  EngagementStatus? _filterStatus;

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
      final list = await _api.list();
      if (mounted) setState(() { _all = list; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  List<Engagement> get _filtered {
    final query = _searchController.text.toLowerCase();
    return _all.where((e) {
      final matchesSearch = query.isEmpty || e.targetUrl.toLowerCase().contains(query);
      final matchesStatus = _filterStatus == null || e.status == _filterStatus;
      return matchesSearch && matchesStatus;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _buildHeader(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _load,
            color: ForgeColors.accent,
            backgroundColor: ForgeColors.surface,
            child: _loading
                ? _buildSkeleton()
                : _error != null
                    ? _buildError()
                    : _buildList(),
          ),
        ),
      ],
    );
  }

  Widget _buildHeader() {
    return Container(
      color: ForgeColors.background,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // App bar row
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(
                children: [
                  const Text(
                    'Engagements',
                    style: TextStyle(
                      color: ForgeColors.textPrimary,
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const Spacer(),
                  if (_all.isNotEmpty)
                    Text(
                      '${_all.length}',
                      style: const TextStyle(color: ForgeColors.textTertiary, fontSize: 14),
                    ),
                ],
              ),
            ),
          ),
          // Search bar
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: TextField(
              controller: _searchController,
              style: const TextStyle(color: ForgeColors.textPrimary, fontSize: 14),
              decoration: InputDecoration(
                hintText: 'Search by target…',
                prefixIcon: const Icon(Icons.search, size: 18),
                suffixIcon: _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 16),
                        onPressed: () => _searchController.clear(),
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              ),
            ),
          ),
          // Filter chips
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FilterChip(
                    label: 'All',
                    selected: _filterStatus == null,
                    onTap: () => setState(() => _filterStatus = null),
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Running',
                    selected: _filterStatus == EngagementStatus.running,
                    onTap: () => setState(() => _filterStatus = EngagementStatus.running),
                    color: ForgeColors.accent,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Complete',
                    selected: _filterStatus == EngagementStatus.complete,
                    onTap: () => setState(() => _filterStatus = EngagementStatus.complete),
                    color: ForgeColors.success,
                  ),
                  const SizedBox(width: 8),
                  _FilterChip(
                    label: 'Failed',
                    selected: _filterStatus == EngagementStatus.aborted,
                    onTap: () => setState(() => _filterStatus = EngagementStatus.aborted),
                    color: ForgeColors.error,
                  ),
                ],
              ),
            ),
          ),
          const Divider(height: 1),
        ],
      ),
    );
  }

  Widget _buildList() {
    final items = _filtered;
    if (items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 80),
          Center(
            child: Column(
              children: [
                const Icon(Icons.radar_outlined, size: 48, color: ForgeColors.textTertiary),
                const SizedBox(height: 16),
                Text(
                  _searchController.text.isNotEmpty || _filterStatus != null
                      ? 'No matching scans.'
                      : 'No scans yet. Tap + to start one.',
                  style: const TextStyle(color: ForgeColors.textTertiary, fontSize: 14),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ],
      );
    }

    return ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: items.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final e = items[index];
        return _EngagementListCard(
          engagement: e,
          onTap: () => context.push('/engagement/${e.id}', extra: e.targetUrl),
        );
      },
    );
  }

  Widget _buildError() {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 80),
        Center(
          child: GestureDetector(
            onTap: _load,
            child: const Text(
              'Could not load engagements.\nTap to retry.',
              textAlign: TextAlign.center,
              style: TextStyle(color: ForgeColors.textSecondary, height: 1.5),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSkeleton() {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: 5,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (_, _) => _ShimmerBox(height: 76),
    );
  }
}

// ---------------------------------------------------------------------------
// Engagement list card (full detail row)
// ---------------------------------------------------------------------------

class _EngagementListCard extends StatelessWidget {
  const _EngagementListCard({required this.engagement, required this.onTap});
  final Engagement engagement;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: ForgeColors.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: ForgeColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    engagement.displayName,
                    style: const TextStyle(
                      color: ForgeColors.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _timeAgo(engagement.createdAt),
                  style: const TextStyle(color: ForgeColors.textTertiary, fontSize: 12),
                ),
                const SizedBox(width: 4),
                const Icon(Icons.chevron_right, size: 16, color: ForgeColors.textTertiary),
              ],
            ),
            if (engagement.targetPath != null) ...[
              const SizedBox(height: 2),
              Text(
                engagement.targetPath!,
                style: const TextStyle(color: ForgeColors.textTertiary, fontSize: 12),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
            const SizedBox(height: 8),
            Row(
              children: [
                _StatusBadge(status: engagement.status),
                const SizedBox(width: 6),
                _TypeBadge(type: engagement.targetType),
              ],
            ),
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

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
    this.color,
  });
  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final activeColor = color ?? ForgeColors.accent;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? activeColor.withValues(alpha: 0.15) : ForgeColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected ? activeColor.withValues(alpha: 0.4) : ForgeColors.border,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? activeColor : ForgeColors.textSecondary,
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shared badge widgets
// ---------------------------------------------------------------------------

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final EngagementStatus status;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      EngagementStatus.running => ('Running', ForgeColors.accent),
      EngagementStatus.complete => ('Complete', ForgeColors.success),
      EngagementStatus.pending => ('Queued', ForgeColors.warning),
      EngagementStatus.aborted => ('Failed', ForgeColors.error),
      EngagementStatus.pausedAtGate => ('Paused', ForgeColors.textSecondary),
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
  const _ShimmerBox({required this.height});
  final double height;

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
    return FadeTransition(
      opacity: _anim,
      child: Container(
        height: widget.height,
        decoration: BoxDecoration(
          color: ForgeColors.surface2,
          borderRadius: BorderRadius.circular(10),
        ),
      ),
    );
  }
}
