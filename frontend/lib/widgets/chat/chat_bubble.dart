import 'package:flutter/material.dart';

import '../../models/ai_chat_message.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import 'chat_attachments.dart';
import 'chat_entity_refs.dart';

/// A single message in the Ask Flo chat.
///
/// The assistant bubble intentionally shows *only* prose — no `[event:5]`
/// tokens, no debug pills. Any events / people / speakers Flo mentions are
/// rendered as compact cards below the bubble via [ChatAttachmentsRow].
class ChatBubble extends StatelessWidget {
  final AiChatMessage message;

  const ChatBubble({super.key, required this.message});

  bool get _isUser => message.isUser;

  @override
  Widget build(BuildContext context) {
    // For user turns, keep the raw text (they wrote it). For assistant
    // turns, strip `[event:5]`/etc. tokens so the bubble reads as plain
    // prose while the cards below carry the entity references.
    final displayText = _isUser
        ? message.text
        : stripEntityTokens(message.text);
    final placeholder = message.text.isEmpty && message.streaming;
    return Padding(
      padding: EdgeInsets.only(
        left: _isUser ? 60 : AppSpacing.md,
        right: _isUser ? AppSpacing.md : 60,
        top: 3,
        bottom: 3,
      ),
      child: Row(
        mainAxisAlignment:
            _isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!_isUser) ...[
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  colors: AppColors.accentGradient,
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: const Icon(
                Icons.auto_awesome,
                size: 15,
                color: Colors.white,
              ),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment:
                  _isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: _isUser ? null : AppColors.surfaceVariant,
                    gradient: _isUser
                        ? const LinearGradient(
                            colors: AppColors.accentGradient,
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          )
                        : null,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(20),
                      topRight: const Radius.circular(20),
                      bottomLeft: Radius.circular(_isUser ? 20 : 6),
                      bottomRight: Radius.circular(_isUser ? 6 : 20),
                    ),
                  ),
                  child: Text(
                    placeholder ? '…' : displayText,
                    style: TextStyle(
                      fontSize: 15,
                      color: _isUser ? Colors.white : AppColors.textPrimary,
                      height: 1.45,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ),
                if (!_isUser) ChatAttachmentsRow(message: message),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
