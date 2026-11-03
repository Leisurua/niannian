package org.example.niannian.feature.game

import kotlin.random.Random

internal enum class MatchItem(val label: String) {
    APPLE("苹果"), BANANA("香蕉"), CUP("杯子"), UMBRELLA("雨伞"),
    FISH("小鱼"), KEY("钥匙"), LEAF("树叶"), CLOCK("时钟")
}

internal data class MatchQuestion(val target: MatchItem, val choices: List<MatchItem>)
internal enum class MatchFeedback { TRY_AGAIN, FOUND }

internal class MatchRound private constructor(
    val questions: List<MatchQuestion>,
    val index: Int = 0,
    val attempts: Int = 0,
    val feedback: MatchFeedback? = null
) {
    val question get() = questions.getOrNull(index)
    val solved get() = feedback == MatchFeedback.FOUND

    fun choose(item: MatchItem): MatchRound {
        val current = question ?: return this
        if (solved || item !in current.choices) return this
        val result = if (item == current.target) MatchFeedback.FOUND else MatchFeedback.TRY_AGAIN
        return MatchRound(questions, index, attempts + 1, result)
    }

    fun advance(): MatchRound =
        if (solved && question != null) MatchRound(questions, index + 1, attempts) else this

    companion object {
        const val SIZE = 5

        fun start(random: Random = Random.Default): MatchRound {
            val items = MatchItem.entries
            return MatchRound(items.shuffled(random).take(SIZE).map { target ->
                val distractors = items.filter { it != target }.shuffled(random).take(2)
                MatchQuestion(target, (distractors + target).shuffled(random))
            })
        }
    }
}
