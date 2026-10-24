package org.example.niannian.feature.conversation

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

private val Persimmon300 = Color(0xFFE79B72)

@Composable
fun PersimmonCompanionOrb(
    size: Dp = 148.dp,
    phase: CompanionPhase = CompanionPhase.IDLE,
    modifier: Modifier = Modifier
) {
    val listening = phase == CompanionPhase.LISTENING
    val mouth = if (phase == CompanionPhase.SPEAKING) speakingMouth() else 0f
    val transition = rememberInfiniteTransition(label = "orbTransition")
    val breatheScale by transition.animateFloat(
        initialValue = 1.0f,
        targetValue = 1.045f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (listening) 1200 else 2500, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "breatheScale"
    )
    val rippleProgress by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (listening) 2200 else 3600, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rippleProgress"
    )

    Box(
        modifier = modifier.size(size),
        contentAlignment = Alignment.Center
    ) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .scale(breatheScale)
        ) {
            val w = this.size.width
            val h = this.size.height
            val center = Offset(w / 2f, h / 2f)
            val baseRadius = w * 0.31f

            listOf(0f, 0.33f, 0.66f).forEach { phaseOffset ->
                val p = (rippleProgress + phaseOffset) % 1f
                val r = baseRadius * (0.95f + p * 0.85f)
                val alpha = (1f - p) * 0.45f
                drawCircle(
                    color = (if (phase == CompanionPhase.THINKING) Color(0xFF6F7F62) else Persimmon300).copy(alpha = alpha),
                    radius = r,
                    center = center,
                    style = Stroke(width = 1.8.dp.toPx())
                )
            }

            val s = (w * 0.78f) / 120f
            val ox = (w - 120f * s) / 2f
            val oy = (h - 120f * s) / 2f

            fun vx(x: Float) = ox + x * s
            fun vy(y: Float) = oy + y * s

            drawOval(
                color = Color(0x388F4224),
                topLeft = Offset(vx(22f), vy(96f)),
                size = Size(76f * s, 16f * s)
            )

            val bodyPath = Path().apply {
                moveTo(vx(60f), vy(26f))
                cubicTo(vx(87f), vy(26f), vx(106f), vy(41f), vx(106f), vy(67f))
                cubicTo(vx(106f), vy(91f), vx(86f), vy(108f), vx(60f), vy(108f))
                cubicTo(vx(34f), vy(108f), vx(14f), vy(91f), vx(14f), vy(67f))
                cubicTo(vx(14f), vy(41f), vx(33f), vy(26f), vx(60f), vy(26f))
                close()
            }
            drawPath(
                path = bodyPath,
                brush = Brush.radialGradient(
                    colors = listOf(
                        Color(0xFFF8C39C),
                        Color(0xFFE58A5C),
                        Color(0xFFB9542C)
                    ),
                    center = Offset(vx(46f), vy(44f)),
                    radius = 68f * s
                )
            )

            val creasePath = Path().apply {
                moveTo(vx(60f), vy(32f))
                cubicTo(vx(54f), vy(50f), vx(54f), vy(84f), vx(60f), vy(106f))
            }
            drawPath(
                path = creasePath,
                color = Color(0x24A9472A),
                style = Stroke(width = 2f * s, cap = StrokeCap.Round)
            )

            rotate(degrees = -24f, pivot = Offset(vx(42f), vy(48f))) {
                drawOval(
                    brush = Brush.radialGradient(
                        colors = listOf(Color.White.copy(alpha = 0.72f), Color.Transparent),
                        center = Offset(vx(42f), vy(48f)),
                        radius = 14f * s
                    ),
                    topLeft = Offset(vx(29f), vy(40f)),
                    size = Size(26f * s, 16f * s)
                )
            }

            val leftLeaf = Path().apply {
                moveTo(vx(60f), vy(28f))
                cubicTo(vx(54f), vy(20f), vx(43f), vy(19f), vx(38f), vy(24f))
                cubicTo(vx(45f), vy(25f), vx(51f), vy(28f), vx(60f), vy(28f))
                close()
            }
            drawPath(leftLeaf, color = Color(0xFF6F7F62))

            val rightLeaf = Path().apply {
                moveTo(vx(60f), vy(28f))
                cubicTo(vx(66f), vy(20f), vx(77f), vy(19f), vx(82f), vy(24f))
                cubicTo(vx(75f), vy(25f), vx(69f), vy(28f), vx(60f), vy(28f))
                close()
            }
            drawPath(rightLeaf, color = Color(0xFF7E8E70))

            val stemPath = Path().apply {
                moveTo(vx(60f), vy(28f))
                cubicTo(vx(57f), vy(22f), vx(58f), vy(16f), vx(62f), vy(13f))
                cubicTo(vx(63f), vy(19f), vx(63f), vy(23f), vx(60f), vy(28f))
                close()
            }
            drawPath(stemPath, color = Color(0xFF5E6E53))
            drawCircle(
                color = Color(0xFF4C5A42),
                radius = 3.4f * s,
                center = Offset(vx(60f), vy(28f))
            )

            val eyeColor = Color(0xFF4A2416)
            if (listening) {
                drawCircle(eyeColor, radius = 3.6f * s, center = Offset(vx(47f), vy(68f)))
                drawCircle(eyeColor, radius = 3.6f * s, center = Offset(vx(73f), vy(68f)))
            } else {
                val leftEye = Path().apply {
                    moveTo(vx(42f), vy(68f))
                    quadraticTo(vx(47f), vy(63f), vx(52f), vy(68f))
                }
                val rightEye = Path().apply {
                    moveTo(vx(68f), vy(68f))
                    quadraticTo(vx(73f), vy(63f), vx(78f), vy(68f))
                }
                drawPath(leftEye, eyeColor, style = Stroke(width = 3f * s, cap = StrokeCap.Round))
                drawPath(rightEye, eyeColor, style = Stroke(width = 3f * s, cap = StrokeCap.Round))
            }

            drawOval(
                color = Color(0xCCF3A07C),
                topLeft = Offset(vx(32f), vy(74.6f)),
                size = Size(12f * s, 6.8f * s)
            )
            drawOval(
                color = Color(0xCCF3A07C),
                topLeft = Offset(vx(76f), vy(74.6f)),
                size = Size(12f * s, 6.8f * s)
            )

            if (phase == CompanionPhase.THINKING) {
                repeat(3) { index ->
                    val emphasis = ((rippleProgress * 3).toInt() == index)
                    drawCircle(eyeColor.copy(alpha = if (emphasis) 1f else 0.3f),
                        radius = 2.5f * s, center = Offset(vx(50f + index * 10f), vy(8f)))
                }
            }
            if (phase == CompanionPhase.SPEAKING) {
                drawOval(eyeColor, topLeft = Offset(vx(54f), vy(79f)),
                    size = Size(12f * s, (2f + 9f * mouth) * s))
            } else {
                val smilePath = Path().apply {
                    if (listening) {
                        moveTo(vx(54f), vy(80f))
                        quadraticTo(vx(60f), vy(86f), vx(66f), vy(80f))
                    } else {
                        moveTo(vx(55f), vy(80f))
                        quadraticTo(vx(60f), vy(84f), vx(65f), vy(80f))
                    }
                }
                drawPath(smilePath, eyeColor, style = Stroke(width = 2.6f * s, cap = StrokeCap.Round))
            }
        }
    }
}

@Composable
private fun speakingMouth(): Float {
    val transition = rememberInfiniteTransition(label = "speechMouth")
    val opening by transition.animateFloat(0f, 1f,
        infiniteRepeatable(tween(160, easing = LinearEasing), RepeatMode.Reverse), label = "mouthOpening")
    return opening
}
