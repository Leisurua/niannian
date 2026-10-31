package org.example.niannian.feature.conversation

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConversationModelTest {
    private val id = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private fun frame(sequence: Long, type: String = "session.ready", payload: JSONObject = JSONObject().put("voice_allowed", true), replyTo: Long? = null) =
        JSONObject().put("conversation_id", id).put("sequence", sequence).put("type", type).put("payload", payload)
            .apply { if (replyTo != null) put("in_reply_to", replyTo) }.toString()

    private class Voice : ConversationVoice {
        var partial: (String) -> Unit = {}
        var final: (String) -> Unit = {}
        var failure: (String) -> Unit = {}
        var started: () -> Unit = {}
        var finished: () -> Unit = {}
        var captured: () -> Unit = {}
        val spoken = mutableListOf<String>()
        val speechRates = mutableListOf<Boolean>()
        var stops = 0
        var finishes = 0
        override fun listen(partial: (String) -> Unit, final: (String) -> Unit, failed: (String) -> Unit, captured: () -> Unit) {
            this.partial = partial; this.final = final; failure = failed; this.captured = captured
        }
        override fun finishListening() { finishes++ }
        override fun speak(text: String, slow: Boolean, started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) {
            spoken.add(text); speechRates.add(slow); this.started = started; this.finished = finished; failure = failed
        }
        override fun stop() { stops++ }
        override fun close() { stop() }
    }

    private inner class Gateway : ConversationGateway {
        val sent = mutableListOf<JSONObject>()
        var listener: (String) -> Unit = {}
        var onClose: (Int) -> Unit = {}
        var closed = 0
        var failEnd = false
        var ends = 0
        var waitStatus: CompletableDeferred<Unit>? = null
        var immediateReady = false
        var failSend = false
        override suspend fun create(family: String) = id
        override suspend fun status(id: String): String { waitStatus?.await(); return "ACTIVE" }
        override suspend fun end(id: String) { ends++; if (failEnd) error("offline") }
        override suspend fun connect(id: String, message: (String) -> Unit, closed: (Int) -> Unit): ConversationSocket {
            listener = message; onClose = closed
            if (immediateReady) message(frame(1))
            return object : ConversationSocket {
                override fun send(text: String): Boolean { if (failSend) return false; sent.add(JSONObject(text)); return true }
                override fun close() { this@Gateway.closed++ }
            }
        }
    }

    @Test fun handshakeSendsOneStartAndNeverRepeatsItForSecondReady() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        gateway.listener(frame(2)); yield()
        assertEquals(listOf("session.start"), gateway.sent.map { it.getString("type") })
        model.clear()
    }

    @Test fun dailyVoiceInputCarriesSelectedCityAndTimezoneAndShowsRealSource() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this); val voice = Voice()
        model.bind("family", "elder"); model.setWeatherCity(1816670); model.attachVoice(voice)
        model.start(); yield(); gateway.listener(frame(1)); yield()
        model.voiceEntry(); voice.final("今天会下雨吗")
        val payload = gateway.sent.last().getJSONObject("payload")
        assertEquals("今天会下雨吗", payload.getString("text"))
        assertEquals(1816670, payload.getInt("weather_city_id"))
        assertEquals(java.time.ZoneId.systemDefault().id, payload.getString("timezone"))
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "今日预报降水概率75%。")
            .put("source_labels", org.json.JSONArray().put("Open-Meteo 今日预报")), gateway.sent.last().getLong("sequence"))); yield()
        assertEquals(listOf("Open-Meteo 今日预报"), model.state.value.messages.last().sourceLabels)
        assertEquals(listOf("今日预报降水概率75%。"), voice.spoken)
        model.bind("another-family", "elder")
        model.start(); yield(); gateway.listener(frame(3)); yield(); model.input("今天会下雨吗")
        assertFalse(gateway.sent.last().getJSONObject("payload").has("weather_city_id"))
        model.clear()
    }

    @Test fun successfulFeedbackSignalsReminderRefreshAndOldTurnsCannotSignalIt() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield(); gateway.listener(frame(1)); yield()
        model.input("第一项完成了")
        val pending = gateway.sent.last().getLong("sequence")
        model.interrupt()
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "旧确认").put("reminders_changed", true), pending)); yield()
        assertEquals(0L, model.state.value.reminderRevision)
        model.input("第一项完成了")
        gateway.listener(frame(3, "assistant.text", JSONObject().put("text", "已记录完成").put("reminders_changed", true),
            gateway.sent.last().getLong("sequence"))); yield()
        assertEquals(1L, model.state.value.reminderRevision)
        model.clear(); assertEquals(0L, model.state.value.reminderRevision)
    }

    @Test fun reconnectKeepsIncreasingClientSequenceAndIgnoresOldCallback() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        val oldClose = gateway.onClose
        gateway.onClose(0); yield()
        model.start(); yield()
        gateway.listener(frame(5)); yield()
        oldClose(4403); yield()
        assertTrue(model.state.value.connected)
        assertEquals(listOf(1L, 2L), gateway.sent.map { it.getLong("sequence") })
        model.clear()
    }

    @Test fun familyChangeAndClearRejectLateFrames() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family-a", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        val old = gateway.listener
        model.bind("family-b", "elder")
        old(frame(2, "assistant.text", JSONObject().put("text", "old private text"))); yield()
        assertEquals("family-b", model.state.value.family)
        assertEquals("", model.state.value.reply)
        assertFalse(model.state.value.connected)
        model.clear()
    }

    @Test fun malformedGapAndAuthorizationFailureClearDisplayedReply() = runBlocking {
        for (failure in listOf("gap", "json", "permission")) {
            val gateway = Gateway(); val model = ConversationModel(gateway, this)
            model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "fictional reply"))); yield()
            assertEquals("fictional reply", model.state.value.reply)
            when (failure) {
                "gap" -> gateway.listener(frame(4))
                "json" -> gateway.listener("invalid")
                else -> gateway.onClose(4403)
            }
            yield()
            assertEquals("", model.state.value.reply)
            assertFalse(model.state.value.connected)
            model.clear()
        }
    }

    @Test fun doubleInputAndControlsDoNotGenerateDuplicateTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("你好"); model.input("不应重发"); model.repeat(); model.slowDown()
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.interrupt()
        assertEquals("interrupt", gateway.sent.last().getString("type"))
        assertEquals("", model.state.value.reply)
        model.clear()
    }

    @Test fun endingUnknownResultRetainsSequenceForSafeReconnect() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        gateway.failEnd = true; model.end(); yield()
        model.start(); yield()
        gateway.listener(frame(3)); yield()
        assertEquals(2L, gateway.sent.last().getLong("sequence"))
        model.clear()
    }

    @Test fun delayedStartAcknowledgementDoesNotUnlockAnActiveTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("你好")
        gateway.listener(frame(2)); yield()
        assertTrue(model.state.value.busy)
        assertEquals("THINKING", model.state.value.state)
        model.input("不应重发")
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.clear()
    }

    @Test fun pendingStatusCannotRestoreOldFamilyAfterClear() = runBlocking {
        val gateway = Gateway(); val gate = CompletableDeferred<Unit>(); gateway.waitStatus = gate
        val model = ConversationModel(gateway, this)
        model.bind("family-a", "elder"); model.start(); yield()
        model.bind("family-b", "elder"); gate.complete(Unit); yield()
        assertEquals("family-b", model.state.value.family)
        assertEquals("", model.state.value.id)
        assertFalse(model.state.value.connected)
        model.clear()
    }

    @Test fun successfulEndKeepsOnlyCurrentRecapIdUntilClear() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        val id = model.state.value.id
        model.end(); model.awaitIdle()
        assertEquals(id, model.state.value.recapId)
        assertEquals("", model.state.value.reply)
        model.clear(); assertEquals("", model.state.value.recapId)
    }
    @Test fun warningStaysConnectedAndDoesNotAllowAnotherPendingTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("有人让我转账并且保密")
        gateway.listener(frame(2, "warning", JSONObject()
            .put("reason_category", "TRANSFER_AND_SECRECY")
            .put("display_text", "请不要转账，先联系家人核实。"))); yield()
        assertTrue(model.state.value.connected)
        assertTrue(model.state.value.busy)
        assertEquals("WARNING", model.state.value.state)
        assertEquals("请不要转账，先联系家人核实。", model.state.value.message)
        model.input("不应发送第二轮")
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        gateway.listener(frame(3, "assistant.state", JSONObject().put("state", "WARNING"))); yield()
        assertFalse(model.state.value.busy)
        model.bind("other-family", "elder")
        assertEquals("", model.state.value.message)
        model.clear()
    }

    @Test fun malformedWarningDisconnectsWithoutDisplayingPayload() = runBlocking {
        for (payload in listOf(JSONObject().put("display_text", "untrusted"),
            JSONObject().put("reason_category", "CATEGORY").put("display_text", "x".repeat(2001)))) {
            val gateway = Gateway(); val model = ConversationModel(gateway, this)
            model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            gateway.listener(frame(2, "warning", payload)); yield()
            assertFalse(model.state.value.connected)
            assertFalse(model.state.value.message.contains("untrusted"))
            assertEquals("", model.state.value.reply)
            model.clear()
        }
    }

    @Test fun createdSignalDoesNotClaimDeliveryOrInterruptPendingSafetyTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("转账并保密")
        gateway.listener(frame(2, "signal.created", JSONObject().put("signal_event_id", id)
            .put("type", "SCAM_RISK").put("severity", "L2"))); yield()
        assertTrue(model.state.value.connected); assertTrue(model.state.value.busy)
        assertFalse(model.state.value.message.contains("已送达"))
        assertFalse(model.state.value.message.contains("已通知"))
        model.clear()
    }

    @Test fun realTextConversationShowsBothSidesAndSupportsAnotherTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1, payload = JSONObject().put("llm_mode", "real"))); yield()
        assertEquals("real", model.state.value.llmMode)
        assertTrue(model.input("我喜欢种花"))
        assertFalse(model.input("重复发送"))
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "喜欢种什么花呢？"))); yield()
        gateway.listener(frame(3, "assistant.state", JSONObject().put("state", "IDLE"))); yield()
        assertEquals(listOf(ChatMessage(true, "我喜欢种花"), ChatMessage(false, "喜欢种什么花呢？")),
            model.state.value.messages)
        assertTrue(model.input("月季"))
        model.bind("another-family", "elder")
        assertTrue(model.state.value.messages.isEmpty())
        assertEquals("", model.state.value.retryText)
        model.clear()
    }

    @Test fun providerFailureAllowsManualRetryAndFailedSendDoesNotConsumeDraft() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        assertTrue(model.input("你好"))
        gateway.listener(frame(2, "error")); yield()
        assertFalse(model.state.value.busy)
        assertEquals("你好", model.state.value.retryText)
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        gateway.failSend = true
        assertFalse(model.input("保留草稿"))
        assertFalse(model.state.value.connected)
        assertTrue(model.state.value.messages.isEmpty())
        model.clear()
    }

    @Test fun voiceRecognitionFeedsExistingTurnAndReplyPlaysUntilCompletion() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry()
        assertTrue(model.state.value.recording)
        assertEquals(CompanionPhase.LISTENING, model.state.value.companionPhase)
        voice.partial("我喜欢"); assertEquals("我喜欢", model.state.value.partialTranscript)
        model.finishListening()
        assertEquals(1, voice.finishes); assertTrue(model.state.value.recognizing)
        assertEquals(CompanionPhase.THINKING, model.state.value.companionPhase)
        voice.final("我喜欢种花")
        val request = gateway.sent.last().getLong("sequence")
        assertEquals("text.input", gateway.sent.last().getString("type"))
        assertEquals("我喜欢种花", gateway.sent.last().getJSONObject("payload").getString("text"))
        assertFalse(model.state.value.recording); assertFalse(model.state.value.recognizing)
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "喜欢什么花？"), request)); yield()
        gateway.listener(frame(3, "assistant.state", JSONObject().put("state", "IDLE"), request)); yield()
        assertFalse(model.state.value.speaking)
        assertTrue(model.state.value.speechPending)
        assertEquals(CompanionPhase.THINKING, model.state.value.companionPhase)
        voice.started()
        assertEquals(listOf("喜欢什么花？"), voice.spoken)
        assertEquals("SPEAKING", model.state.value.state); assertTrue(model.state.value.speaking)
        assertEquals(CompanionPhase.SPEAKING, model.state.value.companionPhase)
        voice.finished(); assertFalse(model.state.value.speaking); assertEquals("IDLE", model.state.value.state)
        assertEquals(CompanionPhase.IDLE, model.state.value.companionPhase)
        model.clear()
    }

    @Test fun interruptDropsLateReplyStateAndRecognitionWithoutBreakingNextTurn() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry(); val oldFinal = voice.final; voice.final("第一句")
        val oldRequest = gateway.sent.last().getLong("sequence")
        model.voiceEntry()
        val stopRequest = gateway.sent.last().getLong("sequence")
        oldFinal("不应发送")
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "迟到回答"), oldRequest)); yield()
        gateway.listener(frame(3, "assistant.state", JSONObject().put("state", "THINKING"), oldRequest)); yield()
        gateway.listener(frame(4, "assistant.state", JSONObject().put("state", "LISTENING"), stopRequest)); yield()
        assertTrue(model.state.value.recording); assertFalse(model.state.value.busy)
        assertTrue(voice.spoken.isEmpty()); assertEquals("", model.state.value.reply)
        voice.final("第二句")
        val newRequest = gateway.sent.last().getLong("sequence")
        gateway.listener(frame(5, "assistant.text", JSONObject().put("text", "第二次回答"), newRequest)); yield()
        assertEquals(listOf("第二次回答"), voice.spoken)
        assertEquals(2, gateway.sent.count { it.getString("type") == "text.input" })
        model.clear()
    }

    @Test fun interruptStopsSpeechImmediatelyAndIgnoresOldPlaybackCallbacks() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry(); voice.final("你好")
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "您好"), gateway.sent.last().getLong("sequence"))); yield()
        val oldStarted = voice.started; val oldFinished = voice.finished; val stops = voice.stops
        model.interrupt()
        assertTrue(voice.stops > stops); assertFalse(model.state.value.speaking)
        model.voiceEntry(); oldStarted(); oldFinished()
        assertTrue(model.state.value.recording); assertEquals("LISTENING", model.state.value.state)
        model.clear()
    }

    @Test fun leavingSessionStopsAudioAndDiscardsPrivateRecognition() = runBlocking {
        for (leave in listOf("background", "family", "disconnect", "end")) {
            val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
            model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            model.voiceEntry(); voice.partial("临时声音"); val late = voice.final; val before = gateway.sent.size
            when (leave) {
                "family" -> model.bind("other", "elder")
                "disconnect" -> { gateway.onClose(4403); yield() }
                "end" -> { model.end(); yield() }
                else -> model.clear()
            }
            late("已离开的会话内容")
            assertEquals(before, gateway.sent.size)
            assertFalse(model.state.value.recording); assertFalse(model.state.value.speaking)
            assertEquals("", model.state.value.partialTranscript); assertTrue(model.state.value.messages.isEmpty())
            model.clear()
        }
    }

    @Test fun permissionRecognitionAndPlaybackFailuresKeepTextUsable() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voicePermissionDenied(); assertFalse(model.state.value.recording)
        model.voiceEntry(); voice.failure("识别不可用")
        assertFalse(model.state.value.recording); assertTrue(model.state.value.connected)
        model.voiceEntry(); voice.final(" ")
        assertFalse(model.state.value.busy); assertEquals("IDLE", model.state.value.state)
        assertTrue(model.input("继续打字"))
        val request = gateway.sent.last().getLong("sequence")
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "文字回答"), request)); yield()
        gateway.listener(frame(3, "assistant.state", JSONObject().put("state", "IDLE"), request)); yield()
        voice.failure("朗读不可用")
        assertFalse(model.state.value.speaking); assertEquals("文字回答", model.state.value.reply)
        assertTrue(model.input("再聊一句"))
        model.clear()
    }

    @Test fun repeatRevalidatesOnServerAndDoesNotSpeakUnsolicitedInvitations() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.toggleSpeech()
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "主动邀请"))); yield()
        assertTrue(voice.spoken.isEmpty())
        model.repeat()
        assertEquals("repeat", gateway.sent.last().getString("type"))
        gateway.listener(frame(3, "assistant.text", JSONObject().put("text", "重新验证后的回答"), gateway.sent.last().getLong("sequence"))); yield()
        assertEquals(listOf("重新验证后的回答"), voice.spoken)
        model.toggleSpeech(); assertFalse(model.state.value.speaking); assertFalse(model.state.value.voiceEnabled)
        model.clear()
    }

    @Test fun recognizedControlsReplayThroughServerAndSetRateWithoutToggling() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry(); voice.final("你好")
        var sequence = 2L
        gateway.listener(frame(sequence++, "assistant.text", JSONObject().put("text", "第一条回答"),
            gateway.sent.last().getLong("sequence"))); yield()
        voice.started()
        for ((command, slow) in listOf("再说一遍。" to false, "慢一点！" to true,
            "慢一点" to true, "恢复语速" to false)) {
            val oldStarted = voice.started; val oldFinished = voice.finished
            model.voiceEntry()
            val interruptSequence = gateway.sent.last().getLong("sequence")
            voice.final(command)
            assertEquals("repeat", gateway.sent.last().getString("type"))
            assertEquals(slow, model.state.value.slowSpeech)
            val replaySequence = gateway.sent.last().getLong("sequence")
            // Old interrupt acknowledgements and local callbacks cannot reset the new replay.
            gateway.listener(frame(sequence++, "assistant.state", JSONObject().put("state", "LISTENING"), interruptSequence)); yield()
            oldStarted(); oldFinished()
            assertTrue(model.state.value.busy); assertFalse(model.state.value.speaking)
            val spokenBefore = voice.spoken.size
            assertFalse(model.state.value.speechPending)
            gateway.listener(frame(sequence++, "assistant.text", JSONObject().put("text", "服务器复核后的回答"), replaySequence)); yield()
            assertEquals(spokenBefore + 1, voice.spoken.size)
            assertEquals("服务器复核后的回答", voice.spoken.last())
            assertEquals(slow, voice.speechRates.last())
            voice.started()
        }
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.clear()
    }

    @Test fun controlsWithoutPreviousAnswerStayLocalAndOrdinarySpeechStillChats() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry(); voice.final("再说一遍")
        assertTrue(model.state.value.message.contains("还没有可重播"))
        assertFalse(model.state.value.busy)
        model.voiceEntry(); voice.final("慢一点")
        assertTrue(model.state.value.slowSpeech)
        assertTrue(voice.spoken.isEmpty())
        assertFalse(gateway.sent.any { it.getString("type") in listOf("repeat", "text.input") })
        model.voiceEntry(); voice.final("女儿让我慢一点走路")
        assertEquals("text.input", gateway.sent.last().getString("type"))
        assertEquals("女儿让我慢一点走路", gateway.sent.last().getJSONObject("payload").getString("text"))
        model.clear()
    }

    @Test fun recognizedStopAndEndIgnoreLateResultsAndDoNotAskTheModel() = runBlocking {
        for (command in listOf("停一下", "结束聊天")) {
            val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
            model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            model.voiceEntry(); val lateFinal = voice.final
            voice.final(command); yield()
            val sent = gateway.sent.size
            lateFinal("迟到的识别结果")
            assertEquals(sent, gateway.sent.size)
            assertFalse(model.state.value.voiceActive); assertFalse(model.state.value.busy)
            assertFalse(gateway.sent.any { it.getString("type") == "text.input" })
            if (command == "结束聊天") {
                assertEquals(1, gateway.ends); assertFalse(model.state.value.connected)
            } else {
                assertEquals("interrupt", gateway.sent.last().getString("type"))
                assertTrue(model.state.value.connected)
            }
            model.clear()
        }
    }

    @Test fun typedControlsUseTheSameDispatchAndDoNotEnableAudio() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("你好")
        gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "您好"),
            gateway.sent.last().getLong("sequence"))); yield()
        assertTrue(model.input("慢一点"))
        assertEquals("repeat", gateway.sent.last().getString("type"))
        gateway.listener(frame(3, "assistant.text", JSONObject().put("text", "复核后的文字"),
            gateway.sent.last().getLong("sequence"))); yield()
        assertTrue(model.state.value.slowSpeech)
        assertFalse(model.state.value.voiceEnabled); assertTrue(voice.spoken.isEmpty())
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.clear()
    }

    @Test fun voiceRequiresExplicitConsentAndRevocationCancelsRecordingAndPlayback() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1, payload = JSONObject().put("voice_allowed", false))); yield()
        model.voiceEntry(); model.toggleSpeech()
        assertFalse(model.state.value.recording); assertFalse(model.state.value.voiceEnabled)
        gateway.listener(frame(2, "voice.permission", JSONObject().put("allowed", true))); yield()
        model.voiceEntry(); val late = voice.final
        gateway.listener(frame(3, "voice.permission", JSONObject().put("allowed", false))); yield()
        late("不再发送")
        assertFalse(model.state.value.recording); assertEquals(0, gateway.sent.count { it.getString("type") == "text.input" })
        gateway.listener(frame(4, "voice.permission", JSONObject().put("allowed", true))); yield()
        model.voiceEntry(); voice.final("你好")
        val request = gateway.sent.last().getLong("sequence")
        gateway.listener(frame(5, "assistant.text", JSONObject().put("text", "你好"), request)); yield()
        gateway.listener(frame(6, "assistant.state", JSONObject().put("state", "IDLE"), request)); yield()
        voice.started()
        assertTrue(model.state.value.speaking)
        gateway.listener(frame(7, "voice.permission", JSONObject().put("allowed", false))); yield()
        assertFalse(model.state.value.speaking); assertFalse(model.state.value.voiceEnabled)
        assertTrue(model.input("仍可打字"))
        model.clear()
    }

    @Test fun serverPhasesAloneDoNotAnimateListeningOrSpeech() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        assertEquals(CompanionPhase.IDLE, model.state.value.companionPhase)
        model.input("文字输入")
        assertEquals(CompanionPhase.THINKING, model.state.value.companionPhase)
        gateway.listener(frame(2, "assistant.state", JSONObject().put("state", "SPEAKING"), gateway.sent.last().getLong("sequence"))); yield()
        assertEquals(CompanionPhase.THINKING, model.state.value.companionPhase)
        gateway.listener(frame(3, "assistant.text", JSONObject().put("text", "文字回答"), gateway.sent.last().getLong("sequence"))); yield()
        assertEquals(CompanionPhase.IDLE, model.state.value.companionPhase)
        model.clear()
    }

    @Test fun automaticCaptureEndShowsThinkingAndFailureReturnsToIdle() = runBlocking {
        val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
        model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.voiceEntry(); voice.captured()
        assertFalse(model.state.value.recording)
        assertEquals(CompanionPhase.THINKING, model.state.value.companionPhase)
        voice.failure("识别失败")
        assertEquals(CompanionPhase.IDLE, model.state.value.companionPhase)
        assertTrue(model.input("可以继续文字聊天"))
        model.clear()
    }

    @Test fun allExitPathsCancelPendingOrPlayingMouthAndRejectLateCallbacks() = runBlocking {
        for (playing in listOf(false, true)) for (exit in listOf("interrupt", "disconnect", "background", "revoke", "failure", "serverError")) {
            val gateway = Gateway(); val voice = Voice(); val model = ConversationModel(gateway, this)
            model.attachVoice(voice); model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            model.voiceEntry(); voice.final("你好")
            val request = gateway.sent.last().getLong("sequence")
            gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "您好"), request)); yield()
            if (playing) voice.started()
            val lateStart = voice.started; val lateFinish = voice.finished
            when (exit) {
                "interrupt" -> model.interrupt()
                "disconnect" -> { gateway.onClose(0); yield() }
                "background" -> model.clear()
                "revoke" -> { gateway.listener(frame(3, "voice.permission", JSONObject().put("allowed", false))); yield() }
                "failure" -> voice.failure("播放失败")
                else -> { gateway.listener(frame(3, "error", JSONObject(), request)); yield() }
            }
            lateStart(); lateFinish()
            assertEquals("$exit / playing=$playing", CompanionPhase.IDLE, model.state.value.companionPhase)
            assertFalse(model.state.value.voiceActive)
            model.clear()
        }
    }
}
