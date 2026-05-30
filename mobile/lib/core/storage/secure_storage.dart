import 'package:flutter/foundation.dart';
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
  Future<void> saveToken(String token) async {
    try {
      await _storage.write(key: _keyToken, value: token);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for saveToken: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_keyToken, token);
    }
  }

  Future<String?> getToken() async {
    try {
      return await _storage.read(key: _keyToken);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for getToken: $e');
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_keyToken);
    }
  }

  Future<void> deleteToken() async {
    try {
      await _storage.delete(key: _keyToken);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for deleteToken: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_keyToken);
    }
  }

  // API key
  Future<void> saveApiKey(String key) async {
    try {
      await _storage.write(key: _keyApiKey, value: key);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for saveApiKey: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_keyApiKey, key);
    }
  }

  Future<String?> getApiKey() async {
    try {
      return await _storage.read(key: _keyApiKey);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for getApiKey: $e');
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_keyApiKey);
    }
  }

  Future<void> deleteApiKey() async {
    try {
      await _storage.delete(key: _keyApiKey);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for deleteApiKey: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_keyApiKey);
    }
  }

  // Server URL
  Future<void> saveServerUrl(String url) async {
    try {
      await _storage.write(key: _keyServerUrl, value: url);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for saveServerUrl: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_keyServerUrl, url);
    }
  }

  Future<String?> getServerUrl() async {
    try {
      return await _storage.read(key: _keyServerUrl);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for getServerUrl: $e');
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_keyServerUrl);
    }
  }

  Future<void> deleteServerUrl() async {
    try {
      await _storage.delete(key: _keyServerUrl);
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for deleteServerUrl: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_keyServerUrl);
    }
  }

  Future<void> clearAll() async {
    try {
      await _storage.deleteAll();
    } catch (e) {
      debugPrint('SecureStorage: falling back to prefs for clearAll: $e');
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_keyToken);
      await prefs.remove(_keyApiKey);
      await prefs.remove(_keyServerUrl);
    }
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
