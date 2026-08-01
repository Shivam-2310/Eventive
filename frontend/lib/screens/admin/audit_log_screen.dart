import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/pulse.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

class AuditLogScreen extends StatefulWidget {
  const AuditLogScreen({super.key});

  @override
  State<AuditLogScreen> createState() => _AuditLogScreenState();
}

class _AuditLogScreenState extends State<AuditLogScreen> {
  bool _loading = true;
  List<AuditLogEntry> _entries = const [];
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
    try {
      final list = await ServiceScope.of(context).admin.auditLog();
      if (!mounted) return;
      setState(() {
        _entries = list;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Audit log',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            )),
        backgroundColor: AppColors.background,
      ),
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: _load,
        child: _loading && _entries.isEmpty
            ? const Center(
                child: CircularProgressIndicator(color: AppColors.accent))
            : _entries.isEmpty
                ? ListView(
                    padding: const EdgeInsets.symmetric(vertical: 60),
                    children: [
                      Center(
                        child: Text('No audit entries yet.',
                            style: TextStyle(color: AppColors.textTertiary)),
                      ),
                    ],
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    itemCount: _entries.length,
                    itemBuilder: (_, i) => _tile(_entries[i]),
                  ),
      ),
    );
  }

  Widget _tile(AuditLogEntry e) {
    String? pretty;
    if (e.payload != null) {
      try {
        final parsed = jsonDecode(e.payload!);
        pretty = const JsonEncoder.withIndent('  ').convert(parsed);
      } catch (_) {
        pretty = e.payload;
      }
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.accentLight,
                  borderRadius: AppRadius.borderFull,
                ),
                child: Text(
                  e.action,
                  style: TextStyle(
                    color: AppColors.accentDark,
                    fontWeight: FontWeight.w700,
                    fontSize: 11,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '${e.targetType ?? '?'} · ${e.targetId ?? '?'}',
                style: TextStyle(
                    color: AppColors.textSecondary, fontSize: 12),
              ),
              const Spacer(),
              Text(
                DateFormat('MMM d · h:mm a').format(e.createdAt.toLocal()),
                style: TextStyle(color: AppColors.textTertiary, fontSize: 11),
              ),
            ],
          ),
          if (pretty != null && pretty.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: AppRadius.borderMd,
              ),
              child: Text(
                pretty,
                style: TextStyle(
                  fontFamily: 'monospace',
                  color: AppColors.textSecondary,
                  fontSize: 11.5,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
