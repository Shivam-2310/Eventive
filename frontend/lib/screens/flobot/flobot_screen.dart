import 'dart:async';

import 'package:flutter/material.dart';

import '../../app_shell.dart' show kAppHeaderHeight;
import '../../models/ai.dart';
import '../../models/ai_chat_message.dart';
import '../../services/services.dart';
import '../../theme/colors.dart';
import '../../theme/radius.dart';
import '../../theme/spacing.dart';
import '../../utils/haptics.dart';
import '../../utils/ui_errors.dart';
import '../../widgets/chat/chat_bubble.dart';
import '../../widgets/chat/quick_action_chip.dart';
import '../../widgets/chat/typing_indicator.dart';

/// Ask Flo — real streaming AI chat backed by `POST /ai/chat` (§14.2).
///
/// - Loads starter chips from `GET /ai/suggestions?user_id=…`.
/// - Streams SSE frames and appends `chunk` frames to the current assistant
///   bubble in real-time. Citations, SQL results, tool calls are displayed
///   as side-signals under the answer.
class FloBotScreen extends StatefulWidget {
  const FloBotScreen({super.key});

  @override
  State<FloBotScreen> createState() => _FloBotScreenState();
}

class _FloBotScreenState extends State<FloBotScreen> {
  final _messages = <AiChatMessage>[];
  final _textController = TextEditingController();
  final _scrollController = ScrollController();

  int _msgId = 0;
  int? _sessionId;
  bool _streaming = false;
  bool _hydrated = false;
  List<AiSuggestion> _suggestions = const [];
  bool _loadingSuggestions = false;
  StreamSubscription<AiChatFrame>? _sub;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hydrated) {
      _hydrated = true;
      _bootstrap();
    }
  }

  Future<void> _bootstrap() async {
    _addAssistantMessage(
      "Hey there! I'm Flo Bot — your AI guide to everything Flo. How can I help?",
      preloaded: true,
    );
    await _loadSuggestions();
  }

  Future<void> _loadSuggestions() async {
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;
    setState(() => _loadingSuggestions = true);
    try {
      final list = await services.ai.suggestions(userId);
      if (!mounted) return;
      setState(() {
        _suggestions = list;
        _loadingSuggestions = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingSuggestions = false);
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _addAssistantMessage(String text, {bool preloaded = false}) {
    setState(() {
      _messages.add(
        AiChatMessage(
          id: 'msg_${_msgId++}',
          role: AiChatRole.assistant,
          timestamp: DateTime.now(),
          text: text,
          streaming: false,
        ),
      );
    });
    _scrollToBottom();
  }

  Future<void> _send(String rawText) async {
    final text = rawText.trim();
    if (text.isEmpty || _streaming) return;
    AppHaptics.light();
    final services = ServiceScope.of(context);
    final userId = services.session.userId;
    if (userId == null) return;

    final userMsg = AiChatMessage(
      id: 'msg_${_msgId++}',
      role: AiChatRole.user,
      timestamp: DateTime.now(),
      text: text,
    );
    final assistantMsg = AiChatMessage(
      id: 'msg_${_msgId++}',
      role: AiChatRole.assistant,
      timestamp: DateTime.now(),
      streaming: true,
    );
    setState(() {
      _messages.add(userMsg);
      _messages.add(assistantMsg);
      _streaming = true;
    });
    _textController.clear();
    _scrollToBottom();

    _sub = services.ai
        .chat(userId: userId, message: text, sessionId: _sessionId)
        .listen(
      (frame) => _onFrame(assistantMsg, frame),
      onError: (Object e) {
        if (!mounted) return;
        setState(() {
          assistantMsg.streaming = false;
          if (assistantMsg.text.isEmpty) {
            assistantMsg.text = 'Something went wrong.';
          }
          _streaming = false;
        });
        showErrorSnack(context, e);
      },
      onDone: () {
        if (!mounted) return;
        setState(() {
          assistantMsg.streaming = false;
          _streaming = false;
        });
      },
      cancelOnError: true,
    );
  }

  void _onFrame(AiChatMessage assistant, AiChatFrame frame) {
    if (!mounted) return;
    setState(() {
      switch (frame.event) {
        case 'intent':
          assistant.intent = frame.data['intent']?.toString();
          break;
        case 'citation':
          assistant.citations.add(AiCitation.fromFrame(frame.data));
          break;
        case 'tool':
          assistant.toolResult = frame.data;
          break;
        case 'sql':
          assistant.sqlResult = frame.data;
          break;
        case 'chunk':
          final t = frame.data['text']?.toString() ?? '';
          assistant.text = '${assistant.text}$t';
          break;
        case 'done':
          final sid = frame.data['session_id'];
          if (sid is int) _sessionId = sid;
          assistant.streaming = false;
          break;
        default:
          break;
      }
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent + 100,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  bool get _showQuickActions =>
      !_streaming &&
      _messages.length <= 1 &&
      (_suggestions.isNotEmpty || _loadingSuggestions);

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    final topPadding = MediaQuery.of(context).padding.top;
    final extras = (_showQuickActions ? 1 : 0) + (_streaming ? 1 : 0);
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            controller: _scrollController,
            padding: EdgeInsets.only(top: topPadding + kAppHeaderHeight + 8, bottom: 8),
            itemCount: _messages.length + extras,
            itemBuilder: (context, index) {
              if (index < _messages.length) {
                return ChatBubble(message: _messages[index]);
              }
              if (_showQuickActions && index == _messages.length) {
                return _buildQuickActions();
              }
              return const TypingIndicator();
            },
          ),
        ),
        _buildInputBar(bottomInset),
      ],
    );
  }

  Widget _buildQuickActions() {
    if (_loadingSuggestions && _suggestions.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(left: 54, top: 8, bottom: 8),
        child: SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(
            color: AppColors.accent,
            strokeWidth: 2,
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(
        left: 54,
        right: AppSpacing.md,
        top: 6,
        bottom: 8,
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: _suggestions
            .map(
              (s) => QuickActionChip(
                label: s.prompt,
                onTap: () => _send(s.prompt),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildInputBar(double bottomInset) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        10,
        10,
        AppSpacing.md + bottomInset + 80,
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(
          top: BorderSide(color: AppColors.borderLight),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _textController,
              textInputAction: TextInputAction.send,
              enabled: !_streaming,
              onSubmitted: _send,
              style: const TextStyle(fontSize: 15),
              decoration: InputDecoration(
                hintText: _streaming ? 'Streaming…' : 'Ask Flo Bot anything...',
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                filled: true,
                fillColor: AppColors.surfaceVariant,
                border: OutlineInputBorder(
                  borderRadius: AppRadius.borderFull,
                  borderSide: BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: AppRadius.borderFull,
                  borderSide: BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: AppRadius.borderFull,
                  borderSide:
                      BorderSide(color: AppColors.accent.withValues(alpha: 0.4)),
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: _streaming ? null : () => _send(_textController.text),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: _streaming
                      ? [AppColors.surfaceMuted, AppColors.surfaceMuted]
                      : AppColors.accentGradient,
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                boxShadow: _streaming
                    ? []
                    : [
                        BoxShadow(
                          color: AppColors.accent.withValues(alpha: 0.3),
                          blurRadius: 12,
                          offset: const Offset(0, 4),
                        ),
                      ],
              ),
              child: const Icon(
                Icons.arrow_upward_rounded,
                color: Colors.white,
                size: 20,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
