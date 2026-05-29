enum EngagementStatus { active, paused, completed, archived }
enum EngagementType { pentest, redTeam, bugBounty, compliance, phishing }

class Engagement {
  const Engagement({
    required this.id,
    required this.name,
    required this.status,
    required this.type,
    required this.createdAt,
    this.description,
    this.targetScope,
    this.completedAt,
    this.findingCounts,
  });

  final String id;
  final String name;
  final EngagementStatus status;
  final EngagementType type;
  final DateTime createdAt;
  final String? description;
  final List<String>? targetScope;
  final DateTime? completedAt;
  final FindingCounts? findingCounts;

  factory Engagement.fromJson(Map<String, dynamic> json) => Engagement(
        id: json['id'] as String,
        name: json['name'] as String,
        status: _parseStatus(json['status'] as String? ?? 'active'),
        type: _parseType(json['type'] as String? ?? 'pentest'),
        createdAt: DateTime.parse(json['created_at'] as String),
        description: json['description'] as String?,
        targetScope: (json['target_scope'] as List<dynamic>?)?.cast<String>(),
        completedAt: json['completed_at'] != null
            ? DateTime.parse(json['completed_at'] as String)
            : null,
        findingCounts: json['finding_counts'] != null
            ? FindingCounts.fromJson(json['finding_counts'] as Map<String, dynamic>)
            : null,
      );

  static EngagementStatus _parseStatus(String v) => switch (v) {
        'paused' => EngagementStatus.paused,
        'completed' => EngagementStatus.completed,
        'archived' => EngagementStatus.archived,
        _ => EngagementStatus.active,
      };

  static EngagementType _parseType(String v) => switch (v) {
        'red_team' => EngagementType.redTeam,
        'bug_bounty' => EngagementType.bugBounty,
        'compliance' => EngagementType.compliance,
        'phishing' => EngagementType.phishing,
        _ => EngagementType.pentest,
      };
}

class FindingCounts {
  const FindingCounts({
    this.critical = 0,
    this.high = 0,
    this.medium = 0,
    this.low = 0,
    this.info = 0,
  });

  final int critical;
  final int high;
  final int medium;
  final int low;
  final int info;

  int get total => critical + high + medium + low + info;

  factory FindingCounts.fromJson(Map<String, dynamic> json) => FindingCounts(
        critical: (json['critical'] as num?)?.toInt() ?? 0,
        high: (json['high'] as num?)?.toInt() ?? 0,
        medium: (json['medium'] as num?)?.toInt() ?? 0,
        low: (json['low'] as num?)?.toInt() ?? 0,
        info: (json['info'] as num?)?.toInt() ?? 0,
      );
}
