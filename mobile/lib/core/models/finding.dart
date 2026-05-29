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

  factory Finding.fromJson(Map<String, dynamic> json) => Finding(
        id: json['id'] as String,
        title: json['title'] as String,
        severity: _parseSeverity(json['severity'] as String? ?? 'info'),
        status: _parseStatus(json['status'] as String? ?? 'open'),
        engagementId: json['engagement_id'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        description: json['description'] as String?,
        cvssScore: (json['cvss_score'] as num?)?.toDouble(),
        cweId: json['cwe_id'] as String?,
        cveId: json['cve_id'] as String?,
        affectedAsset: json['affected_asset'] as String?,
        remediationNote: json['remediation_note'] as String?,
        updatedAt: json['updated_at'] != null
            ? DateTime.parse(json['updated_at'] as String)
            : null,
      );

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
}
