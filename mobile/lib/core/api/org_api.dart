import 'package:dio/dio.dart';
import 'api_client.dart';

class OrgUser {
  const OrgUser({
    required this.id,
    required this.email,
    required this.role,
    this.isActive = true,
    this.orgName,
    this.orgId,
    this.isPlatformAdmin = false,
  });

  final String id;
  final String email;
  final String role;
  final bool isActive;
  final String? orgName;
  final String? orgId;
  final bool isPlatformAdmin;

  String get displayName {
    final local = email.split('@').first;
    return local.replaceAll(RegExp(r'[._\-]'), ' ');
  }

  String get initials {
    final parts = displayName.trim().split(' ');
    if (parts.length >= 2 && parts[1].isNotEmpty) {
      return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    }
    return email.isNotEmpty ? email[0].toUpperCase() : '?';
  }

  factory OrgUser.fromJson(Map<String, dynamic> json) => OrgUser(
        id: json['id'].toString(),
        email: json['email'] as String,
        role: json['role'] as String? ?? 'viewer',
        isActive: json['is_active'] as bool? ?? true,
        orgName: json['org_name'] as String?,
        orgId: json['org_id']?.toString(),
        isPlatformAdmin: json['is_platform_admin'] as bool? ?? false,
      );
}

class LlmUsageRow {
  const LlmUsageRow({
    required this.task,
    required this.provider,
    required this.inputTokens,
    required this.outputTokens,
    required this.costUsd,
    required this.calls,
  });

  final String task;
  final String provider;
  final int inputTokens;
  final int outputTokens;
  final double costUsd;
  final int calls;

  int get totalTokens => inputTokens + outputTokens;

  factory LlmUsageRow.fromJson(Map<String, dynamic> json) => LlmUsageRow(
        task: json['task'] as String,
        provider: json['provider'] as String,
        inputTokens: json['input_tokens'] as int? ?? 0,
        outputTokens: json['output_tokens'] as int? ?? 0,
        costUsd: (json['cost_usd'] as num?)?.toDouble() ?? 0.0,
        calls: json['calls'] as int? ?? 0,
      );
}

class OrgApi {
  OrgApi(this._client);
  final ApiClient _client;

  Future<List<OrgUser>> listUsers() async {
    final res = await _client.get<List<dynamic>>('/api/v1/org/users');
    return (res.data ?? [])
        .cast<Map<String, dynamic>>()
        .map(OrgUser.fromJson)
        .toList();
  }

  Future<OrgUser> updateUserRole(String userId, String role) async {
    final res = await _client.patch<Map<String, dynamic>>(
      '/api/v1/org/users/$userId/role',
      data: {'role': role},
    );
    return OrgUser.fromJson(res.data!);
  }

  Future<Map<String, dynamic>> invite(String role) async {
    final res = await _client.post<Map<String, dynamic>>(
      '/api/v1/org/invite',
      data: {'role': role},
    );
    return res.data ?? {};
  }

  Future<Map<String, dynamic>> getUsage() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/org/llm/usage');
    return res.data ?? {};
  }

  Future<Map<String, dynamic>> getBudget() async {
    try {
      final res = await _client.get<Map<String, dynamic>>('/api/v1/org/llm/budget');
      return res.data ?? {};
    } on DioException catch (e) {
      if (e.response?.statusCode == 403 || e.response?.statusCode == 404) {
        return {};
      }
      rethrow;
    }
  }

  // Super-admin endpoints
  Future<List<OrgUser>> listAllUsers() async {
    final res = await _client.get<List<dynamic>>('/api/v1/admin/users');
    return (res.data ?? [])
        .cast<Map<String, dynamic>>()
        .map(OrgUser.fromJson)
        .toList();
  }

  Future<OrgUser> setUserRole(String userId, String role) async {
    final res = await _client.patch<Map<String, dynamic>>(
      '/api/v1/admin/users/$userId/role',
      data: {'role': role},
    );
    return OrgUser.fromJson(res.data!);
  }
}
