import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '../../models/message.dart';
import '../../models/thread.dart';
import '../../services/services.dart';
import '../../services/ws_service.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/haptics.dart';
import '../../utils/ui_errors.dart';

/// Single-thread chat backed by:
///   - `GET /threads/{id}/messages` for history,
///   - `POST /threads/{id}/messages` to send,
///   - `WS /ws/chat` for live inbound messages,
///   - `POST /threads/{id}/attend-together(/{msg}/accept)` for the CTA.
class ChatScreen extends StatefulWidget {
  final ThreadRead thread;

  const ChatScreen({super.key, required this.thread});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _textCtrl = TextEditingController();
  final _scroll = ScrollController();
  final List<MessageRead> _messages = [];
  bool _loading = true;
  bool _sending = false;
  bool _hydrated = false;
  ReconnectingWebSocket? _ws;
  StreamSubscription<Map<String, dynamic>>? _wsSub;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _load();
      _openWs();
    }
  }

  @override
  void dispose() {
    _wsSub?.cancel();
    _ws?.close();
    _textCtrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loading = true);
    try {
      final list =
          await services.chat.listMessages(widget.thread.id, userId: userId);
      if (!mounted) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(list);
        _loading = false;
      });
      _scrollToBottom();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showErrorSnack(context, e);
    }
  }

  void _openWs() {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    final ws = services.ws.chatSocket(userId);
    _ws = ws;
    _wsSub = ws.frames.listen(_onWsFrame);
    ws.connect();
  }

  void _onWsFrame(Map<String, dynamic> frame) {
    if (frame['channel'] != 'chat') return;
    final data = frame['data'];
    if (data is! Map) return;
    final msg = MessageRead.fromJson(Map<String, dynamic>.from(data));
    if (msg.threadId != widget.thread.id) return;
    if (_messages.any((m) => m.id == msg.id)) return;
    setState(() => _messages.add(msg));
    _scrollToBottom();
  }

  Future<void> _send() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty || _sending) return;
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _sending = true);
    AppHaptics.light();
    try {
      final msg = await services.chat.sendMessage(
        widget.thread.id,
        userId: userId,
        body: text,
      );
      if (!mounted) return;
      setState(() {
        if (!_messages.any((m) => m.id == msg.id)) _messages.add(msg);
        _textCtrl.clear();
        _sending = false;
      });
      _scrollToBottom();
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      showErrorSnack(context, e);
    }
  }

  Future<void> _acceptAttend(MessageRead msg) async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    try {
      await services.chat.acceptAttendTogether(
        widget.thread.id,
        userId: userId,
        messageId: msg.id,
      );
      if (!mounted) return;
      showInfoSnack(context, 'Attending together — RSVP recorded.');
      _load();
    } catch (e) {
      if (!mounted) return;
      showErrorSnack(context, e);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent + 200,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final userId = ServiceScope.of(context).session.userId ?? -1;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          widget.thread.title ?? 'Thread #${widget.thread.id}',
          style: GoogleFonts.plusJakartaSans(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
          ),
        ),
        backgroundColor: AppColors.background,
      ),
      body: Column(
        children: [
          Expanded(
            child: _loading && _messages.isEmpty
                ? const Center(
                    child: CircularProgressIndicator(color: AppColors.accent))
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.md, vertical: 12),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) => _messageBubble(_messages[i], userId),
                  ),
          ),
          _buildComposer(),
        ],
      ),
    );
  }

  Widget _messageBubble(MessageRead m, int selfId) {
    if (m.isSystem) return _systemBubble(m);
    final isMe = m.senderId == selfId;
    if (m.isAttendTogetherInvite || m.isAttendTogetherAccepted) {
      return _attendTogetherBubble(m, isMe);
    }
    return Row(
      mainAxisAlignment: isMe ? MainAxisAlignment.end : MainAxisAlignment.start,
      children: [
        Flexible(
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isMe ? null : AppColors.surface,
              gradient: isMe
                  ? const LinearGradient(colors: AppColors.accentGradient)
                  : null,
              border: isMe ? null : Border.all(color: AppColors.borderLight),
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(18),
                topRight: const Radius.circular(18),
                bottomLeft: Radius.circular(isMe ? 18 : 4),
                bottomRight: Radius.circular(isMe ? 4 : 18),
              ),
            ),
            child: Column(
              crossAxisAlignment:
                  isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Text(
                  m.body ?? '',
                  style: TextStyle(
                    color: isMe ? Colors.white : AppColors.textPrimary,
                    fontSize: 14.5,
                    height: 1.35,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  DateFormat.jm().format(m.createdAt.toLocal()),
                  style: TextStyle(
                    color: isMe
                        ? Colors.white.withValues(alpha: 0.7)
                        : AppColors.textTertiary,
                    fontSize: 10.5,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _systemBubble(MessageRead m) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: AppColors.surfaceVariant,
            borderRadius: AppRadius.borderFull,
          ),
          child: Text(
            m.body ?? m.kind,
            style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
          ),
        ),
      ),
    );
  }

  Widget _attendTogetherBubble(MessageRead m, bool isMe) {
    final title = m.payload?['event_title']?.toString();
    final eventId = m.payload?['event_id'];
    final invite = m.isAttendTogetherInvite;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.accentLight,
        borderRadius: AppRadius.borderLg,
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.event_available_rounded,
                  size: 18, color: AppColors.accentDark),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  invite ? 'Attend together?' : 'Attending together!',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: AppColors.accentDark,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            title ?? 'Event #$eventId',
            style: const TextStyle(
              color: AppColors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (invite && !isMe) ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                icon: const Icon(Icons.check_rounded, size: 16),
                onPressed: () => _acceptAttend(m),
                label: const Text('Accept invite'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildComposer() {
    return Container(
      padding: const EdgeInsets.fromLTRB(AppSpacing.md, 8, 8, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.borderLight)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _textCtrl,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                enabled: !_sending,
                decoration: const InputDecoration(hintText: 'Message…'),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: _sending ? null : _send,
              child: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    colors: _sending
                        ? [AppColors.surfaceMuted, AppColors.surfaceMuted]
                        : AppColors.accentGradient,
                  ),
                ),
                child: _sending
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: CircularProgressIndicator(
                            color: Colors.white, strokeWidth: 2),
                      )
                    : const Icon(Icons.send_rounded, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
