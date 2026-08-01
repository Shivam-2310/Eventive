import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../models/interest.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// Lets the user change their interest set via `PUT /users/{id}/interests`.
class EditInterestsScreen extends StatefulWidget {
  const EditInterestsScreen({super.key});

  @override
  State<EditInterestsScreen> createState() => _EditInterestsScreenState();
}

class _EditInterestsScreenState extends State<EditInterestsScreen> {
  bool _loading = true;
  bool _saving = false;
  List<InterestRead> _all = const [];
  final Set<int> _selected = <int>{};
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
    }
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loading = true);
    try {
      final r = await Future.wait([
        services.interests.list(),
        services.users.listInterests(userId),
      ]);
      if (!mounted) return;
      final all = r[0] as List<InterestRead>;
      final mine = r[1] as List<UserInterestRead>;
      setState(() {
        _all = all;
        _selected
          ..clear()
          ..addAll(mine.map((e) => e.interestId));
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  Future<void> _save() async {
    if (_saving) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _saving = true);
    try {
      await services.users.setInterests(userId, _selected.toList());
      if (!mounted) return;
      showInfoSnack(context, 'Interests saved');
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showErrorSnack(context, e);
    }
  }

  Map<String, List<InterestRead>> get _byCategory {
    final map = <String, List<InterestRead>>{};
    for (final i in _all) {
      map.putIfAbsent(i.category, () => []).add(i);
    }
    return map;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Interests',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent))
          : ListView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              children: [
                for (final entry in _byCategory.entries) ...[
                  Text(
                    entry.key.toUpperCase(),
                    style: TextStyle(
                      color: AppColors.textTertiary,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: entry.value.map(_chip).toList(),
                  ),
                  const SizedBox(height: 20),
                ],
                const SizedBox(height: 60),
              ],
            ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: SizedBox(
            height: 52,
            child: ElevatedButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          color: Colors.white, strokeWidth: 2),
                    )
                  : Text('Save (${_selected.length})'),
            ),
          ),
        ),
      ),
    );
  }

  Widget _chip(InterestRead interest) {
    final selected = _selected.contains(interest.id);
    return GestureDetector(
      onTap: () {
        setState(() {
          if (selected) {
            _selected.remove(interest.id);
          } else {
            _selected.add(interest.id);
          }
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? AppColors.accent : AppColors.surface,
          border: Border.all(
            color: selected ? AppColors.accent : AppColors.borderLight,
          ),
          borderRadius: AppRadius.borderFull,
        ),
        child: Text(
          interest.label,
          style: TextStyle(
            color: selected ? Colors.white : AppColors.textPrimary,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
