enum FindingSeverity { critical, high, medium, low, info }
enum FindingStatus { open, inProgress, remediated, accepted, falsePositive }

class Finding {
  const Finding({
    required this.id,
    required this.title,
    required this.severity,
    required this.status,
    required this.engagementId,
    required this.createdAt,
    this.description,
    this.cvssScore,
    this.cweId,
    this.cveId,
    this.affectedAsset,
    this.remediationNote,
    this.updatedAt,
    this.vulnerabilityClass,
    this.affectedSurface,
    this.evidence = const [],
    this.reproductionSteps = const [],
    this.recommendation,
    this.confidenceScore,
    this.findingType = 'regular',
    this.chainSteps,
    this.componentFindingIds,
    this.isFalsePositive = false,
    this.agentType,
    this.triageStatus,
    this.triageNotes,
  });

  final String id;
  final String title;
  final FindingSeverity severity;
  final FindingStatus status;
  final String engagementId;
  final DateTime createdAt;
  final String? description;
  final double? cvssScore;
  final String? cweId;
  final String? cveId;
  final String? affectedAsset;
  final String? remediationNote;
  final DateTime? updatedAt;
  final String? vulnerabilityClass;
  final String? affectedSurface;
  final List<dynamic> evidence;
  final List<dynamic> reproductionSteps;
  final String? recommendation;
  final double? confidenceScore;
  final String findingType;
  final List<String>? chainSteps;
  final List<String>? componentFindingIds;
  final bool isFalsePositive;
  final String? agentType;
  final String? triageStatus;
  final String? triageNotes;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'severity': severity.name,
        'status': _statusName(status),
        'engagement_id': engagementId,
        'created_at': createdAt.toIso8601String(),
        'description': description,
        'cvss_score': cvssScore,
        'cwe_id': cweId,
        'cve_id': cveId,
        'affected_asset': affectedAsset,
        'remediation_note': remediationNote,
        'updated_at': updatedAt?.toIso8601String(),
        'vulnerability_class': vulnerabilityClass,
        'affected_surface': affectedSurface,
        'evidence': evidence,
        'reproduction_steps': reproductionSteps,
        'recommendation': recommendation,
        'confidence_score': confidenceScore,
        'finding_type': findingType,
        'chain_steps': chainSteps,
        'component_finding_ids': componentFindingIds,
        'triage_status': triageStatus ?? (isFalsePositive ? 'false_positive' : null),
        'agent_type': agentType,
        'triage_notes': triageNotes,
      };

  static String _statusName(FindingStatus s) => switch (s) {
        FindingStatus.inProgress => 'in_progress',
        FindingStatus.remediated => 'remediated',
        FindingStatus.accepted => 'accepted',
        FindingStatus.falsePositive => 'false_positive',
        _ => 'open',
      };

  factory Finding.fromJson(Map<String, dynamic> json) {
    final ts = json['triage_status'] as String?;
    final isFP = ts == 'false_positive' || (json['is_false_positive'] as bool? ?? false);

    return Finding(
      id: json['id'] as String,
      title: json['title'] as String,
      severity: _parseSeverity(json['severity'] as String? ?? 'info'),
      status: _parseStatus(json['status'] as String? ?? ts ?? 'open'),
      engagementId: json['engagement_id'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      description: json['description'] as String?,
      cvssScore: (json['cvss_score'] as num?)?.toDouble(),
      cweId: json['cwe_id'] as String?,
      cveId: json['cve_id'] as String?,
      affectedAsset: json['affected_asset'] as String? ?? json['affected_surface'] as String?,
      remediationNote: json['remediation_note'] as String? ?? json['recommendation'] as String?,
      updatedAt: json['updated_at'] != null ? DateTime.parse(json['updated_at'] as String) : null,
      vulnerabilityClass: json['vulnerability_class'] as String?,
      affectedSurface: json['affected_surface'] as String?,
      evidence: (json['evidence'] as List<dynamic>?) ?? const [],
      reproductionSteps: (json['reproduction_steps'] as List<dynamic>?) ?? const [],
      recommendation: json['recommendation'] as String?,
      confidenceScore: (json['confidence_score'] as num?)?.toDouble(),
      findingType: json['finding_type'] as String? ?? 'regular',
      chainSteps: (json['chain_steps'] as List<dynamic>?)?.cast<String>(),
      componentFindingIds: (json['component_finding_ids'] as List<dynamic>?)?.cast<String>(),
      isFalsePositive: isFP,
      agentType: json['agent_type'] as String?,
      triageStatus: ts,
      triageNotes: json['triage_notes'] as String?,
    );
  }

  static FindingSeverity _parseSeverity(String v) => switch (v) {
        'critical' => FindingSeverity.critical,
        'high' => FindingSeverity.high,
        'medium' => FindingSeverity.medium,
        'low' => FindingSeverity.low,
        _ => FindingSeverity.info,
      };

  static FindingStatus _parseStatus(String v) => switch (v) {
        'in_progress' => FindingStatus.inProgress,
        'remediated' => FindingStatus.remediated,
        'accepted' => FindingStatus.accepted,
        'false_positive' => FindingStatus.falsePositive,
        _ => FindingStatus.open,
      };

  bool get isOpen => status == FindingStatus.open || status == FindingStatus.inProgress;
  bool get isChain => findingType == 'chain';
}
