import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../models/mission.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// Simple mission builder — creates via `POST /missions` (§15.1).
class MissionsAdminScreen extends StatefulWidget {
  const MissionsAdminScreen({super.key});

  @override
  State<MissionsAdminScreen> createState() => _MissionsAdminScreenState();
}

class _MissionsAdminScreenState extends State<MissionsAdminScreen> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _trackCtrl = TextEditingController();
  final _countCtrl = TextEditingController(text: '3');
  final _pointsCtrl = TextEditingController(text: '10');

  String _ruleType = missionRuleTypes.first;
  bool _saving = false;
  List<MissionRead> _existing = const [];
  bool _loading = true;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
    }
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _descCtrl.dispose();
    _trackCtrl.dispose();
    _countCtrl.dispose();
    _pointsCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final list = await ServiceScope.of(context).missions.list();
      if (!mounted) return;
      setState(() {
        _existing = list;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  Map<String, dynamic> _buildRule() {
    final count = int.tryParse(_countCtrl.text.trim()) ?? 1;
    switch (_ruleType) {
      case 'attend_track':
        return {
          'type': 'attend_track',
          'track': _trackCtrl.text.trim().isEmpty ? 'AI' : _trackCtrl.text.trim(),
          'count': count,
        };
      default:
        return {'type': _ruleType, 'count': count};
    }
  }

  Future<void> _submit() async {
    if (_saving) return;
    final title = _titleCtrl.text.trim();
    if (title.isEmpty) {
      showErrorSnack(context, 'Title is required');
      return;
    }
    setState(() => _saving = true);
    try {
      await ServiceScope.of(context).missions.create(
            title: title,
            description: _descCtrl.text.trim().isEmpty
                ? null
                : _descCtrl.text.trim(),
            rule: _buildRule(),
            points: int.tryParse(_pointsCtrl.text.trim()) ?? 10,
          );
      if (!mounted) return;
      showInfoSnack(context, 'Mission created');
      _titleCtrl.clear();
      _descCtrl.clear();
      _trackCtrl.clear();
      _load();
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Missions builder',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          TextField(
            controller: _titleCtrl,
            decoration: const InputDecoration(hintText: 'Title *'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _descCtrl,
            decoration: const InputDecoration(hintText: 'Description'),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: missionRuleTypes
                .map(
                  (t) => ChoiceChip(
                    label: Text(t),
                    selected: _ruleType == t,
                    onSelected: (_) => setState(() => _ruleType = t),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 10),
          if (_ruleType == 'attend_track')
            TextField(
              controller: _trackCtrl,
              decoration: const InputDecoration(hintText: 'Track (e.g. AI)'),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _countCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(hintText: 'Count'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _pointsCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(hintText: 'Points'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 50,
            child: ElevatedButton(
              onPressed: _saving ? null : _submit,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          color: Colors.white, strokeWidth: 2),
                    )
                  : const Text('Create mission'),
            ),
          ),
          const SizedBox(height: 28),
          const Text(
            'Existing missions',
            style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                color: AppColors.textPrimary),
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Center(child: CircularProgressIndicator(color: AppColors.accent))
          else if (_existing.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text('No missions yet.',
                  style: TextStyle(color: AppColors.textTertiary)),
            )
          else
            ..._existing.map(_missionTile),
        ],
      ),
    );
  }

  Widget _missionTile(MissionRead m) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  m.title,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary),
                ),
                if (m.description != null && m.description!.isNotEmpty)
                  Text(
                    m.description!,
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                Text(
                  m.rule.toString(),
                  style:
                      TextStyle(color: AppColors.textTertiary, fontSize: 11),
                ),
              ],
            ),
          ),
          Text(
            '${m.points} pts',
            style: TextStyle(
              color: AppColors.accent,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}
