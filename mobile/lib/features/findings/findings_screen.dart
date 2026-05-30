import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api/api_client.dart';
import '../../core/api/engagements_api.dart';
import '../../core/models/engagement.dart';
import '../../core/models/finding.dart';
import '../../core/storage/cache_storage.dart';
import '../../core/theme/app_theme.dart';

// ─── Severity colour helpers ──────────────────────────────────────────────────

Color _borderColor(FindingSeverity s, BuildContext context) => switch (s) {
      FindingSeverity.critical => const Color(0xFFCF6679),
      FindingSeverity.high => const Color(0xFFBA7517),
      FindingSeverity.medium => const Color(0xFFB8B000),
      FindingSeverity.low => const Color(0xFF555555),
      _ => Theme.of(context).colorScheme.outline,
    };

Color _badgeBg(FindingSeverity s, BuildContext context) => switch (s) {
      FindingSeverity.critical => const Color(0xFF4D1F27),
      FindingSeverity.high => const Color(0xFF3D2800),
      FindingSeverity.medium => const Color(0xFF2F2E00),
      FindingSeverity.low => const Color(0xFF1E1E1E),
      _ => Theme.of(context).colorScheme.surfaceContainerHighest,
    };

Color _badgeFg(FindingSeverity s, BuildContext context) => switch (s) {
      FindingSeverity.critical => const Color(0xFFCF6679),
      FindingSeverity.high => const Color(0xFFBA7517),
      FindingSeverity.medium => const Color(0xFFB8B000),
      FindingSeverity.low => const Color(0xFF888888),
      _ => Theme.of(context).colorScheme.onSurfaceVariant,
    };

String _severityLabel(FindingSeverity s) => switch (s) {
      FindingSeverity.critical => 'CRITICAL',
      FindingSeverity.high => 'HIGH',
      FindingSeverity.medium => 'MEDIUM',
      FindingSeverity.low => 'LOW',
      _ => 'INFO',
    };

FindingSeverity _parseSeverityStr(String s) => switch (s) {
      'critical' => FindingSeverity.critical,
      'high' => FindingSeverity.high,
      'medium' => FindingSeverity.medium,
      'low' => FindingSeverity.low,
      _ => FindingSeverity.info,
    };

// ─── AllFindingsTab ───────────────────────────────────────────────────────────

/// Global "Findings" tab: shows engagement list; tap to view findings.
class AllFindingsTab extends StatefulWidget {
  const AllFindingsTab({super.key});

  @override
  State<AllFindingsTab> createState() => _AllFindingsTabState();
}

class _AllFindingsTabState extends State<AllFindingsTab> {
  List<Engagement>? _engagements;
  String? _error;
  bool _showingCached = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _error = null; _showingCached = false; });
    try {
      final list = await EngagementsApi(ApiClient.instance).list();
      if (!mounted) return;
      await CacheStorage.instance.saveEngagements(list);
      setState(() => _engagements = list);
    } catch (e) {
      if (e is DioException && e.isConnectionError) {
        final cached = await CacheStorage.instance.getEngagements();
        if (!mounted) return;
        if (cached != null) {
          setState(() { _engagements = cached; _showingCached = true; });
          return;
        }
      }
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return RefreshIndicator(
      color: ForgeColors.accent,
      backgroundColor: cs.surface,
      onRefresh: _load,
      child: CustomScrollView(
        slivers: [
          const SliverAppBar(
            title: Text('Findings'),
            floating: true,
          ),
          if (_showingCached)
            SliverToBoxAdapter(
              child: Container(
                color: Colors.orange.withValues(alpha: 0.12),
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: const Row(
                  children: [
                    Icon(Icons.cloud_off, size: 14, color: Colors.orange),
                    SizedBox(width: 8),
                    Text('Showing cached data',
                        style: TextStyle(color: Colors.orange, fontSize: 12)),
                  ],
                ),
              ),
            ),
          if (_error != null)
            SliverFillRemaining(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, color: ForgeColors.error, size: 40),
                    const SizedBox(height: 12),
                    Text('Failed to load', style: TextStyle(color: cs.onSurface)),
                    const SizedBox(height: 16),
                    TextButton(onPressed: _load, child: const Text('Retry')),
                  ],
                ),
              ),
            )
          else if (_engagements == null)
            const SliverFillRemaining(
              child: Center(
                child: CircularProgressIndicator(strokeWidth: 2, color: ForgeColors.accent),
              ),
            )
          else if (_engagements!.isEmpty)
            SliverFillRemaining(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.bug_report_outlined, size: 52, color: cs.onSurfaceVariant),
                    const SizedBox(height: 16),
                    Text('No engagements yet',
                        style: TextStyle(color: cs.onSurfaceVariant, fontSize: 15)),
                    const SizedBox(height: 6),
                    Text('Start a scan to see findings here',
                        style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13)),
                  ],
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: SliverList.builder(
                itemCount: _engagements!.length,
                itemBuilder: (ctx, i) => _EngagementRow(engagement: _engagements![i]),
              ),
            ),
        ],
      ),
    );
  }
}

class _EngagementRow extends StatelessWidget {
  const _EngagementRow({required this.engagement});
  final Engagement engagement;

  Color _statusColor(BuildContext context) => switch (engagement.status) {
        EngagementStatus.complete => ForgeColors.success,
        EngagementStatus.running => ForgeColors.accent,
        EngagementStatus.aborted => ForgeColors.error,
        _ => Theme.of(context).colorScheme.onSurfaceVariant,
      };

  String get _statusLabel => switch (engagement.status) {
        EngagementStatus.complete => 'COMPLETE',
        EngagementStatus.running => 'RUNNING',
        EngagementStatus.aborted => 'ABORTED',
        EngagementStatus.pausedAtGate => 'PAUSED',
        _ => 'PENDING',
      };

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final statusColor = _statusColor(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: cs.outline),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          width: 36,
          height: 36,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: ForgeColors.accentDim,
          ),
          child: const Icon(Icons.bug_report_outlined, color: ForgeColors.accent, size: 18),
        ),
        title: Text(
          engagement.displayName,
          style: TextStyle(
              color: cs.onSurface, fontSize: 14, fontWeight: FontWeight.w500),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  _statusLabel,
                  style: TextStyle(
                      color: statusColor, fontSize: 10, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  engagement.targetType,
                  style: TextStyle(color: cs.onSurfaceVariant, fontSize: 11),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
        trailing:
            Icon(Icons.chevron_right, color: cs.onSurfaceVariant, size: 20),
        onTap: () => context.push(
          '/engagement/${engagement.id}/findings',
          extra: engagement.targetUrl,
        ),
      ),
    );
  }
}

// ─── FindingsScreen ───────────────────────────────────────────────────────────

class FindingsScreen extends StatefulWidget {
  const FindingsScreen({
    super.key,
    required this.engagementId,
    this.targetUrl,
  });

  final String engagementId;
  final String? targetUrl;

  @override
  State<FindingsScreen> createState() => _FindingsScreenState();
}

class _FindingsScreenState extends State<FindingsScreen> {
  final _api = EngagementsApi(ApiClient.instance);

  List<Finding>? _findings;
  String? _error;
  String? _severityFilter;
  String? _typeFilter;
  bool _isDownloading = false;
  String? _expandedId;
  bool _showingCached = false;

  @override
  void initState() {
    super.initState();
    _loadFindings();
  }

  Future<void> _loadFindings() async {
    setState(() { _findings = null; _error = null; _showingCached = false; });
    try {
      final list = await _api.findings(widget.engagementId);
      if (!mounted) return;
      await CacheStorage.instance.saveFindings(widget.engagementId, list);
      setState(() => _findings = list);
    } catch (e) {
      if (e is DioException && e.isConnectionError) {
        final cached = await CacheStorage.instance.getFindings(widget.engagementId);
        if (!mounted) return;
        if (cached != null) {
          setState(() { _findings = cached; _showingCached = true; });
          return;
        }
      }
      if (mounted) setState(() => _error = e.toString());
    }
  }

  List<Finding> get _filtered {
    if (_findings == null) return [];
    return _findings!.where((f) {
      if (_severityFilter != null && f.severity.name != _severityFilter) return false;
      if (_typeFilter != null && f.findingType != _typeFilter) return false;
      return true;
    }).toList();
  }

  Future<void> _showFilterSheet() async {
    final cs = Theme.of(context).colorScheme;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        side: BorderSide(color: cs.outline),
      ),
      isScrollControlled: true,
      builder: (_) => _FilterSheet(
        initialSeverity: _severityFilter,
        initialType: _typeFilter,
        onApply: (sev, type) {
          setState(() {
            _severityFilter = sev;
            _typeFilter = type;
          });
          Navigator.pop(context);
        },
      ),
    );
  }

  Future<void> _downloadAndShare() async {
    setState(() => _isDownloading = true);
    try {
      final bytes = await _api.downloadReport(widget.engagementId);
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/forge_report_${widget.engagementId}.pdf');
      await file.writeAsBytes(bytes);
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'FORGE Security Report',
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Export failed: $e'),
            backgroundColor: ForgeColors.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isDownloading = false);
    }
  }

  Future<void> _markFalsePositive(String findingId, bool value) async {
    try {
      await _api.markFalsePositive(findingId, value);
      await _loadFindings();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to update: $e'),
            backgroundColor: ForgeColors.error,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final filtered = _filtered;
    final hasFilter = _severityFilter != null || _typeFilter != null;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Findings'),
            if (widget.targetUrl != null)
              Text(
                widget.targetUrl!,
                style: TextStyle(
                    fontSize: 11,
                    color: cs.onSurfaceVariant,
                    fontWeight: FontWeight.w400),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
          ],
        ),
        actions: [
          if (_findings != null)
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: ForgeColors.accentDim,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${filtered.length}',
                    style: const TextStyle(
                        fontSize: 12,
                        color: ForgeColors.accent,
                        fontWeight: FontWeight.w700),
                  ),
                ),
              ),
            ),
          IconButton(
            icon: Icon(
              Icons.filter_list,
              color: hasFilter ? ForgeColors.accent : cs.onSurfaceVariant,
            ),
            tooltip: 'Filter',
            onPressed: _showFilterSheet,
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _isDownloading ? null : _downloadAndShare,
        backgroundColor: ForgeColors.accentDim,
        elevation: 0,
        tooltip: 'Download PDF report',
        child: _isDownloading
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: ForgeColors.accent),
              )
            : const Icon(Icons.download_outlined, color: ForgeColors.accent),
      ),
      body: Column(
        children: [
          if (_showingCached)
            Container(
              width: double.infinity,
              color: Colors.orange.withValues(alpha: 0.12),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: const Row(
                children: [
                  Icon(Icons.cloud_off, size: 14, color: Colors.orange),
                  SizedBox(width: 8),
                  Text('Showing cached data',
                      style: TextStyle(color: Colors.orange, fontSize: 12)),
                ],
              ),
            ),
          Expanded(
            child: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, color: ForgeColors.error, size: 40),
                    const SizedBox(height: 12),
                    Text('Failed to load findings',
                        style: TextStyle(color: cs.onSurface, fontSize: 16)),
                    const SizedBox(height: 6),
                    Text(_error!,
                        style: TextStyle(
                            color: cs.onSurfaceVariant, fontSize: 12)),
                    const SizedBox(height: 20),
                    TextButton(
                        onPressed: _loadFindings, child: const Text('Retry')),
                  ],
                ),
              ),
            )
          : RefreshIndicator(
              color: ForgeColors.accent,
              backgroundColor: cs.surface,
              onRefresh: _loadFindings,
              child: _findings == null
                  ? ListView.builder(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 12),
                      itemCount: 5,
                      itemBuilder: (context, _) => const _ShimmerCard(),
                    )
                  : filtered.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            SizedBox(
                              height: MediaQuery.of(context).size.height * 0.6,
                              child: Center(
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const Icon(Icons.check_circle_outline,
                                        size: 52,
                                        color: ForgeColors.success),
                                    const SizedBox(height: 16),
                                    Text('No findings',
                                        style: TextStyle(
                                            color: cs.onSurface,
                                            fontSize: 16)),
                                    const SizedBox(height: 6),
                                    Text('All clear for this engagement',
                                        style: TextStyle(
                                            color: cs.onSurfaceVariant,
                                            fontSize: 13)),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 12),
                          itemCount: filtered.length,
                          itemBuilder: (_, i) {
                            final f = filtered[i];
                            return _FindingCard(
                              key: ValueKey(f.id),
                              finding: f,
                              isExpanded: _expandedId == f.id,
                              onTap: () => setState(() {
                                _expandedId =
                                    _expandedId == f.id ? null : f.id;
                              }),
                              onFalsePositiveToggle: (v) =>
                                  _markFalsePositive(f.id, v),
                            );
                          },
                        ),
            ),
          ),        // closes Expanded
        ],          // closes Column children
      ),            // closes Column
    );
  }
}

// ─── Filter Sheet ─────────────────────────────────────────────────────────────

class _FilterSheet extends StatefulWidget {
  const _FilterSheet({
    required this.initialSeverity,
    required this.initialType,
    required this.onApply,
  });

  final String? initialSeverity;
  final String? initialType;
  final void Function(String? severity, String? type) onApply;

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  String? _severity;
  String? _type;

  @override
  void initState() {
    super.initState();
    _severity = widget.initialSeverity;
    _type = widget.initialType;
  }

  Widget _chip({
    required String label,
    required bool selected,
    required VoidCallback onTap,
    Color? color,
  }) {
    final cs = Theme.of(context).colorScheme;
    final c = color ?? ForgeColors.accent;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? c.withValues(alpha: 0.15) : cs.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: selected ? c : cs.outline),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? c : cs.onSurfaceVariant,
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'Filter Findings',
                style: TextStyle(
                    color: cs.onSurface,
                    fontSize: 17,
                    fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              TextButton(
                onPressed: () => setState(() {
                  _severity = null;
                  _type = null;
                }),
                child: const Text('Clear all'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text('Severity',
              style: TextStyle(
                  color: cs.onSurfaceVariant,
                  fontSize: 13,
                  fontWeight: FontWeight.w500)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in [null, 'critical', 'high', 'medium', 'low'])
                _chip(
                  label: s == null ? 'All' : '${s[0].toUpperCase()}${s.substring(1)}',
                  selected: _severity == s,
                  onTap: () => setState(() => _severity = s),
                  color: s == null ? null : _badgeFg(_parseSeverityStr(s), context),
                ),
            ],
          ),
          const SizedBox(height: 16),
          Text('Type',
              style: TextStyle(
                  color: cs.onSurfaceVariant,
                  fontSize: 13,
                  fontWeight: FontWeight.w500)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final t in [null, 'chain', 'regular'])
                _chip(
                  label: t == null ? 'All' : '${t[0].toUpperCase()}${t.substring(1)}',
                  selected: _type == t,
                  onTap: () => setState(() => _type = t),
                ),
            ],
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => widget.onApply(_severity, _type),
              style: ElevatedButton.styleFrom(
                backgroundColor: ForgeColors.accent,
                foregroundColor: cs.onPrimary,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('Apply', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Finding Card ─────────────────────────────────────────────────────────────

class _FindingCard extends StatefulWidget {
  const _FindingCard({
    super.key,
    required this.finding,
    required this.isExpanded,
    required this.onTap,
    required this.onFalsePositiveToggle,
  });

  final Finding finding;
  final bool isExpanded;
  final VoidCallback onTap;
  final Future<void> Function(bool) onFalsePositiveToggle;

  @override
  State<_FindingCard> createState() => _FindingCardState();
}

class _FindingCardState extends State<_FindingCard> {
  bool _marking = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final f = widget.finding;
    final bc = _borderColor(f.severity, context);

    return GestureDetector(
      onTap: widget.onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: cs.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: cs.outline),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(width: 3, color: bc),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            _SeverityBadge(severity: f.severity),
                            const SizedBox(width: 8),
                            if (f.agentType != null)
                              Text(
                                f.agentType!,
                                style: TextStyle(
                                    color: cs.onSurfaceVariant, fontSize: 11),
                              ),
                            const Spacer(),
                            Icon(
                              widget.isExpanded
                                  ? Icons.expand_less
                                  : Icons.expand_more,
                              size: 18,
                              color: cs.onSurfaceVariant,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          f.vulnerabilityClass ?? f.title,
                          style: TextStyle(
                            color: cs.onSurface,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        AnimatedCrossFade(
                          duration: const Duration(milliseconds: 250),
                          crossFadeState: widget.isExpanded
                              ? CrossFadeState.showSecond
                              : CrossFadeState.showFirst,
                          firstChild: f.isChain
                              ? Text(
                                  '${f.chainSteps?.length ?? 0} attack chain steps',
                                  style: const TextStyle(
                                      color: ForgeColors.accent, fontSize: 11),
                                )
                              : Text(
                                  f.description ?? '',
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      color: cs.onSurfaceVariant,
                                      fontSize: 11),
                                ),
                          secondChild: _ExpandedBody(
                            finding: f,
                            marking: _marking,
                            onMarkFalsePositive: () async {
                              setState(() => _marking = true);
                              try {
                                await widget.onFalsePositiveToggle(!f.isFalsePositive);
                              } finally {
                                if (mounted) setState(() => _marking = false);
                              }
                            },
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ─── Expanded body ────────────────────────────────────────────────────────────

class _ExpandedBody extends StatelessWidget {
  const _ExpandedBody({
    required this.finding,
    required this.marking,
    required this.onMarkFalsePositive,
  });

  final Finding finding;
  final bool marking;
  final VoidCallback onMarkFalsePositive;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final f = finding;
    final rec = f.recommendation ?? f.remediationNote;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),

        if (f.isChain && f.chainSteps != null && f.chainSteps!.isNotEmpty)
          _ChainSteps(steps: f.chainSteps!),

        if (f.description != null && f.description!.isNotEmpty) ...[
          _sectionLabel('Description', context),
          const SizedBox(height: 4),
          Text(
            f.description!,
            style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12),
          ),
          const SizedBox(height: 12),
        ],

        if (f.evidence.isNotEmpty) ...[
          _sectionLabel('Evidence', context),
          const SizedBox(height: 4),
          _EvidenceBlock(evidence: f.evidence),
          const SizedBox(height: 12),
        ],

        if (f.reproductionSteps.isNotEmpty) ...[
          _sectionLabel('Reproduction Steps', context),
          const SizedBox(height: 4),
          for (int i = 0; i < f.reproductionSteps.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${i + 1}. ',
                    style: const TextStyle(
                        color: ForgeColors.accent,
                        fontSize: 11,
                        fontWeight: FontWeight.w600),
                  ),
                  Expanded(
                    child: Text(
                      f.reproductionSteps[i].toString(),
                      style: TextStyle(
                          color: cs.onSurfaceVariant, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 12),
        ],

        if (rec != null && rec.isNotEmpty) ...[
          _sectionLabel('Recommendation', context),
          const SizedBox(height: 4),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF0a120a),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFF1a3a1a)),
            ),
            child: Text(
              rec,
              style: TextStyle(
                  color: cs.onSurfaceVariant, fontSize: 12),
            ),
          ),
          const SizedBox(height: 12),
        ],

        Row(
          children: [
            if (f.confidenceScore != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: ForgeColors.accentDim,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '${(f.confidenceScore! * 100).round()}% confidence',
                  style: const TextStyle(
                      color: ForgeColors.accent,
                      fontSize: 11,
                      fontWeight: FontWeight.w500),
                ),
              ),
            const Spacer(),
            marking
                ? SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: cs.onSurfaceVariant),
                  )
                : TextButton(
                    onPressed: onMarkFalsePositive,
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 0),
                      foregroundColor: f.isFalsePositive
                          ? cs.onSurfaceVariant
                          : ForgeColors.error,
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    child: Text(f.isFalsePositive
                        ? 'Unmark false positive'
                        : 'Mark false positive'),
                  ),
          ],
        ),
      ],
    );
  }

  Widget _sectionLabel(String text, BuildContext context) => Text(
        text,
        style: TextStyle(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5,
        ),
      );
}

// ─── Chain Steps ──────────────────────────────────────────────────────────────

class _ChainSteps extends StatelessWidget {
  const _ChainSteps({required this.steps});
  final List<String> steps;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Attack Chain',
            style: TextStyle(
                color: cs.onSurfaceVariant,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5),
          ),
          const SizedBox(height: 8),
          for (int i = 0; i < steps.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: ForgeColors.accentDim,
                      border: Border.all(color: ForgeColors.accent, width: 1),
                    ),
                    child: Center(
                      child: Text(
                        '${i + 1}',
                        style: const TextStyle(
                            color: ForgeColors.accent,
                            fontSize: 10,
                            fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text(
                        steps[i],
                        style: TextStyle(
                            color: cs.onSurfaceVariant, fontSize: 12),
                      ),
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

// ─── Evidence Block ───────────────────────────────────────────────────────────

class _EvidenceBlock extends StatelessWidget {
  const _EvidenceBlock({required this.evidence});
  final List<dynamic> evidence;

  @override
  Widget build(BuildContext context) {
    final text = evidence.map((e) {
      if (e is Map) {
        return e.entries.map((kv) => '${kv.key}: ${kv.value}').join('\n');
      }
      return e.toString();
    }).join('\n\n');

    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF050508),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF0e3a42)),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: 'monospace',
          color: cs.onSurfaceVariant,
          fontSize: 11,
          height: 1.5,
        ),
      ),
    );
  }
}

// ─── Severity Badge ───────────────────────────────────────────────────────────

class _SeverityBadge extends StatelessWidget {
  const _SeverityBadge({required this.severity});
  final FindingSeverity severity;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: _badgeBg(severity, context),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: _badgeFg(severity, context).withValues(alpha: 0.4)),
      ),
      child: Text(
        _severityLabel(severity),
        style: TextStyle(
          color: _badgeFg(severity, context),
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

// ─── Shimmer Card ─────────────────────────────────────────────────────────────

class _ShimmerCard extends StatefulWidget {
  const _ShimmerCard();

  @override
  State<_ShimmerCard> createState() => _ShimmerCardState();
}

class _ShimmerCardState extends State<_ShimmerCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _opacity = Tween<double>(begin: 0.3, end: 0.7)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AnimatedBuilder(
      animation: _opacity,
      builder: (context, _) => Opacity(
        opacity: _opacity.value,
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          height: 88,
          decoration: BoxDecoration(
            color: cs.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: cs.outline),
          ),
          child: Row(
            children: [
              Container(
                width: 3,
                decoration: BoxDecoration(
                  color: cs.outline,
                  borderRadius:
                      const BorderRadius.horizontal(left: Radius.circular(14)),
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        height: 14,
                        width: 60,
                        decoration: BoxDecoration(
                          color: cs.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Container(
                        height: 12,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: cs.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Container(
                        height: 10,
                        width: 140,
                        decoration: BoxDecoration(
                          color: cs.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
