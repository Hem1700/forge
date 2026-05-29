import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:local_auth/local_auth.dart';
import '../../core/api/api_client.dart';
import '../../core/api/auth_api.dart';
import '../../core/storage/secure_storage.dart';
import '../../core/theme/app_theme.dart';
import '../../app.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _passwordVisible = false;
  bool _loading = false;
  String? _serverUrl;
  bool _biometricAvailable = false;

  late final AuthApi _authApi;
  final _localAuth = LocalAuthentication();

  @override
  void initState() {
    super.initState();
    _authApi = AuthApi(ApiClient.instance);
    _loadServerAndBiometric();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _loadServerAndBiometric() async {
    final url = await SecureStorage.instance.getServerUrl();
    final biometricEnabled = await SecureStorage.instance.getBiometricEnabled();
    bool canCheckBiometrics = false;
    try {
      canCheckBiometrics = await _localAuth.canCheckBiometrics;
    } catch (_) {}

    if (mounted) {
      setState(() {
        _serverUrl = url;
        _biometricAvailable = canCheckBiometrics && biometricEnabled;
      });
    }
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);

    try {
      final response = await _authApi.login(
        _emailController.text.trim(),
        _passwordController.text,
      );
      await SecureStorage.instance.saveToken(response.token);
      ref.read(authNotifierProvider).setAuthenticated();
      if (mounted) context.go('/home');
    } on AuthException catch (e) {
      _showError(e.message);
    } catch (e) {
      _showError('Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loginWithApiKey(String apiKey) async {
    setState(() => _loading = true);
    try {
      await _authApi.loginWithApiKey(apiKey);
      ref.read(authNotifierProvider).setAuthenticated();
      if (mounted) context.go('/home');
    } on AuthException catch (e) {
      _showError(e.message);
    } catch (e) {
      _showError('Invalid API key.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _biometricLogin() async {
    try {
      final didAuthenticate = await _localAuth.authenticate(
        localizedReason: 'Sign in to FORGE',
        options: const AuthenticationOptions(biometricOnly: true),
      );
      if (!didAuthenticate) return;

      setState(() => _loading = true);
      final user = await _authApi.me();
      if (user.id.isNotEmpty) {
        ref.read(authNotifierProvider).setAuthenticated();
        if (mounted) context.go('/home');
      }
    } on AuthException catch (e) {
      _showError(e.message);
    } catch (e) {
      _showError('Biometric sign-in failed.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showApiKeyDialog() {
    final controller = TextEditingController();
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('API Key'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Enter your FORGE API key',
              style: TextStyle(color: ForgeColors.textSecondary, fontSize: 13),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: controller,
              obscureText: true,
              autofocus: true,
              style: const TextStyle(
                color: ForgeColors.textPrimary,
                fontFamily: 'monospace',
                fontSize: 14,
              ),
              decoration: const InputDecoration(hintText: 'frg_xxxxxxxxxxxxxxxx'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              final key = controller.text.trim();
              if (key.isEmpty) return;
              Navigator.of(ctx).pop();
              _loginWithApiKey(key);
            },
            child: const Text('Sign in'),
          ),
        ],
      ),
    );
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: ForgeColors.error.withValues(alpha: 0.9),
      ),
    );
  }

  Future<void> _changeServer() async {
    await SecureStorage.instance.deleteServerUrl();
    if (mounted) context.go('/onboarding');
  }

  @override
  Widget build(BuildContext context) {
    final displayUrl = _serverUrl != null
        ? Uri.tryParse(_serverUrl!)?.host ?? _serverUrl!
        : '';

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
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 40),

                  // Header
                  const Text(
                    'Sign in',
                    style: TextStyle(
                      color: ForgeColors.textPrimary,
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'to $displayUrl',
                    style: const TextStyle(color: ForgeColors.textSecondary, fontSize: 15),
                  ),

                  const SizedBox(height: 36),

                  // Email field
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    textInputAction: TextInputAction.next,
                    style: const TextStyle(color: ForgeColors.textPrimary, fontSize: 15),
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      hintText: 'you@company.com',
                      prefixIcon: Icon(Icons.mail_outline, size: 20),
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Email is required';
                      if (!v.contains('@')) return 'Enter a valid email';
                      return null;
                    },
                  ),

                  const SizedBox(height: 14),

                  // Password field
                  TextFormField(
                    controller: _passwordController,
                    obscureText: !_passwordVisible,
                    textInputAction: TextInputAction.done,
                    style: const TextStyle(color: ForgeColors.textPrimary, fontSize: 15),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline, size: 20),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _passwordVisible ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                          size: 20,
                        ),
                        onPressed: () => setState(() => _passwordVisible = !_passwordVisible),
                      ),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Password is required';
                      return null;
                    },
                    onFieldSubmitted: _loading ? null : (_) => _login(),
                  ),

                  const SizedBox(height: 24),

                  // Sign in button
                  ForgeGlowButton(
                    label: 'Sign in',
                    onPressed: _loading ? null : _login,
                    isLoading: _loading,
                  ),

                  const SizedBox(height: 20),

                  // Divider
                  Row(
                    children: [
                      const Expanded(child: Divider()),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Text(
                          'or',
                          style: TextStyle(
                            color: ForgeColors.textTertiary,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      const Expanded(child: Divider()),
                    ],
                  ),

                  const SizedBox(height: 16),

                  // API key button
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _loading ? null : _showApiKeyDialog,
                      icon: const Icon(Icons.vpn_key_outlined, size: 18),
                      label: const Text('Use API key'),
                    ),
                  ),

                  // Biometric button (shown only when available + enabled)
                  if (_biometricAvailable) ...[
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: TextButton.icon(
                        onPressed: _loading ? null : _biometricLogin,
                        icon: const Icon(Icons.fingerprint, size: 22),
                        label: const Text('Use Face ID / Fingerprint'),
                        style: TextButton.styleFrom(
                          foregroundColor: ForgeColors.accent,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
                      ),
                    ),
                  ],

                  const SizedBox(height: 40),

                  // Server footer
                  Center(
                    child: Wrap(
                      alignment: WrapAlignment.center,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        const Icon(Icons.dns_outlined, size: 13, color: ForgeColors.textTertiary),
                        const SizedBox(width: 4),
                        Text(
                          displayUrl,
                          style: const TextStyle(color: ForgeColors.textTertiary, fontSize: 12),
                        ),
                        const SizedBox(width: 4),
                        GestureDetector(
                          onTap: _changeServer,
                          child: const Text(
                            'Change',
                            style: TextStyle(
                              color: ForgeColors.accent,
                              fontSize: 12,
                              decoration: TextDecoration.underline,
                              decorationColor: ForgeColors.accent,
                            ),
                          ),
                        ),
                      ],
                    ),
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
