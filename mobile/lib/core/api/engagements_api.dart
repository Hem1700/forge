import 'dart:typed_data';
import 'package:dio/dio.dart';
import '../models/engagement.dart';
import '../models/finding.dart';
import 'api_client.dart';

class EngagementsApi {
  EngagementsApi(this._client);
  final ApiClient _client;

  Future<List<Engagement>> list() async {
    final res = await _client.get<List<dynamic>>('/api/v1/engagements/');
    return (res.data ?? [])
        .cast<Map<String, dynamic>>()
        .map(Engagement.fromJson)
        .toList();
  }

  Future<Engagement> get(String id) async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/engagements/$id');
    return Engagement.fromJson(res.data!);
  }

  Future<List<Finding>> findings(String engagementId, {String? severity, String? status}) async {
    final params = <String, dynamic>{};
    if (severity != null) params['severity'] = severity;
    if (status != null) params['status'] = status;

    final res = await _client.get<List<dynamic>>(
      '/api/v1/engagements/$engagementId/findings',
      queryParams: params.isEmpty ? null : params,
    );
    return (res.data ?? [])
        .cast<Map<String, dynamic>>()
        .map(Finding.fromJson)
        .toList();
  }

  Future<List<Finding>> getFindings(
    String engagementId, {
    String? severity,
    String? findingType,
  }) async {
    final all = await findings(engagementId);
    return all.where((f) {
      if (severity != null && f.severity.name != severity) return false;
      if (findingType != null && f.findingType != findingType) return false;
      return true;
    }).toList();
  }

  Future<void> markFalsePositive(String findingId, bool value) async {
    await _client.patch<dynamic>(
      '/api/v1/findings/$findingId/triage',
      data: {'status': value ? 'false_positive' : 'unreviewed'},
    );
  }

  Future<Uint8List> downloadReport(String engagementId) async {
    final res = await _client.dio.post<List<int>>(
      '/api/v1/engagements/$engagementId/report/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    return Uint8List.fromList(res.data!);
  }

  Future<Finding> getFinding(String engagementId, String findingId) async {
    final res = await _client.get<Map<String, dynamic>>(
      '/api/v1/engagements/$engagementId/findings/$findingId',
    );
    return Finding.fromJson(res.data!);
  }

  Future<Engagement> createEngagement({
    required String targetUrl,
    required String targetType,
    String? targetPath,
  }) async {
    final body = <String, dynamic>{
      'target_url': targetUrl,
      'target_type': targetType,
    };
    if (targetPath != null) body['target_path'] = targetPath;
    final res = await _client.post<Map<String, dynamic>>(
      '/api/v1/engagements/',
      data: body,
    );
    return Engagement.fromJson(res.data!);
  }

  Future<void> startEngagement(String id) async {
    await _client.post<dynamic>('/api/v1/engagements/$id/start');
  }

  Future<void> addOsTarget({
    required String engagementId,
    required String host,
    required int port,
    required String username,
    required String authType,
    String? keyMaterial,
  }) async {
    await _client.post<dynamic>(
      '/api/v1/engagements/$engagementId/os-target',
      data: {
        'host': host,
        'port': port,
        'username': username,
        'auth_type': authType,
        if (keyMaterial != null && keyMaterial.isNotEmpty) 'key_material': keyMaterial,
      },
    );
  }

  Future<List<Map<String, dynamic>>> getEvents(String engagementId) async {
    final res = await _client.get<List<dynamic>>(
      '/api/v1/engagements/$engagementId/events',
    );
    return (res.data ?? []).cast<Map<String, dynamic>>();
  }

  Future<void> uploadCodebaseZip(
    String engagementId,
    Uint8List bytes,
    String filename,
  ) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: filename),
    });
    await _client.dio.post(
      '/api/v1/engagements/$engagementId/upload-codebase',
      data: formData,
    );
  }
}

extension DioExceptionExt on DioException {
  bool get isConnectionError =>
      type == DioExceptionType.connectionError ||
      type == DioExceptionType.connectionTimeout;
}
