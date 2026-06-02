import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../storage/secure_storage.dart';

class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  late final Dio _dio;
  bool _initialized = false;
  // Guards against multiple concurrent 401s each firing the callback and
  // triggering redundant GoRouter navigation events on the same build cycle.
  bool _authErrorPending = false;

  // Called once the server URL is known; also re-called on URL change.
  Future<void> init(String serverUrl) async {
    _authErrorPending = false;
    _dio = Dio(BaseOptions(
      baseUrl: serverUrl.endsWith('/') ? serverUrl.substring(0, serverUrl.length - 1) : serverUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await SecureStorage.instance.getToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        } else {
          final apiKey = await SecureStorage.instance.getApiKey();
          if (apiKey != null) {
            options.headers['X-API-Key'] = apiKey;
          }
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401 && !_authErrorPending) {
          _authErrorPending = true;
          await SecureStorage.instance.deleteToken();
          // Signal that re-auth is needed via the global auth state.
          // GoRouter redirect handles navigation on next build.
          _authErrorCallback?.call();
        }
        handler.next(error);
      },
    ));

    _initialized = true;
  }

  void Function()? _authErrorCallback;
  void setAuthErrorCallback(void Function() cb) => _authErrorCallback = cb;

  Dio get dio {
    assert(_initialized, 'ApiClient.init() must be called before using the client');
    return _dio;
  }

  // Opens a WebSocket to {serverUrl}{path}.
  // Auth token is injected as a query parameter (?token=...) because the
  // web_socket_channel package does not expose header injection cross-platform.
  // Phase 2: switch to dart:io WebSocket.connect on mobile for header support.
  Future<WebSocketChannel> connect(String path) async {
    assert(_initialized, 'ApiClient.init() must be called before connect');
    final wsBase = _dio.options.baseUrl.replaceFirst(RegExp(r'^http'), 'ws');
    var uri = Uri.parse('$wsBase$path');

    final token = await SecureStorage.instance.getToken();
    if (token != null) {
      uri = uri.replace(queryParameters: {...uri.queryParameters, 'token': token});
    } else {
      final apiKey = await SecureStorage.instance.getApiKey();
      if (apiKey != null) {
        uri = uri.replace(queryParameters: {...uri.queryParameters, 'api_key': apiKey});
      }
    }

    return WebSocketChannel.connect(uri);
  }

  // Convenience wrappers
  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? queryParams}) =>
      dio.get<T>(path, queryParameters: queryParams);

  Future<Response<T>> post<T>(String path, {Object? data}) =>
      dio.post<T>(path, data: data);

  Future<Response<T>> put<T>(String path, {Object? data}) =>
      dio.put<T>(path, data: data);

  Future<Response<T>> patch<T>(String path, {Object? data}) =>
      dio.patch<T>(path, data: data);

  Future<Response<T>> delete<T>(String path) => dio.delete<T>(path);
}
