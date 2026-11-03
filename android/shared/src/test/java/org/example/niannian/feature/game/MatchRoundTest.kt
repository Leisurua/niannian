package org.example.niannian.feature.game

import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class MatchRoundTest {
    @Test fun targetsAreDistinctAndEachQuestionHasExactlyOneMatch() {
        repeat(20) { seed ->
            val round = MatchRound.start(Random(seed))
            assertEquals(5, round.questions.map { it.target }.distinct().size)
            for (question in round.questions) {
                assertEquals(3, question.choices.distinct().size)
                assertEquals(1, question.choices.count { it == question.target })
            }
        }
    }

    @Test fun wrongChoiceKeepsQuestionAndOnlySolvingAllowsAdvance() {
        val round = MatchRound.start(Random(1))
        val question = round.question!!
        assertSame(round, round.advance())
        val wrong = round.choose(question.choices.first { it != question.target })
        assertEquals(question, wrong.question)
        assertEquals(MatchFeedback.TRY_AGAIN, wrong.feedback)
        assertSame(wrong, wrong.advance())
        val found = wrong.choose(question.target)
        assertEquals(MatchFeedback.FOUND, found.feedback)
        assertEquals(2, found.attempts)
        assertSame(found, found.choose(question.target))
        assertEquals(1, found.advance().index)
        assertNull(found.advance().feedback)
    }

    @Test fun lastQuestionFinishesOnlyOnAdvanceAndReplayResetsCount() {
        var round = MatchRound.start(Random(2))
        repeat(5) { index ->
            val question = round.question!!
            if (index == 0) round = round.choose(question.choices.first { it != question.target })
            round = round.choose(question.target)
            assertEquals(index, round.index)
            assertNotNull(round.question)
            round = round.advance()
        }
        assertNull(round.question)
        assertEquals(6, round.attempts)
        assertSame(round, round.advance())
        assertSame(round, round.choose(MatchItem.APPLE))
        val replay = MatchRound.start(Random(3))
        assertEquals(0, replay.index)
        assertEquals(0, replay.attempts)
        assertNull(replay.feedback)
    }
}
