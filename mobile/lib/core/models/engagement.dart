enum EngagementStatus { pending, running, pausedAtGate, complete, aborted }

class Engagement {
  const Engagement({
    required this.id,
    required this.targetUrl,
    required this.targetType,
    this.targetPath,
    required this.status,
    required this.gateStatus,
    required this.createdAt,
    this.completedAt,
  });

  final String id;
  final String targetUrl;
  final String targetType;
  final String? targetPath;
  final EngagementStatus status;
  final String gateStatus;
  final DateTime createdAt;
  final DateTime? completedAt;

  String get displayName {
    try {
      final host = Uri.parse(targetUrl).host;
      return host.isNotEmpty ? host : targetUrl;
    } catch (_) {
      return targetUrl;
    }
  }

  factory Engagement.fromJson(Map<String, dynamic> json) => Engagement(
        id: json['id'].toString(),
        targetUrl: json['target_url'] as String,
        targetType: json['target_type'] as String? ?? 'web',
        targetPath: json['target_path'] as String?,
        status: _parseStatus(json['status'] as String? ?? 'pending'),
        gateStatus: json['gate_status'] as String? ?? 'gate_1',
        createdAt: DateTime.parse(json['created_at'] as String),
        completedAt: json['completed_at'] != null
            ? DateTime.parse(json['completed_at'] as String)
            : null,
      );

  static EngagementStatus _parseStatus(String v) => switch (v) {
        'running' => EngagementStatus.running,
        'paused_at_gate' => EngagementStatus.pausedAtGate,
        'complete' => EngagementStatus.complete,
        'aborted' => EngagementStatus.aborted,
        _ => EngagementStatus.pending,
      };
}
