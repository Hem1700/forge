import 'package:dio/dio.dart';
import '../models/user.dart';
import 'api_client.dart';
import '../storage/secure_storage.dart';

class AuthResponse {
  const AuthResponse({required this.token, required this.user});
  final String token;
  final User user;
}

class AuthException implements Exception {
  const AuthException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class AuthApi {
  AuthApi(this._client);
  final ApiClient _client;

  Future<AuthResponse> login(String email, String password) async {
    try {
      final res = await _client.post<Map<String, dynamic>>(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      return _parseAuthResponse(res.data!);
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  Future<AuthResponse> loginWithApiKey(String apiKey) async {
    try {
      // Store key temporarily so the interceptor sends it
      await SecureStorage.instance.saveApiKey(apiKey);
      final user = await me();
      return AuthResponse(token: '', user: user);
    } on DioException catch (e) {
      await SecureStorage.instance.deleteApiKey();
      throw _mapError(e);
    } catch (_) {
      await SecureStorage.instance.deleteApiKey();
      rethrow;
    }
  }

  Future<User> me() async {
    try {
      final res = await _client.get<Map<String, dynamic>>('/auth/me');
      return User.fromJson(res.data!);
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  Future<void> logout() async {
    try {
      await _client.post<void>('/auth/logout');
    } catch (_) {
      // Best-effort; always clear local storage
    } finally {
      await SecureStorage.instance.deleteToken();
      await SecureStorage.instance.deleteApiKey();
    }
  }

  AuthResponse _parseAuthResponse(Map<String, dynamic> data) {
    final token = data['token'] as String? ?? data['access_token'] as String? ?? '';
    final userJson = data['user'] as Map<String, dynamic>?;
    if (userJson == null) throw const AuthException('Invalid server response');
    return AuthResponse(token: token, user: User.fromJson(userJson));
  }

  AuthException _mapError(DioException e) {
    final status = e.response?.statusCode;
    final message = (e.response?.data as Map<String, dynamic>?)?['message'] as String?
        ?? (e.response?.data as Map<String, dynamic>?)?['error'] as String?
        ?? e.message
        ?? 'Connection failed';
    return AuthException(message, statusCode: status);
  }
}
