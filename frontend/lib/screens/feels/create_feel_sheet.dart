import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/ui_errors.dart';

class CreateFeelSheet extends StatefulWidget {
  const CreateFeelSheet({super.key});

  @override
  State<CreateFeelSheet> createState() => _CreateFeelSheetState();
}

class _CreateFeelSheetState extends State<CreateFeelSheet> {
  PlatformFile? _picked;
  final _captionCtrl = TextEditingController();
  bool _uploading = false;

  @override
  void dispose() {
    _captionCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickVideo() async {
    try {
      final res = await FilePicker.platform.pickFiles(
        type: FileType.video,
        allowMultiple: false,
        withData: true,
      );
      if (res == null || res.files.isEmpty) return;
      setState(() => _picked = res.files.first);
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    }
  }

  Future<void> _post() async {
    if (_uploading) return;
    if (_picked == null) {
      showErrorSnack(context, 'Please choose a video first.');
      return;
    }
    final bytes = _picked!.bytes;
    if (bytes == null || bytes.isEmpty) {
      showErrorSnack(context, 'Empty video file.');
      return;
    }
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _uploading = true);
    try {
      await services.reels.upload(
        userId: userId,
        bytes: bytes,
        filename: _picked!.name,
        caption: _captionCtrl.text.trim().isEmpty
            ? null
            : _captionCtrl.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
      showInfoSnack(context, 'Uploading — it\'ll show up shortly');
    } catch (e) {
      if (!mounted) return;
      setState(() => _uploading = false);
      showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 12),
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: AppRadius.borderFull,
              ),
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Create a Feel',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Share a moment from Eventive. Up to ~10s vertical video.',
            style: TextStyle(fontSize: 13, color: AppColors.textTertiary),
          ),
          const SizedBox(height: 20),
          GestureDetector(
            onTap: _uploading ? null : _pickVideo,
            child: Container(
              height: 200,
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: AppRadius.borderXl,
                border: Border.all(
                    color: AppColors.borderLight, width: 1.5),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.accentLight,
                    ),
                    child: Icon(
                      _picked == null
                          ? Icons.videocam_rounded
                          : Icons.check_circle_rounded,
                      size: 28,
                      color: AppColors.accent,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _picked?.name ?? 'Tap to pick a video',
                    style: TextStyle(
                      fontSize: 14,
                      color: _picked == null
                          ? AppColors.textTertiary
                          : AppColors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (_picked != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      _humanSize(_picked!.size),
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _captionCtrl,
            maxLines: 3,
            maxLength: 500,
            enabled: !_uploading,
            decoration: InputDecoration(
              hintText: 'Add a caption...',
              fillColor: AppColors.surfaceVariant,
              filled: true,
              border: OutlineInputBorder(
                borderRadius: AppRadius.borderLg,
                borderSide: BorderSide.none,
              ),
            ),
          ),
          const SizedBox(height: 12),
          GestureDetector(
            onTap: _uploading ? null : _post,
            child: Container(
              height: 52,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: _uploading
                      ? [AppColors.surfaceMuted, AppColors.surfaceMuted]
                      : AppColors.accentGradient,
                ),
                borderRadius: AppRadius.borderFull,
                boxShadow: _uploading
                    ? []
                    : [
                        BoxShadow(
                          color: AppColors.accent.withValues(alpha: 0.3),
                          blurRadius: 16,
                          offset: const Offset(0, 6),
                        ),
                      ],
              ),
              child: Center(
                child: _uploading
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2.5,
                        ),
                      )
                    : Text(
                        'Post Feel',
                        style: GoogleFonts.plusJakartaSans(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
              ),
            ),
          ),
          SizedBox(
              height: MediaQuery.of(context).viewInsets.bottom + AppSpacing.md),
        ],
      ),
    );
  }

  String _humanSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
