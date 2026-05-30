import 'dart:convert';
import 'package:hive_flutter/hive_flutter.dart';
import '../models/engagement.dart';
import '../models/finding.dart';

class CacheStorage {
  CacheStorage._();
  static final CacheStorage instance = CacheStorage._();

  static const _boxEngagements = 'engagements';
  static const _keyList = 'list';

  Future<void> saveEngagements(List<Engagement> items) async {
    final box = await Hive.openBox(_boxEngagements);
    await box.put(_keyList, jsonEncode(items.map((e) => e.toJson()).toList()));
    await box.put('ts', DateTime.now().toIso8601String());
  }

  Future<List<Engagement>?> getEngagements() async {
    final box = await Hive.openBox(_boxEngagements);
    final raw = box.get(_keyList) as String?;
    if (raw == null) return null;
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list
          .map((e) => Engagement.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return null;
    }
  }

  Future<void> saveFindings(String engagementId, List<Finding> items) async {
    final box = await Hive.openBox('findings_$engagementId');
    await box.put(_keyList, jsonEncode(items.map((e) => e.toJson()).toList()));
    await box.put('ts', DateTime.now().toIso8601String());
  }

  Future<List<Finding>?> getFindings(String engagementId) async {
    final box = await Hive.openBox('findings_$engagementId');
    final raw = box.get(_keyList) as String?;
    if (raw == null) return null;
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list
          .map((e) => Finding.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return null;
    }
  }

  Future<void> clearEngagement(String id) async {
    await Hive.deleteBoxFromDisk('findings_$id');
  }

  Future<void> clear() async {
    await Hive.deleteBoxFromDisk(_boxEngagements);
  }
}
