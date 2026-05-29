import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _keyToken = 'forge_jwt_token';
const _keyApiKey = 'forge_api_key';
const _keyServerUrl = 'forge_server_url';
const _prefDarkMode = 'forge_dark_mode';
const _prefBiometricEnabled = 'forge_biometric_enabled';

// Dark mode values stored as strings in SharedPreferences
enum DarkModePreference { system, on, off }

class SecureStorage {
  SecureStorage._();
  static final SecureStorage instance = SecureStorage._();

  final _storage = const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  // JWT token
  Future<void> saveToken(String token) => _storage.write(key: _keyToken, value: token);
  Future<String?> getToken() => _storage.read(key: _keyToken);
  Future<void> deleteToken() => _storage.delete(key: _keyToken);

  // API key
  Future<void> saveApiKey(String key) => _storage.write(key: _keyApiKey, value: key);
  Future<String?> getApiKey() => _storage.read(key: _keyApiKey);
  Future<void> deleteApiKey() => _storage.delete(key: _keyApiKey);

  // Server URL
  Future<void> saveServerUrl(String url) => _storage.write(key: _keyServerUrl, value: url);
  Future<String?> getServerUrl() => _storage.read(key: _keyServerUrl);
  Future<void> deleteServerUrl() => _storage.delete(key: _keyServerUrl);

  Future<void> clearAll() async {
    await _storage.deleteAll();
  }

  // --- SharedPreferences (non-sensitive prefs) ---

  Future<DarkModePreference> getDarkMode() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_prefDarkMode) ?? 'system';
    return switch (value) {
      'on' => DarkModePreference.on,
      'off' => DarkModePreference.off,
      _ => DarkModePreference.system,
    };
  }

  Future<void> setDarkMode(DarkModePreference mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefDarkMode, mode.name);
  }

  Future<bool> getBiometricEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_prefBiometricEnabled) ?? false;
  }

  Future<void> setBiometricEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_prefBiometricEnabled, enabled);
  }
}
