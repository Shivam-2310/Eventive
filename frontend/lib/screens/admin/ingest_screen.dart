import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/ingestion.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

/// Admin CSV/JSON uploads (§8). Kicks off a job then polls `/ingest/jobs` for
/// status until it hits a terminal state.
class IngestScreen extends StatefulWidget {
  const IngestScreen({super.key});

  @override
  State<IngestScreen> createState() => _IngestScreenState();
}

class _IngestScreenState extends State<IngestScreen> {
  List<IngestionJobRead> _jobs = const [];
  bool _loading = true;
  Timer? _poll;
  bool _uploading = false;
  bool _hydrated = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
      _poll = Timer.periodic(const Duration(seconds: 3), (_) => _load());
    }
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final list = await ServiceScope.of(context).ingest.jobs();
      if (!mounted) return;
      setState(() {
        _jobs = list;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickAndUpload(String kind) async {
    if (_uploading) return;
    final services = ServiceScope.of(context);
    final res = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: kind == 'json' ? ['json'] : ['csv'],
      withData: true,
    );
    if (res == null || res.files.isEmpty) return;
    final f = res.files.first;
    final bytes = f.bytes;
    if (bytes == null) return;
    setState(() => _uploading = true);
    try {
      switch (kind) {
        case 'events':
          await services.ingest
              .uploadEventsCsv(bytes: bytes, filename: f.name);
          break;
        case 'speakers':
          await services.ingest
              .uploadSpeakersCsv(bytes: bytes, filename: f.name);
          break;
        case 'json':
          await services.ingest.uploadJson(bytes: bytes, filename: f.name);
          break;
      }
      if (!mounted) return;
      showInfoSnack(context, 'Job queued');
      _load();
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Ingestion',
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
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: [
            Row(
              children: [
                Expanded(
                  child: _uploadCard(
                    icon: Icons.event_note_rounded,
                    label: 'Events CSV',
                    onTap: () => _pickAndUpload('events'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _uploadCard(
                    icon: Icons.record_voice_over_rounded,
                    label: 'Speakers CSV',
                    onTap: () => _pickAndUpload('speakers'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _uploadCard(
                    icon: Icons.data_object_rounded,
                    label: 'Bundle JSON',
                    onTap: () => _pickAndUpload('json'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            const Text(
              'Recent jobs',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary),
            ),
            const SizedBox(height: 12),
            if (_loading && _jobs.isEmpty)
              const Center(child: CircularProgressIndicator(color: AppColors.accent))
            else if (_jobs.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 40),
                child: Center(
                  child: Text('No jobs yet.',
                      style: TextStyle(color: AppColors.textTertiary)),
                ),
              )
            else
              ..._jobs.map(_jobTile),
          ],
        ),
      ),
    );
  }

  Widget _uploadCard({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: _uploading ? null : onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 12),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: AppRadius.borderLg,
          border: Border.all(color: AppColors.borderLight),
        ),
        child: Column(
          children: [
            Icon(icon, color: AppColors.accent),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _jobTile(IngestionJobRead j) {
    final subtitle = j.stats == null
        ? (j.error ?? j.status)
        : j.stats!.entries.map((e) => '${e.key}=${e.value}').join(' · ');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: _statusColor(j.status).withValues(alpha: 0.15),
              borderRadius: AppRadius.borderMd,
            ),
            child: Icon(_statusIcon(j.status),
                color: _statusColor(j.status), size: 18),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${j.sourceType} · ${j.filename ?? '(no filename)'}',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 11.5,
                  ),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Text(
                  DateFormat('MMM d · h:mm a').format(j.createdAt.toLocal()),
                  style: TextStyle(
                    color: AppColors.textTertiary,
                    fontSize: 10.5,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: _statusColor(j.status).withValues(alpha: 0.15),
              borderRadius: AppRadius.borderFull,
            ),
            child: Text(
              j.status,
              style: TextStyle(
                color: _statusColor(j.status),
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  IconData _statusIcon(String status) {
    switch (status) {
      case 'success':
        return Icons.check_rounded;
      case 'failed':
        return Icons.error_rounded;
      case 'running':
        return Icons.autorenew_rounded;
      default:
        return Icons.schedule_rounded;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'success':
        return AppColors.accent;
      case 'failed':
        return AppColors.error;
      case 'running':
        return const Color(0xFF2563EB);
      default:
        return AppColors.textTertiary;
    }
  }
}
