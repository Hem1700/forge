import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../core/api/api_client.dart';
import '../../core/api/engagements_api.dart';
import '../../core/models/engagement.dart';
import '../../core/state/notifiers.dart';
import '../../core/storage/cache_storage.dart';
import '../../core/theme/app_theme.dart';

// ---------------------------------------------------------------------------
// Internal models
// ---------------------------------------------------------------------------

class _WsEvent {
  final int? id;
  final String type;
  final Map<String, dynamic> payload;
  final DateTime timestamp;

  const _WsEvent({
    required this.id,
    required this.type,
    required this.payload,
    required this.timestamp,
  });

  factory _WsEvent.fromMap(Map<String, dynamic> m) => _WsEvent(
        id: m['id'] as int?,
        type: (m['type'] as String?) ?? '',
        payload: (m['payload'] as Map<String, dynamic>?) ?? {},
        timestamp: DateTime.tryParse((m['timestamp'] as String?) ?? '') ?? DateTime.now(),
      );
}

enum _AgentStatus { waiting, running, done, failed }

class _AgentModel {
  final String key;
  String label;
  _AgentStatus status;
  _AgentModel({required this.key, required this.label, this.status = _AgentStatus.waiting});
}

class _LogEntry {
  final DateTime timestamp;
  final String text;
  final Color color;
  const _LogEntry({required this.timestamp, required this.text, required this.color});
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

class EngagementDetailScreen extends StatefulWidget {
  const EngagementDetailScreen({super.key, required this.engagementId});
  final String engagementId;

  @override
  State<EngagementDetailScreen> createState() => _EngagementDetailScreenState();
}

class _EngagementDetailScreenState extends State<EngagementDetailScreen> {
  final _api = EngagementsApi(ApiClient.instance);

  Engagement? _engagement;
  bool _loading = true;

  // Live state
  EngagementStatus _liveStatus = EngagementStatus.pending;
  int _findingsCount = 0;

  final List<_AgentModel> _agents = [];
  final List<_LogEntry> _log = []; // _log[0] = newest

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _sub?.cancel();
    _channel?.sink.close();
    super.dispose();
  }

  Future<void> _showDeleteSheet() async {
    if (_engagement == null) return;
    final engagement = _engagement!;
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        final cs = Theme.of(ctx).colorScheme;
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.delete_outline, color: ForgeColors.error, size: 20),
                    const SizedBox(width: 10),
                    Text(
                      'Delete engagement',
                      style: TextStyle(
                        color: cs.onSurface,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  engagement.displayName,
                  style: TextStyle(
                    color: cs.onSurface,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 8),
                Text(
                  'This will permanently delete all findings, events, and data for this scan.',
                  style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13, height: 1.4),
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(ctx).pop(false),
                        child: const Text('Cancel'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton(
                        style: FilledButton.styleFrom(backgroundColor: ForgeColors.error),
                        onPressed: () => Navigator.of(ctx).pop(true),
                        child: const Text('Delete', style: TextStyle(color: Colors.white)),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
    if (confirmed != true || !mounted) return;
    try {
      await _api.deleteEngagement(widget.engagementId);
      await CacheStorage.instance.clearEngagement(widget.engagementId);
      if (!mounted) return;
      engagementDeletedNotifier.value = widget.engagementId;
      final messenger = ScaffoldMessenger.of(context);
      context.pop();
      messenger.showSnackBar(const SnackBar(content: Text('Engagement deleted')));
    } catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to delete: $err')),
      );
    }
  }

  Future<void> _init() async {
    try {
      final eng = await _api.get(widget.engagementId);
      if (!mounted) return;
      setState(() {
        _engagement = eng;
        _liveStatus = eng.status;
        _loading = false;
      });

      // Load historical events to reconstruct agent + log state
      int maxEventId = 0;
      try {
        final events = await _api.getEvents(widget.engagementId);
        if (!mounted) return;
        // Events come back newest-first; reverse to process chronologically
        final chronological = events.reversed.toList();
        final tempLog = <_LogEntry>[];
        for (final e in chronological) {
          final ev = _WsEvent.fromMap(e);
          if (ev.id != null && ev.id! > maxEventId) maxEventId = ev.id!;
          _applyEvent(ev);
          final entry = _eventToLogEntry(ev);
          if (entry != null) tempLog.add(entry);
        }
        // tempLog is oldest-first; reverse so newest is at index 0
        if (mounted) {
          setState(() {
            _log.addAll(tempLog.reversed);
          });
        }
      } catch (_) {}

      // If still running, open WS from the last known event id
      if (eng.status == EngagementStatus.running) {
        await _connectWs(since: maxEventId > 0 ? maxEventId : null);
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _connectWs({int? since}) async {
    final path = since != null
        ? '/ws/${widget.engagementId}?since=$since'
        : '/ws/${widget.engagementId}';
    try {
      _channel = await ApiClient.instance.connect(path);
      _sub = _channel!.stream.listen(
        _onWsData,
        onDone: () {},
        onError: (_) {},
      );
    } catch (_) {
    }
  }

  void _onWsData(dynamic raw) {
    if (!mounted || raw is! String) return;
    try {
      final m = jsonDecode(raw) as Map<String, dynamic>;
      final ev = _WsEvent.fromMap(m);
      setState(() {
        _applyEvent(ev);
        final entry = _eventToLogEntry(ev);
        if (entry != null) _log.insert(0, entry);
      });
    } catch (_) {}
  }

  // Mutates agent list and counts without calling setState (call inside setState).
  void _applyEvent(_WsEvent ev) {
    switch (ev.type) {
      case 'agent_started':
        final key = _agentKey(ev.payload);
        final label = _agentLabel(ev.payload);
        final idx = _agents.indexWhere((a) => a.key == key);
        if (idx >= 0) {
          _agents[idx].status = _AgentStatus.running;
          _agents[idx].label = label;
        } else {
          _agents.add(_AgentModel(key: key, label: label, status: _AgentStatus.running));
        }

      case 'os_agent_started':
        final t = ev.payload['agent_type'] as String? ?? 'agent';
        final idx = _agents.indexWhere((a) => a.key == t);
        if (idx >= 0) {
          _agents[idx].status = _AgentStatus.running;
        } else {
          _agents.add(_AgentModel(key: t, label: _agentTypeLabel(t), status: _AgentStatus.running));
        }

      case 'os_agents_started':
        final types = (ev.payload['agents'] as List<dynamic>?)?.cast<String>() ?? [];
        for (final t in types) {
          if (_agents.every((a) => a.key != t)) {
            _agents.add(_AgentModel(key: t, label: _agentTypeLabel(t)));
          }
        }

      case 'agent_completed':
        final key = ev.payload['agent_id'] as String? ??
            ev.payload['agent_type'] as String? ??
            ev.payload['phase'] as String?;
        if (key != null) {
          final idx = _agents.indexWhere((a) => a.key == key);
          if (idx >= 0) _agents[idx].status = _AgentStatus.done;
        }

      case 'os_agent_complete':
        final t = ev.payload['agent_type'] as String?;
        if (t != null) {
          final idx = _agents.indexWhere((a) => a.key == t);
          if (idx >= 0) _agents[idx].status = _AgentStatus.done;
        }

      case 'agent_failed':
      case 'os_agent_failed':
        final key = ev.payload['agent_id'] as String? ??
            ev.payload['agent_type'] as String?;
        if (key != null) {
          final idx = _agents.indexWhere((a) => a.key == key);
          if (idx >= 0) _agents[idx].status = _AgentStatus.failed;
        }

      case 'finding_discovered':
        _findingsCount++;

      case 'campaign_complete':
      case 'os_pipeline_complete':
        _liveStatus = EngagementStatus.complete;
        for (final a in _agents) {
          if (a.status == _AgentStatus.running) a.status = _AgentStatus.done;
        }
    }
  }

  _LogEntry? _eventToLogEntry(_WsEvent ev) {
    final cs = Theme.of(context).colorScheme;
    String? text;
    var color = cs.onSurfaceVariant;

    switch (ev.type) {
      case 'agent_started':
        text = '→ ${_agentLabel(ev.payload)} started';
        color = ForgeColors.accent;
      case 'os_agent_started':
        final t = ev.payload['agent_type'] as String? ?? 'agent';
        text = '→ ${_agentTypeLabel(t)} started';
        color = ForgeColors.accent;
      case 'agent_completed':
        final label = ev.payload['phase'] as String? ?? ev.payload['agent_type'] as String? ?? 'agent';
        final n = ev.payload['findings_count'] as int? ?? ev.payload['findings'] as int?;
        text = '✓ ${_phaseName(label)} complete${n != null ? ' ($n findings)' : ''}';
        color = ForgeColors.success;
      case 'os_agent_complete':
        final t = ev.payload['agent_type'] as String? ?? 'agent';
        final n = ev.payload['findings'] as int?;
        text = '✓ ${_agentTypeLabel(t)} complete${n != null ? ' ($n findings)' : ''}';
        color = ForgeColors.success;
      case 'finding_discovered':
        final f = ev.payload['finding'] as Map<String, dynamic>?;
        final sev = (f?['severity'] as String? ?? '').toLowerCase();
        final title = f?['title'] as String? ??
            f?['vulnerability_class'] as String? ??
            'Finding';
        text = '⚠  $title';
        color = (sev == 'critical' || sev == 'high') ? ForgeColors.error : ForgeColors.accent;
      case 'campaign_complete':
      case 'os_pipeline_complete':
        text = '● Scan complete';
        color = ForgeColors.success;
      case 'os_modeling_started':
        text = '→ OS fingerprinting…';
        color = ForgeColors.accent;
      case 'os_modeling_complete':
        final pkgs = ev.payload['packages'] as int? ?? 0;
        text = '✓ OS model ready — $pkgs packages';
        color = ForgeColors.success;
      case 'os_modeling_failed':
        text = '✗ OS fingerprint failed: ${ev.payload['error'] ?? ''}';
        color = ForgeColors.error;
      case 'agent_failed':
      case 'os_agent_failed':
        final label = ev.payload['agent_type'] as String? ?? ev.payload['error'] as String? ?? 'agent';
        text = '✗ $label failed';
        color = ForgeColors.error;
      case 'progress':
        final detail = ev.payload['detail'] as String?;
        if (detail == null || detail.isEmpty) return null;
        text = detail;
        color = cs.onSurfaceVariant;
      default:
        return null;
    }

    return _LogEntry(timestamp: ev.timestamp, text: text, color: color);
  }

  int get _agentsActiveCount =>
      _agents.where((a) => a.status == _AgentStatus.running).length;

  bool get _isRunning => _liveStatus == EngagementStatus.running;
  bool get _isDone =>
      _liveStatus == EngagementStatus.complete ||
      _liveStatus == EngagementStatus.aborted;

  static String _agentKey(Map<String, dynamic> p) =>
      p['agent_id'] as String? ??
      p['phase'] as String? ??
      p['agent_type'] as String? ??
      'agent';

  static String _agentLabel(Map<String, dynamic> p) {
    if (p.containsKey('phase')) return _phaseName(p['phase'] as String);
    if (p.containsKey('agent_type')) return _agentTypeLabel(p['agent_type'] as String);
    if (p.containsKey('hypothesis')) return 'Probe: ${p['hypothesis']}';
    return 'Agent';
  }

  static String _phaseName(String s) => switch (s) {
    'crawl' => 'Crawl',
    'campaign_planning' => 'Campaign Planner',
    'codebase_modeling' => 'Codebase Modeler',
    'cve_research' => 'CVE Research',
    'exploit_script_gen' => 'Exploit Generator',
    'diff_execute' => 'Differential Tester',
    _ => s,
  };

  static String _agentTypeLabel(String t) => switch (t) {
    'privesc' => 'Priv Escalation',
    'service_audit' => 'Service Audit',
    'package_vuln' => 'Package Vulns',
    'config_audit' => 'Config Audit',
    'network_exposure' => 'Network Exposure',
    'chain_discovery' => 'Attack Chains',
    'code_analyzer' => 'Code Analyzer',
    'dependency_scanner' => 'Dep Scanner',
    'fuzzer' => 'Fuzzer',
    'secret_scanner' => 'Secret Scanner',
    'config_auditor' => 'Config Auditor',
    'probe' => 'Probe',
    _ => t,
  };

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (_loading) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator(color: ForgeColors.accent)),
      );
    }

    final target = _engagement?.displayName ?? widget.engagementId;

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Expanded(
              child: Text(
                target,
                style: TextStyle(
                  color: _isRunning ? ForgeColors.accent : cs.onSurface,
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (_isRunning) ...[
              const SizedBox(width: 8),
              const _LiveDot(),
            ],
          ],
        ),
        actions: [
          if (!_isRunning)
            IconButton(
              icon: const Icon(Icons.delete_outline, color: ForgeColors.error),
              onPressed: _showDeleteSheet,
            ),
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: _StatusPill(status: _liveStatus),
          ),
        ],
      ),
      body: Column(
        children: [
          _buildMetrics(),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: [
                if (_agents.isNotEmpty) ...[
                  _buildAgentsCard(),
                  const SizedBox(height: 16),
                ],
                _buildLog(),
                const SizedBox(height: 16),
              ],
            ),
          ),
          if (_isDone) _buildBottomBar(),
        ],
      ),
    );
  }

  Widget _buildMetrics() {
    final cs = Theme.of(context).colorScheme;
    return Container(
      color: cs.surface,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          _MetricItem(
            label: 'Agents',
            value: _isRunning ? '$_agentsActiveCount active' : '${_agents.length} ran',
            color: ForgeColors.accent,
          ),
          const SizedBox(width: 28),
          _MetricItem(
            label: 'Findings',
            value: '$_findingsCount',
            color: _findingsCount > 0 ? ForgeColors.warning : cs.onSurfaceVariant,
          ),
        ],
      ),
    );
  }

  Widget _buildAgentsCard() {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.outline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('AGENTS',
            style: TextStyle(
              color: cs.onSurfaceVariant,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.8,
            )),
          const SizedBox(height: 10),
          ..._agents.map((a) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 5),
            child: _AgentRow(agent: a),
          )),
        ],
      ),
    );
  }

  Widget _buildLog() {
    final cs = Theme.of(context).colorScheme;
    if (_log.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 40),
          child: Text(
            _isRunning ? 'Waiting for events…' : 'No events.',
            style: TextStyle(color: cs.onSurfaceVariant, fontSize: 14),
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('EVENTS',
          style: TextStyle(
            color: cs.onSurfaceVariant,
            fontSize: 11,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.8,
          )),
        const SizedBox(height: 10),
        ..._log.map((e) => _LogRow(entry: e)),
      ],
    );
  }

  Widget _buildBottomBar() {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outline)),
      ),
      child: ForgeGlowButton(
        label: 'View findings',
        icon: Icons.bug_report_outlined,
        onPressed: () => context.push('/engagement/${widget.engagementId}/findings'),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Small widgets
// ---------------------------------------------------------------------------

class _LiveDot extends StatefulWidget {
  const _LiveDot();

  @override
  State<_LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<_LiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.3, end: 1.0).animate(_ctrl),
      child: Container(
        width: 8, height: 8,
        decoration: BoxDecoration(
          color: ForgeColors.accent,
          shape: BoxShape.circle,
          boxShadow: [BoxShadow(color: ForgeColors.accent.withValues(alpha: 0.6), blurRadius: 6)],
        ),
      ),
    );
  }
}

class _AgentDotWidget extends StatefulWidget {
  const _AgentDotWidget({required this.status});
  final _AgentStatus status;

  @override
  State<_AgentDotWidget> createState() => _AgentDotWidgetState();
}

class _AgentDotWidgetState extends State<_AgentDotWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 800));
    if (widget.status == _AgentStatus.running) _ctrl.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(_AgentDotWidget old) {
    super.didUpdateWidget(old);
    if (widget.status == _AgentStatus.running) {
      if (!_ctrl.isAnimating) _ctrl.repeat(reverse: true);
    } else {
      _ctrl.stop();
      _ctrl.value = 1.0;
    }
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  Color get _color => switch (widget.status) {
    _AgentStatus.running => ForgeColors.accent,
    _AgentStatus.done => ForgeColors.success,
    _AgentStatus.failed => ForgeColors.error,
    _AgentStatus.waiting => Theme.of(context).colorScheme.onSurfaceVariant,
  };

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: 8, height: 8,
      decoration: BoxDecoration(color: _color, shape: BoxShape.circle),
    );
    return widget.status == _AgentStatus.running
        ? FadeTransition(opacity: Tween<double>(begin: 0.3, end: 1.0).animate(_ctrl), child: dot)
        : dot;
  }
}

class _AgentRow extends StatelessWidget {
  const _AgentRow({required this.agent});
  final _AgentModel agent;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final (badgeLabel, badgeColor) = switch (agent.status) {
      _AgentStatus.running => ('Running', ForgeColors.accent),
      _AgentStatus.done => ('Done', ForgeColors.success),
      _AgentStatus.failed => ('Failed', ForgeColors.error),
      _AgentStatus.waiting => ('Waiting', cs.onSurfaceVariant),
    };
    return Row(
      children: [
        _AgentDotWidget(status: agent.status),
        const SizedBox(width: 10),
        Expanded(
          child: Text(agent.label,
            style: TextStyle(color: cs.onSurface, fontSize: 13)),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: badgeColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(badgeLabel,
            style: TextStyle(color: badgeColor, fontSize: 10, fontWeight: FontWeight.w600)),
        ),
      ],
    );
  }
}

class _LogRow extends StatelessWidget {
  const _LogRow({required this.entry});
  final _LogEntry entry;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final h = entry.timestamp.hour.toString().padLeft(2, '0');
    final m = entry.timestamp.minute.toString().padLeft(2, '0');
    final s = entry.timestamp.second.toString().padLeft(2, '0');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$h:$m:$s',
            style: TextStyle(
              color: cs.onSurfaceVariant, fontSize: 11, fontFamily: 'monospace',
            )),
          const SizedBox(width: 10),
          Expanded(
            child: Text(entry.text,
              style: TextStyle(color: entry.color, fontSize: 13)),
          ),
        ],
      ),
    );
  }
}

class _MetricItem extends StatelessWidget {
  const _MetricItem({required this.label, required this.value, required this.color});
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
          style: TextStyle(color: cs.onSurfaceVariant, fontSize: 11)),
        const SizedBox(height: 2),
        Text(value,
          style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});
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
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}
