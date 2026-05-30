import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../core/api/engagements_api.dart';
import '../../core/theme/app_theme.dart';

enum _ModelTier { light, standard, heavy }

enum _CodebaseMode { github, zip }

enum _AuthMode { sshKey, password }

class NewScanScreen extends StatefulWidget {
  const NewScanScreen({super.key});

  @override
  State<NewScanScreen> createState() => _NewScanScreenState();
}

class _NewScanScreenState extends State<NewScanScreen>
    with SingleTickerProviderStateMixin {
  final _api = EngagementsApi(ApiClient.instance);
  late final TabController _tabs;
  bool _submitting = false;

  // Web
  final _webUrlCtrl = TextEditingController();
  final _webNameCtrl = TextEditingController();
  _ModelTier _tier = _ModelTier.standard;
  final _budgetCtrl = TextEditingController(text: '5.00');

  // OS
  final _osHostCtrl = TextEditingController();
  final _osPortCtrl = TextEditingController(text: '22');
  final _osUserCtrl = TextEditingController();
  final _osNameCtrl = TextEditingController();
  _AuthMode _authMode = _AuthMode.sshKey;
  final _osKeyCtrl = TextEditingController();
  final _osPassCtrl = TextEditingController();
  bool _showPass = false;

  // Codebase
  _CodebaseMode _codeMode = _CodebaseMode.github;
  final _ghUrlCtrl = TextEditingController();
  final _ghBranchCtrl = TextEditingController(text: 'main');
  final _codeNameCtrl = TextEditingController();
  PlatformFile? _zipFile;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabs.dispose();
    for (final c in [
      _webUrlCtrl, _webNameCtrl, _budgetCtrl,
      _osHostCtrl, _osPortCtrl, _osUserCtrl, _osNameCtrl, _osKeyCtrl, _osPassCtrl,
      _ghUrlCtrl, _ghBranchCtrl, _codeNameCtrl,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  void _err(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: ForgeColors.error),
    );
  }

  Future<void> _startWeb() async {
    final url = _webUrlCtrl.text.trim();
    if (url.isEmpty) { _err('Target URL is required'); return; }
    setState(() => _submitting = true);
    try {
      final eng = await _api.createEngagement(targetUrl: url, targetType: 'web');
      await _api.startEngagement(eng.id);
      if (mounted) context.pushReplacement('/engagement/${eng.id}');
    } catch (e) {
      if (mounted) _err(e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _startOs() async {
    final host = _osHostCtrl.text.trim();
    final user = _osUserCtrl.text.trim();
    if (host.isEmpty || user.isEmpty) { _err('Host and username are required'); return; }
    final keyMat = _authMode == _AuthMode.sshKey ? _osKeyCtrl.text.trim() : _osPassCtrl.text;
    if (keyMat.isEmpty) {
      _err(_authMode == _AuthMode.sshKey ? 'SSH key is required' : 'Password is required');
      return;
    }
    final port = int.tryParse(_osPortCtrl.text.trim()) ?? 22;
    setState(() => _submitting = true);
    try {
      final eng = await _api.createEngagement(targetUrl: host, targetType: 'os');
      await _api.addOsTarget(
        engagementId: eng.id,
        host: host,
        port: port,
        username: user,
        authType: _authMode == _AuthMode.sshKey ? 'key' : 'password',
        keyMaterial: keyMat,
      );
      if (mounted) context.pushReplacement('/engagement/${eng.id}');
    } catch (e) {
      if (mounted) _err(e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _startCodebase() async {
    setState(() => _submitting = true);
    try {
      if (_codeMode == _CodebaseMode.github) {
        final url = _ghUrlCtrl.text.trim();
        if (url.isEmpty) { _err('GitHub URL is required'); return; }
        final branch = _ghBranchCtrl.text.trim();
        final eng = await _api.createEngagement(
          targetUrl: url,
          targetType: 'github',
          targetPath: branch.isEmpty ? 'main' : branch,
        );
        await _api.startEngagement(eng.id);
        if (mounted) context.pushReplacement('/engagement/${eng.id}');
      } else {
        final zip = _zipFile;
        if (zip == null) { _err('Please select a ZIP file'); return; }
        final eng = await _api.createEngagement(targetUrl: zip.name, targetType: 'local_codebase');
        final bytes = zip.bytes ?? await zip.xFile.readAsBytes();
        await _api.uploadCodebaseZip(eng.id, bytes, zip.name);
        if (mounted) context.pushReplacement('/engagement/${eng.id}');
      }
    } catch (e) {
      if (mounted) _err(e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _pickZip() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['zip'],
      withData: true,
    );
    if (result != null && result.files.isNotEmpty) {
      setState(() => _zipFile = result.files.first);
    }
  }

  void _showTierSheet() {
    final cs = Theme.of(context).colorScheme;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: cs.surface,
      shape: RoundedRectangleBorder(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
        side: BorderSide(color: cs.outline),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            Container(
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: cs.onSurfaceVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Model tier',
                  style: TextStyle(color: cs.onSurface, fontSize: 16, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(height: 4),
            for (final t in _ModelTier.values)
              ListTile(
                title: Text(_tierLabel(t)),
                subtitle: Text(_tierDesc(t),
                  style: TextStyle(color: cs.onSurfaceVariant, fontSize: 12)),
                trailing: _tier == t
                    ? const Icon(Icons.check, color: ForgeColors.accent, size: 18)
                    : null,
                onTap: () { setState(() => _tier = t); Navigator.pop(ctx); },
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  static String _tierLabel(_ModelTier t) => switch (t) {
    _ModelTier.light => 'Light',
    _ModelTier.standard => 'Standard',
    _ModelTier.heavy => 'Heavy',
  };

  static String _tierDesc(_ModelTier t) => switch (t) {
    _ModelTier.light => 'Fastest, lowest cost. Good for quick recon.',
    _ModelTier.standard => 'Balanced depth and cost. Recommended.',
    _ModelTier.heavy => 'Most thorough. Highest cost.',
  };

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('New Scan'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [Tab(text: 'Web'), Tab(text: 'OS'), Tab(text: 'Codebase')],
          labelColor: ForgeColors.accent,
          unselectedLabelColor: cs.onSurfaceVariant,
          indicatorColor: ForgeColors.accent,
          dividerColor: cs.outline,
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [_buildWebTab(), _buildOsTab(), _buildCodebaseTab()],
      ),
    );
  }

  Widget _buildWebTab() {
    final cs = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label('Target URL'),
          const SizedBox(height: 6),
          TextField(
            controller: _webUrlCtrl,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              hintText: 'https://example.com',
              prefixIcon: Icon(Icons.link, size: 18),
            ),
          ),
          const SizedBox(height: 16),
          _label('Scan name (optional)'),
          const SizedBox(height: 6),
          TextField(
            controller: _webNameCtrl,
            decoration: const InputDecoration(hintText: 'My web scan'),
          ),
          const SizedBox(height: 16),
          _label('Model tier'),
          const SizedBox(height: 6),
          GestureDetector(
            onTap: _showTierSheet,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: cs.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: cs.outline),
              ),
              child: Row(
                children: [
                  Icon(Icons.memory, size: 16, color: cs.onSurfaceVariant),
                  const SizedBox(width: 10),
                  Text(_tierLabel(_tier),
                    style: TextStyle(color: cs.onSurface, fontSize: 14)),
                  const Spacer(),
                  Icon(Icons.expand_more, size: 16, color: cs.onSurfaceVariant),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          _label('Budget limit (\$)'),
          const SizedBox(height: 6),
          TextField(
            controller: _budgetCtrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(prefixText: '\$  ', hintText: '5.00'),
          ),
          const SizedBox(height: 32),
          ForgeGlowButton(
            label: '▶  Start scan',
            onPressed: _submitting ? null : _startWeb,
            isLoading: _submitting,
          ),
        ],
      ),
    );
  }

  Widget _buildOsTab() {
    final cs = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label('Host'),
          const SizedBox(height: 6),
          TextField(
            controller: _osHostCtrl,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(hintText: '192.168.1.100'),
          ),
          const SizedBox(height: 16),
          _label('Port'),
          const SizedBox(height: 6),
          TextField(
            controller: _osPortCtrl,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(hintText: '22'),
          ),
          const SizedBox(height: 16),
          _label('Username'),
          const SizedBox(height: 6),
          TextField(
            controller: _osUserCtrl,
            autocorrect: false,
            decoration: const InputDecoration(hintText: 'root'),
          ),
          const SizedBox(height: 16),
          _label('Auth type'),
          const SizedBox(height: 8),
          Row(
            children: [
              _ToggleBtn(
                label: 'SSH Key',
                selected: _authMode == _AuthMode.sshKey,
                onTap: () => setState(() => _authMode = _AuthMode.sshKey),
              ),
              const SizedBox(width: 8),
              _ToggleBtn(
                label: 'Password',
                selected: _authMode == _AuthMode.password,
                onTap: () => setState(() => _authMode = _AuthMode.password),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_authMode == _AuthMode.sshKey) ...[
            _label('SSH key'),
            const SizedBox(height: 6),
            TextField(
              controller: _osKeyCtrl,
              maxLines: 6,
              style: TextStyle(
                fontFamily: 'monospace', fontSize: 12, color: cs.onSurface,
              ),
              decoration: const InputDecoration(
                hintText: '-----BEGIN OPENSSH PRIVATE KEY-----\n...',
                alignLabelWithHint: true,
              ),
            ),
          ] else ...[
            _label('Password'),
            const SizedBox(height: 6),
            TextField(
              controller: _osPassCtrl,
              obscureText: !_showPass,
              decoration: InputDecoration(
                hintText: '••••••••',
                suffixIcon: IconButton(
                  icon: Icon(_showPass ? Icons.visibility_off : Icons.visibility, size: 18),
                  onPressed: () => setState(() => _showPass = !_showPass),
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          _label('Scan name (optional)'),
          const SizedBox(height: 6),
          TextField(
            controller: _osNameCtrl,
            decoration: const InputDecoration(hintText: 'Prod server'),
          ),
          const SizedBox(height: 32),
          ForgeGlowButton(
            label: '▶  Start scan',
            onPressed: _submitting ? null : _startOs,
            isLoading: _submitting,
          ),
        ],
      ),
    );
  }

  Widget _buildCodebaseTab() {
    final cs = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _ToggleBtn(
                label: 'GitHub URL',
                selected: _codeMode == _CodebaseMode.github,
                onTap: () => setState(() => _codeMode = _CodebaseMode.github),
              ),
              const SizedBox(width: 8),
              _ToggleBtn(
                label: 'Upload ZIP',
                selected: _codeMode == _CodebaseMode.zip,
                onTap: () => setState(() => _codeMode = _CodebaseMode.zip),
              ),
            ],
          ),
          const SizedBox(height: 20),
          if (_codeMode == _CodebaseMode.github) ...[
            _label('GitHub URL'),
            const SizedBox(height: 6),
            TextField(
              controller: _ghUrlCtrl,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: const InputDecoration(
                hintText: 'https://github.com/org/repo',
                prefixIcon: Icon(Icons.code, size: 18),
              ),
            ),
            const SizedBox(height: 16),
            _label('Branch'),
            const SizedBox(height: 6),
            TextField(
              controller: _ghBranchCtrl,
              autocorrect: false,
              decoration: const InputDecoration(hintText: 'main'),
            ),
          ] else ...[
            _label('ZIP file'),
            const SizedBox(height: 6),
            GestureDetector(
              onTap: _pickZip,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cs.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _zipFile != null
                        ? ForgeColors.accent.withValues(alpha: 0.4)
                        : cs.outline,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(Icons.upload_file,
                      color: _zipFile != null ? ForgeColors.accent : cs.onSurfaceVariant,
                      size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _zipFile?.name ?? 'Select ZIP file…',
                        style: TextStyle(
                          color: _zipFile != null ? cs.onSurface : cs.onSurfaceVariant,
                          fontSize: 14,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (_zipFile != null)
                      GestureDetector(
                        onTap: () => setState(() => _zipFile = null),
                        child: Icon(Icons.close, color: cs.onSurfaceVariant, size: 16),
                      ),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          _label('Scan name (optional)'),
          const SizedBox(height: 6),
          TextField(
            controller: _codeNameCtrl,
            decoration: const InputDecoration(hintText: 'My codebase'),
          ),
          const SizedBox(height: 32),
          ForgeGlowButton(
            label: '▶  Start scan',
            onPressed: _submitting ? null : _startCodebase,
            isLoading: _submitting,
          ),
        ],
      ),
    );
  }

  Widget _label(String text) => Text(
    text,
    style: TextStyle(
      color: Theme.of(context).colorScheme.onSurfaceVariant,
      fontSize: 13,
      fontWeight: FontWeight.w500,
    ),
  );
}

class _ToggleBtn extends StatelessWidget {
  const _ToggleBtn({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? ForgeColors.accentDim : cs.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: selected ? ForgeColors.accent.withValues(alpha: 0.4) : cs.outline,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? ForgeColors.accent : cs.onSurfaceVariant,
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}
