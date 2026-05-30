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
        '/api/v1/auth/login',
        data: {'email': email, 'password': password},
      );
      final token = (res.data!['access_token'] as String?) ?? '';
      await SecureStorage.instance.saveToken(token);
      try {
        final user = await me();
        return AuthResponse(token: token, user: user);
      } catch (_) {
        await SecureStorage.instance.deleteToken();
        rethrow;
      }
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  Future<AuthResponse> register(String email, String password, String orgName) async {
    try {
      final res = await _client.post<Map<String, dynamic>>(
        '/api/v1/auth/register',
        data: {'email': email, 'password': password, 'org_name': orgName},
      );
      final token = (res.data!['access_token'] as String?) ?? '';
      await SecureStorage.instance.saveToken(token);
      try {
        final user = await me();
        return AuthResponse(token: token, user: user);
      } catch (_) {
        await SecureStorage.instance.deleteToken();
        rethrow;
      }
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
      final res = await _client.get<Map<String, dynamic>>('/api/v1/auth/me');
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

  AuthException _mapError(DioException e) {
    final status = e.response?.statusCode;
    final body = e.response?.data as Map<String, dynamic>?;
    final message = body?['detail'] as String?
        ?? body?['message'] as String?
        ?? body?['error'] as String?
        ?? e.message
        ?? 'Connection failed';
    return AuthException(message, statusCode: status);
  }
}
