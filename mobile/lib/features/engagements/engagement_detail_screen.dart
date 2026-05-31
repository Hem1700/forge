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
// Terminal log color constants
// ---------------------------------------------------------------------------

const _kTermBg     = Color(0xFF050508);
const _kTermBorder = Color(0xFF0E3A42);
const _kTagCrit    = Color(0xFFF87171);
const _kTagFind    = Color(0xFFFBBF24);
const _kTagDone    = Color(0xFF4ADE80);
const _kTagCyan    = Color(0xFF06B6D4);
const _kTagFail    = Color(0xFFF87171);
const _kTagInfo    = Color(0xFF444A60);
const _kMsgCyan    = Color(0xFF8890A8);
const _kTagGate    = Color(0xFFFBBF24); // amber — gate / warn events
const _kTimestamp  = Color(0xFF4B5268); // muted gray for timestamp prefix

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
  final String tag;
  final Color tagColor;
  final String message;
  final Color messageColor;
  final DateTime timestamp;
  _LogEntry({
    required this.tag,
    required this.tagColor,
    required this.message,
    required this.messageColor,
    required this.timestamp,
  });
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
  final _scrollController = ScrollController();

  Engagement? _engagement;
  bool _loading = true;

  // Live state
  EngagementStatus _liveStatus = EngagementStatus.pending;
  int _findingsCount = 0;

  final List<_AgentModel> _agents = [];
  final List<_LogEntry> _log = []; // oldest-first (newest at end)

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
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
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
        // tempLog is oldest-first; keep that order for terminal display (newest at end)
        if (mounted) {
          setState(() {
            _log.addAll(tempLog);
          });
          _scrollToBottom();
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
        if (entry != null) _log.add(entry); // append: newest at end
      });
      _scrollToBottom();
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
      case 'finding_created':
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
    final ts = ev.timestamp;
    switch (ev.type) {
      case 'agent_started':
        final phase = ev.payload['phase'] as String?;
        final agentType = ev.payload['agent_type'] as String?;
        final hypothesis = ev.payload['hypothesis'] as String?;
        final String msg;
        if (phase != null) {
          msg = '${_phaseName(phase)} initializing — ${_phaseDescription(phase)}';
        } else if (hypothesis != null) {
          final truncated = hypothesis.length > 60 ? '${hypothesis.substring(0, 60)}…' : hypothesis;
          msg = 'ProbeAgent initializing — testing: $truncated';
        } else if (agentType != null) {
          msg = '${_agentTypeLabel(agentType)} initializing — ${_agentTypeDescription(agentType)}';
        } else {
          msg = 'Agent initializing';
        }
        return _LogEntry(tag: 'AGNT', tagColor: _kTagCyan, message: msg, messageColor: _kMsgCyan, timestamp: ts);

      case 'os_agent_started':
        final t = ev.payload['agent_type'] as String? ?? 'agent';
        return _LogEntry(
          tag: 'AGNT', tagColor: _kTagCyan,
          message: '${_agentTypeLabel(t)} scanning — ${_agentTypeDescription(t)}',
          messageColor: _kMsgCyan, timestamp: ts,
        );

      case 'os_agents_started':
        final types = (ev.payload['agents'] as List<dynamic>?)?.cast<String>() ?? [];
        if (types.isEmpty) return null;
        return _LogEntry(
          tag: 'SCAN', tagColor: _kTagCyan,
          message: 'Launching ${types.length} parallel security agents',
          messageColor: _kMsgCyan, timestamp: ts,
        );

      case 'agent_completed':
        final phase = ev.payload['phase'] as String?;
        final agentType = ev.payload['agent_type'] as String?;
        final n = ev.payload['findings_count'] as int? ?? ev.payload['findings'] as int?;
        final String completionMsg;
        if (phase != null) {
          final detail = _phaseCompletionDetail(phase, ev.payload);
          completionMsg = '${_phaseName(phase)} complete — $detail';
        } else if (agentType != null) {
          completionMsg = n != null
              ? '${_agentTypeLabel(agentType)} complete — $n findings'
              : '${_agentTypeLabel(agentType)} complete';
        } else {
          completionMsg = n != null ? 'Agent complete — $n findings' : 'Agent complete';
        }
        return _LogEntry(tag: 'DONE', tagColor: _kTagDone, message: completionMsg, messageColor: _kTagDone, timestamp: ts);

      case 'os_agent_complete':
        final t = ev.payload['agent_type'] as String? ?? 'agent';
        final n = ev.payload['findings'] as int?;
        final msg = n != null
            ? '${_agentTypeLabel(t)} complete — $n findings'
            : '${_agentTypeLabel(t)} complete';
        return _LogEntry(tag: 'DONE', tagColor: _kTagDone, message: msg, messageColor: _kTagDone, timestamp: ts);

      case 'finding_discovered':
      case 'finding_created':
        final f = ev.payload['finding'] as Map<String, dynamic>?;
        final sev = (f?['severity'] as String? ?? '').toLowerCase();
        final title = f?['title'] as String? ??
            f?['vulnerability'] as String? ??
            f?['vulnerability_class'] as String? ?? 'Finding';
        final surface = f?['endpoint'] as String? ??
            f?['file'] as String? ??
            f?['affected_surface'] as String?;
        final isCrit = sev == 'critical';
        final sevLabel = switch (sev) {
          'critical' => 'Critical',
          'high' => 'High',
          'medium' => 'Medium',
          'low' => 'Low',
          _ => sev.isNotEmpty ? '${sev[0].toUpperCase()}${sev.substring(1)}' : 'Unknown',
        };
        final truncTitle = title.length > 60 ? '${title.substring(0, 60)}…' : title;
        final surfacePart = (surface != null && surface.isNotEmpty && surface != 'unknown')
            ? ' — $surface'
            : '';
        return _LogEntry(
          tag: isCrit ? 'CRIT' : 'FIND',
          tagColor: isCrit ? _kTagCrit : _kTagFind,
          message: '$truncTitle ($sevLabel)$surfacePart',
          messageColor: isCrit ? _kTagCrit : _kTagFind,
          timestamp: ts,
        );

      case 'campaign_complete':
      case 'os_pipeline_complete':
        final status = ev.payload['status'] as String?;
        if (status == 'budget_exceeded') {
          return _LogEntry(tag: 'WARN', tagColor: _kTagGate, message: 'Budget limit reached — scan stopped', messageColor: _kTagGate, timestamp: ts);
        }
        if (status == 'rate_limited') {
          return _LogEntry(tag: 'WAIT', tagColor: _kTagGate, message: 'Rate limited — queued, resuming shortly', messageColor: _kTagGate, timestamp: ts);
        }
        if (status == 'error') {
          final err = ev.payload['error'] as String? ?? 'unknown error';
          final truncErr = err.length > 80 ? '${err.substring(0, 80)}…' : err;
          return _LogEntry(tag: 'FAIL', tagColor: _kTagFail, message: 'Scan failed — $truncErr', messageColor: _kTagFail, timestamp: ts);
        }
        final total = ev.payload['total_findings'] as int?;
        final critCount = ev.payload['critical_count'] as int?;
        final String doneMsg;
        if (total != null && critCount != null && critCount > 0) {
          doneMsg = 'Scan complete — $total findings, $critCount critical';
        } else if (total != null) {
          doneMsg = 'Scan complete — $total findings';
        } else {
          doneMsg = 'Scan complete';
        }
        return _LogEntry(tag: 'DONE', tagColor: _kTagDone, message: doneMsg, messageColor: _kTagDone, timestamp: ts);

      case 'os_modeling_started':
        final host = ev.payload['host'] as String? ?? 'target';
        return _LogEntry(
          tag: 'SCAN', tagColor: _kTagCyan,
          message: 'SSH connection established — collecting system fingerprint from $host',
          messageColor: _kMsgCyan, timestamp: ts,
        );

      case 'os_modeling_complete':
        final packages = ev.payload['packages'] as int?;
        final ports = ev.payload['open_ports'] as int?;
        final String fpMsg;
        if (packages != null && ports != null) {
          fpMsg = 'Fingerprint complete — $packages packages, $ports open ports';
        } else if (packages != null) {
          fpMsg = 'Fingerprint complete — $packages packages';
        } else {
          fpMsg = 'Fingerprint complete';
        }
        return _LogEntry(tag: 'SCAN', tagColor: _kTagCyan, message: fpMsg, messageColor: _kMsgCyan, timestamp: ts);

      case 'os_modeling_failed':
        final err = ev.payload['error'] as String? ?? 'unknown error';
        return _LogEntry(
          tag: 'FAIL', tagColor: _kTagFail,
          message: 'Fingerprint failed — $err',
          messageColor: _kTagFail, timestamp: ts,
        );

      case 'agent_failed':
      case 'os_agent_failed':
        final rawLabel = ev.payload['agent_type'] as String? ??
            ev.payload['phase'] as String? ?? 'agent';
        final err = ev.payload['error'] as String?;
        final failLabel = _agentTypeLabel(rawLabel);
        final failMsg = (err != null && err.isNotEmpty)
            ? '$failLabel failed — $err'
            : '$failLabel failed';
        return _LogEntry(tag: 'FAIL', tagColor: _kTagFail, message: failMsg, messageColor: _kTagFail, timestamp: ts);

      case 'gate_triggered':
        return _LogEntry(tag: 'GATE', tagColor: _kTagGate, message: 'Paused at security gate — awaiting approval', messageColor: _kTagGate, timestamp: ts);

      case 'budget_exceeded':
        return _LogEntry(tag: 'WARN', tagColor: _kTagGate, message: 'Budget limit reached — scan stopped', messageColor: _kTagGate, timestamp: ts);

      case 'rate_limit':
        return _LogEntry(tag: 'WAIT', tagColor: _kTagGate, message: 'Rate limited — queued, resuming shortly', messageColor: _kTagGate, timestamp: ts);

      case 'progress':
        final detail = ev.payload['detail'] as String?;
        if (detail == null || detail.isEmpty) return null;
        return _LogEntry(tag: 'INFO', tagColor: _kTagInfo, message: detail, messageColor: _kTagInfo, timestamp: ts);

      default:
        return null;
    }
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
    'crawl' => 'Crawler',
    'campaign_planning' => 'Campaign Planner',
    'codebase_modeling' => 'Codebase Modeler',
    'cve_research' => 'CVE Researcher',
    'exploit_script_gen' => 'Exploit Generator',
    'diff_execute' => 'Differential Tester',
    'clone' => 'Repository Fetcher',
    _ => s,
  };

  static String _phaseDescription(String s) => switch (s) {
    'crawl' => 'mapping attack surface and endpoints',
    'campaign_planning' => 'generating attack hypotheses from surface model',
    'codebase_modeling' => 'parsing code structure and attack surfaces',
    'cve_research' => 'querying OSV and NVD for advisories',
    'exploit_script_gen' => 'generating weaponized PoC script',
    'diff_execute' => 'running vuln vs patched differential test',
    'clone' => 'fetching source code from repository',
    _ => 'running',
  };

  static String _phaseCompletionDetail(String phase, Map<String, dynamic> payload) {
    return switch (phase) {
      'crawl' => payload['app_type'] != null ? 'detected ${payload['app_type']}' : 'surface mapped',
      'campaign_planning' => payload['hypotheses'] != null ? '${payload['hypotheses']} hypotheses generated' : 'complete',
      'codebase_modeling' => payload['attack_surfaces'] != null ? '${payload['attack_surfaces']} attack surfaces found' : 'complete',
      'cve_research' => payload['package'] != null
          ? 'advisory found — ${payload['package']} (first fixed: ${payload['first_fixed'] ?? 'unknown'})'
          : 'complete',
      'exploit_script_gen' => payload['language'] != null ? '${payload['language']} script generated' : 'complete',
      'diff_execute' => payload['verdict'] != null ? 'verdict: ${payload['verdict']}' : 'complete',
      'clone' => 'repository cloned',
      _ => 'complete',
    };
  }

  static String _agentTypeLabel(String t) => switch (t) {
    'privesc' => 'PrivEscAgent',
    'service_audit' => 'ServiceAuditAgent',
    'package_vuln' => 'PackageVulnAgent',
    'config_audit' => 'ConfigAuditAgent',
    'network_exposure' => 'NetworkExposureAgent',
    'chain_discovery' => 'ChainDiscoveryAgent',
    'code_analyzer' => 'CodeAnalyzerAgent',
    'dependency_scanner' => 'DependencyScannerAgent',
    'fuzzer' => 'FuzzerAgent',
    'secret_scanner' => 'SecretScannerAgent',
    'config_auditor' => 'ConfigAuditorAgent',
    'probe' => 'ProbeAgent',
    _ => t,
  };

  static String _agentTypeDescription(String t) => switch (t) {
    'privesc' => 'SUID binaries, sudo misconfigs, kernel CVEs',
    'service_audit' => 'exposed services and misconfigurations',
    'package_vuln' => 'building SBOM, querying Trivy for CVEs',
    'config_audit' => 'system configuration weaknesses',
    'network_exposure' => 'open ports and firewall rules',
    'chain_discovery' => 'correlating findings into attack chains',
    'code_analyzer' => 'LLM-powered code review for vulnerabilities',
    'dependency_scanner' => 'building SBOM, querying OSV for CVEs',
    'fuzzer' => 'generating and running fuzz test cases',
    'secret_scanner' => 'detecting hardcoded credentials and keys',
    'config_auditor' => 'checking for insecure configurations',
    'probe' => 'HTTP probe-based hypothesis testing',
    _ => 'security analysis',
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
              controller: _scrollController,
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '// event log',
          style: TextStyle(
            color: _kTagInfo,
            fontSize: 11,
            fontFamily: 'monospace',
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
          decoration: BoxDecoration(
            color: _kTermBg,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: _kTermBorder),
          ),
          child: _log.isEmpty
              ? const Text(
                  'waiting for events...',
                  style: TextStyle(
                    color: _kTagInfo,
                    fontSize: 11,
                    fontFamily: 'monospace',
                  ),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ..._log.map((e) => _TerminalRow(entry: e)),
                    if (_isRunning) const _BlinkingCursor(),
                  ],
                ),
        ),
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

class _TerminalRow extends StatelessWidget {
  const _TerminalRow({required this.entry});
  final _LogEntry entry;

  @override
  Widget build(BuildContext context) {
    final local = entry.timestamp.toLocal();
    final ts = '${local.hour.toString().padLeft(2, '0')}:'
        '${local.minute.toString().padLeft(2, '0')}:'
        '${local.second.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 11, fontFamily: 'monospace', height: 1.5),
          children: [
            TextSpan(
              text: '$ts  ',
              style: const TextStyle(color: _kTimestamp),
            ),
            TextSpan(
              text: '[${entry.tag}]  ',
              style: TextStyle(color: entry.tagColor),
            ),
            TextSpan(
              text: entry.message,
              style: TextStyle(color: entry.messageColor),
            ),
          ],
        ),
      ),
    );
  }
}

class _BlinkingCursor extends StatefulWidget {
  const _BlinkingCursor();

  @override
  State<_BlinkingCursor> createState() => _BlinkingCursorState();
}

class _BlinkingCursorState extends State<_BlinkingCursor> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 530))
      ..repeat(reverse: true);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: FadeTransition(
        opacity: Tween<double>(begin: 0.0, end: 1.0).animate(_ctrl),
        child: const Text(
          '▋',
          style: TextStyle(
            color: Color(0xFF06B6D4),
            fontSize: 11,
            fontFamily: 'monospace',
          ),
        ),
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
