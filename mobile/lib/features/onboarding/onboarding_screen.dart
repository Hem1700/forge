import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/storage/secure_storage.dart';
import '../../core/theme/app_theme.dart';

const _demoServer = 'https://demo.forge.security';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _urlController = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _connect(String rawUrl) async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; });

    try {
      final url = _normalizeUrl(rawUrl.trim());
      final dio = Dio(BaseOptions(
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      ));
      final res = await dio.get<dynamic>('$url/health');
      if (res.statusCode == 200) {
        await SecureStorage.instance.saveServerUrl(url);
        await ApiClient.instance.init(url);
        if (mounted) context.go('/login');
      } else {
        setState(() => _error = 'Server returned unexpected status ${res.statusCode}');
      }
    } on DioException catch (e) {
      setState(() => _error = _friendlyDioError(e));
    } catch (e) {
      setState(() => _error = 'Could not connect: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _useDemoServer() async {
    _urlController.text = _demoServer;
    await _connect(_demoServer);
  }

  String _normalizeUrl(String url) {
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://$url';
    }
    return url.endsWith('/') ? url.substring(0, url.length - 1) : url;
  }

  String _friendlyDioError(DioException e) {
    return switch (e.type) {
      DioExceptionType.connectionTimeout => 'Connection timed out. Check the server address.',
      DioExceptionType.connectionError => 'Cannot reach server. Check the address and your network.',
      DioExceptionType.badResponse => 'Server responded with error ${e.response?.statusCode}.',
      _ => e.message ?? 'Connection failed',
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ForgeColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(height: 40),

                  // FORGE hex logo
                  _ForgeLogo(),

                  const SizedBox(height: 32),

                  // Title
                  const Text(
                    'FORGE',
                    style: TextStyle(
                      color: ForgeColors.accent,
                      fontSize: 32,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 6,
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'SECURITY PLATFORM',
                    style: TextStyle(
                      color: ForgeColors.textTertiary,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 4,
                    ),
                  ),

                  const SizedBox(height: 40),

                  const Text(
                    'Enter your server address to get started',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: ForgeColors.textSecondary, fontSize: 14, height: 1.5),
                  ),

                  const SizedBox(height: 24),

                  // Server URL field
                  TextFormField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    enableSuggestions: false,
                    style: const TextStyle(color: ForgeColors.textPrimary, fontSize: 15),
                    decoration: const InputDecoration(
                      hintText: 'https://forge.yourcompany.com',
                      prefixIcon: Icon(Icons.dns_outlined, size: 20),
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Please enter a server address';
                      final normalized = v.trim().startsWith('http') ? v.trim() : 'https://${v.trim()}';
                      final uri = Uri.tryParse(normalized);
                      if (uri == null || !uri.hasAuthority) return 'Enter a valid URL';
                      return null;
                    },
                    onFieldSubmitted: _loading ? null : _connect,
                  ),

                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: ForgeColors.error.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: ForgeColors.error.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: ForgeColors.error, size: 16),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _error!,
                              style: const TextStyle(color: ForgeColors.error, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],

                  const SizedBox(height: 20),

                  // Connect button
                  ForgeGlowButton(
                    label: 'Connect',
                    onPressed: _loading ? null : () => _connect(_urlController.text),
                    isLoading: _loading,
                  ),

                  const SizedBox(height: 12),

                  // Demo server ghost button
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton(
                      onPressed: _loading ? null : _useDemoServer,
                      child: const Text('Use demo server'),
                    ),
                  ),

                  const SizedBox(height: 40),

                  const Text(
                    'v1.0.0',
                    style: TextStyle(color: ForgeColors.textTertiary, fontSize: 11),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ForgeLogo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 80,
      height: 80,
      decoration: BoxDecoration(
        color: ForgeColors.accentBg,
        shape: BoxShape.circle,
        border: Border.all(color: ForgeColors.accentDim, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: ForgeColors.accent.withValues(alpha: 0.15),
            blurRadius: 30,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Center(
        child: CustomPaint(
          size: const Size(42, 42),
          painter: _HexMarkPainter(),
        ),
      ),
    );
  }
}

class _HexMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = ForgeColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final cx = size.width / 2;
    final cy = size.height / 2;
    final r = size.width / 2;

    // Hexagon
    final path = Path();
    for (var i = 0; i < 6; i++) {
      final angle = (i * 60 - 30) * (math.pi / 180);
      final x = cx + r * math.cos(angle);
      final y = cy + r * math.sin(angle);
      if (i == 0) { path.moveTo(x, y); } else { path.lineTo(x, y); }
    }
    path.close();
    canvas.drawPath(path, paint);

    // Inner "F" lettermark
    final fPaint = Paint()
      ..color = ForgeColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final left = cx - 7.0;
    final top = cy - 9.0;

    canvas.drawLine(Offset(left, top), Offset(left, top + 18), fPaint);
    canvas.drawLine(Offset(left, top), Offset(left + 11, top), fPaint);
    canvas.drawLine(Offset(left, top + 9), Offset(left + 8, top + 9), fPaint);
  }

  @override
  bool shouldRepaint(_HexMarkPainter old) => false;
}
