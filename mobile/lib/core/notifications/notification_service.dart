import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/api_client.dart';
import '../api/auth_api.dart';

// Global navigator key — imported by app.dart and used by GoRouter.
final appNavigatorKey = GlobalKey<NavigatorState>();

// Notification preference keys (must match settings_screen.dart)
const _kNotifCritical = 'notif_critical_findings';
const _kNotifScanComplete = 'notif_scan_complete';
const _kNotifBudget = 'notif_budget_warnings';

// Android notification channel
const _channelId = 'forge_alerts';
const _channelName = 'FORGE Alerts';

class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  final _localNotif = FlutterLocalNotificationsPlugin();
  String? _pendingRoute;

  // ------------------------------------------------------------------
  // Step 1: init local notifications (called before Firebase init)
  // ------------------------------------------------------------------
  Future<void> initLocalNotifications() async {
    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings();
    await _localNotif.initialize(
      const InitializationSettings(android: androidInit, iOS: iosInit),
      onDidReceiveNotificationResponse: _onLocalNotifTap,
    );

    // Create Android notification channel
    const channel = AndroidNotificationChannel(
      _channelId,
      _channelName,
      importance: Importance.high,
    );
    await _localNotif
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);
  }

  // ------------------------------------------------------------------
  // Step 2: FCM setup (called after Firebase.initializeApp())
  // ------------------------------------------------------------------
  Future<void> setup() async {
    // Request iOS permission
    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    // Get FCM token and register with backend
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) {
      await _registerToken(token);
    }

    // Re-register when token refreshes
    FirebaseMessaging.instance.onTokenRefresh.listen(_registerToken);

    // Foreground messages → local notification
    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

    // App resumed from background via notification tap
    FirebaseMessaging.onMessageOpenedApp
        .listen((msg) => _navigate(_routeFromData(msg.data)));

    // App launched from terminated state via notification tap
    final initial = await FirebaseMessaging.instance.getInitialMessage();
    if (initial != null) {
      _pendingRoute = _routeFromData(initial.data);
    }
  }

  // After the first frame: navigate to any route from a cold-start tap
  void drainPendingRoute() {
    if (_pendingRoute == null) return;
    final route = _pendingRoute!;
    _pendingRoute = null;
    WidgetsBinding.instance.addPostFrameCallback((_) => _navigate(route));
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  Future<void> _registerToken(String token) async {
    try {
      await AuthApi(ApiClient.instance).registerFcmToken(token);
    } catch (e) {
      debugPrint('FCM token registration failed: $e');
    }
  }

  Future<void> _handleForegroundMessage(RemoteMessage message) async {
    final type = message.data['type'] as String?;
    if (!await _isNotifEnabled(type)) return;

    final notification = message.notification;
    final title = notification?.title ?? _defaultTitle(type);
    final body = notification?.body ?? '';
    final route = _routeFromData(message.data);

    await _localNotif.show(
      message.messageId?.hashCode ?? DateTime.now().millisecondsSinceEpoch % (1 << 30),
      title,
      body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: const DarwinNotificationDetails(),
      ),
      payload: route,
    );
  }

  void _onLocalNotifTap(NotificationResponse response) {
    final route = response.payload;
    if (route != null && route.isNotEmpty) {
      _navigate(route);
    }
  }

  void _navigate(String route) {
    final ctx = appNavigatorKey.currentContext;
    if (ctx != null) ctx.go(route);
  }

  // Map notification data to an app route
  String _routeFromData(Map<String, dynamic> data) {
    final type = data['type'] as String?;
    final engagementId = data['engagement_id'] as String?;

    return switch (type) {
      'critical_finding' when engagementId != null =>
        '/engagement/$engagementId/findings',
      'scan_complete' when engagementId != null => '/engagement/$engagementId',
      'scan_failed' when engagementId != null => '/engagement/$engagementId',
      'budget_warning' => '/settings',
      _ => '/home',
    };
  }

  // Check notification preference for this type
  Future<bool> _isNotifEnabled(String? type) async {
    final prefs = await SharedPreferences.getInstance();
    return switch (type) {
      'critical_finding' => prefs.getBool(_kNotifCritical) ?? true,
      'scan_complete' || 'scan_failed' => prefs.getBool(_kNotifScanComplete) ?? true,
      'budget_warning' => prefs.getBool(_kNotifBudget) ?? false,
      _ => true,
    };
  }

  String _defaultTitle(String? type) => switch (type) {
        'critical_finding' => 'Critical finding detected',
        'scan_complete' => 'Scan complete',
        'scan_failed' => 'Scan failed',
        'budget_warning' => 'Budget warning',
        _ => 'FORGE',
      };
}
