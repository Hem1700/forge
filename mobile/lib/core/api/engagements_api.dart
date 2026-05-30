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

  Future<Finding> getFinding(String engagementId, String findingId) async {
    final res = await _client.get<Map<String, dynamic>>(
      '/api/v1/engagements/$engagementId/findings/$findingId',
    );
    return Finding.fromJson(res.data!);
  }
}

extension DioExceptionExt on DioException {
  bool get isConnectionError =>
      type == DioExceptionType.connectionError ||
      type == DioExceptionType.connectionTimeout;
}
