package org.example.niannian.feature.conversation

import org.junit.Assert.*
import org.junit.Test

class ConversationVoiceTest {
    @Test fun completeCommandsAcceptAsrWhitespaceAndSentenceEndings() {
        for ((input, command) in listOf(
            "  请再说一遍。  " to VoiceCommand.REPEAT,
            "再读一遍" to VoiceCommand.REPEAT,
            "说慢一点！" to VoiceCommand.SLOWER,
            "恢复正常语速。" to VoiceCommand.NORMAL_SPEED,
            "停一下！" to VoiceCommand.STOP,
            "不要说了" to VoiceCommand.STOP,
            "结束聊天。" to VoiceCommand.END,
        )) assertEquals(input, command, voiceCommand(input))
    }

    @Test fun questionsNegationsQuotationsAndLongerSpeechRemainOrdinaryInput() {
        for (input in listOf("慢一点？", "停一下吗", "能再说一遍吗", "不要再说一遍",
            "女儿说慢一点", "“停一下”", "他说：结束聊天", "我走得慢一点", "如果我说停一下",
            "停一下，帮我叫人", "再说一遍，今天几号", "今天少打扰我", "", "   ")) {
            assertNull(input, voiceCommand(input))
        }
    }
}
