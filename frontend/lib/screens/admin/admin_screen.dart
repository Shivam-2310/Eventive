import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import 'audit_log_screen.dart';
import 'ingest_screen.dart';
import 'missions_admin_screen.dart';
import 'pulse_screen.dart';

/// Admin console hub — routes to Pulse dashboard, Ingest tool, Audit log,
/// and the Mission builder. Only reachable when [Session.adminMode] is true
/// or the current user's `is_admin` flag is set.
class AdminScreen extends StatelessWidget {
  const AdminScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = ServiceScope.of(context).session;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Admin console',
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
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.accentLight,
              borderRadius: AppRadius.borderLg,
              border: Border.all(color: AppColors.accent.withValues(alpha: 0.2)),
            ),
            child: Row(
              children: [
                Icon(Icons.shield_moon_rounded, color: AppColors.accentDark),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Admin endpoints are open in dev. Handle with care.',
                    style: TextStyle(
                        color: AppColors.accentDark, fontSize: 12.5),
                  ),
                ),
                Switch(
                  value: session.adminMode,
                  activeThumbColor: AppColors.accent,
                  onChanged: (v) => session.setAdminMode(v),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _tile(context, Icons.dashboard_rounded, 'Live pulse',
              'Realtime stats over WebSocket.', const PulseScreen()),
          _tile(context, Icons.cloud_upload_rounded, 'Ingestion',
              'Upload events / speakers / bundle JSON.', const IngestScreen()),
          _tile(context, Icons.flag_rounded, 'Missions builder',
              'Create a new mission.', const MissionsAdminScreen()),
          _tile(context, Icons.receipt_long_rounded, 'Audit log',
              'Latest 100 audit rows.', const AuditLogScreen()),
        ],
      ),
    );
  }

  Widget _tile(BuildContext context, IconData icon, String title,
      String subtitle, Widget screen) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.borderLight),
      ),
      child: ListTile(
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: Container(
          width: 40,
          height: 40,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.accentLight,
            borderRadius: AppRadius.borderMd,
          ),
          child: Icon(icon, color: AppColors.accentDark, size: 20),
        ),
        title: Text(title,
            style: const TextStyle(
                fontWeight: FontWeight.w700, color: AppColors.textPrimary)),
        subtitle: Text(subtitle,
            style: TextStyle(color: AppColors.textTertiary, fontSize: 12.5)),
        trailing:
            const Icon(Icons.chevron_right_rounded, color: AppColors.textTertiary),
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => screen)),
      ),
    );
  }
}
