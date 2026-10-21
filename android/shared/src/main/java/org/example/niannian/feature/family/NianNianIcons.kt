package org.example.niannian.feature.family

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

object NianNianIcons {
    private fun strokeIcon(
        name: String,
        strokeWidth: Float = 2.1f,
        block: ImageVector.Builder.() -> Unit
    ): ImageVector = ImageVector.Builder(
        name = name,
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f
    ).apply(block).build()

    private fun ImageVector.Builder.strokePath(
        strokeWidth: Float = 2.1f,
        builder: androidx.compose.ui.graphics.vector.PathBuilder.() -> Unit
    ) {
        path(
            fill = null,
            stroke = SolidColor(Color.Black),
            strokeLineWidth = strokeWidth,
            strokeLineCap = StrokeCap.Round,
            strokeLineJoin = StrokeJoin.Round,
            pathFillType = PathFillType.NonZero,
            pathBuilder = builder
        )
    }

    val Type: ImageVector = strokeIcon("Type") {
        strokePath {
            moveTo(4f, 7f)
            verticalLineTo(4f)
            horizontalLineTo(20f)
            verticalLineTo(7f)
            moveTo(9f, 20f)
            horizontalLineTo(15f)
            moveTo(12f, 4f)
            verticalLineTo(20f)
        }
    }

    val Sun: ImageVector = strokeIcon("Sun") {
        strokePath {
            moveTo(16f, 12f)
            arcTo(4f, 4f, 0f, true, true, 8f, 12f)
            arcTo(4f, 4f, 0f, true, true, 16f, 12f)
            moveTo(12f, 2f); verticalLineTo(4f)
            moveTo(12f, 20f); verticalLineTo(22f)
            moveTo(4.93f, 4.93f); lineTo(6.34f, 6.34f)
            moveTo(17.66f, 17.66f); lineTo(19.07f, 19.07f)
            moveTo(2f, 12f); horizontalLineTo(4f)
            moveTo(20f, 12f); horizontalLineTo(22f)
            moveTo(6.34f, 17.66f); lineTo(4.93f, 19.07f)
            moveTo(19.07f, 4.93f); lineTo(17.66f, 6.34f)
        }
    }

    val Mic: ImageVector = strokeIcon("Mic", 2.3f) {
        strokePath(2.3f) {
            moveTo(12f, 2f)
            arcTo(3f, 3f, 0f, false, false, 9f, 5f)
            verticalLineTo(12f)
            arcTo(3f, 3f, 0f, false, false, 15f, 12f)
            verticalLineTo(5f)
            arcTo(3f, 3f, 0f, false, false, 12f, 2f)
            close()
            moveTo(19f, 10f)
            verticalLineTo(12f)
            arcTo(7f, 7f, 0f, false, true, 5f, 12f)
            verticalLineTo(10f)
            moveTo(12f, 19f)
            verticalLineTo(22f)
        }
    }

    val ShieldCheck: ImageVector = strokeIcon("ShieldCheck") {
        strokePath {
            moveTo(12f, 22f)
            curveTo(12f, 22f, 20f, 18f, 20f, 12f)
            verticalLineTo(5f)
            lineTo(12f, 2f)
            lineTo(4f, 5f)
            verticalLineTo(12f)
            curveTo(4f, 18f, 12f, 22f, 12f, 22f)
            close()
            moveTo(9f, 12f)
            lineTo(11f, 14f)
            lineTo(15f, 10f)
        }
    }

    val Check: ImageVector = strokeIcon("Check", 2.8f) {
        strokePath(2.8f) {
            moveTo(20f, 6f)
            lineTo(9f, 17f)
            lineTo(4f, 12f)
        }
    }

    val Pill: ImageVector = strokeIcon("Pill") {
        strokePath {
            moveTo(10.5f, 20.5f)
            lineTo(3.5f, 13.5f)
            arcTo(4.95f, 4.95f, 0f, true, true, 10.5f, 6.5f)
            lineTo(17.5f, 13.5f)
            arcTo(4.95f, 4.95f, 0f, true, true, 10.5f, 20.5f)
            close()
            moveTo(8.5f, 8.5f)
            lineTo(15.5f, 15.5f)
        }
    }

    val Footprints: ImageVector = strokeIcon("Footprints") {
        strokePath {
            moveTo(4f, 16f)
            verticalLineTo(13.5f)
            arcTo(2.5f, 2.5f, 0f, false, true, 9f, 13.5f)
            verticalLineTo(16f)
            close()
            moveTo(8f, 10f)
            arcTo(2.5f, 3.5f, 0f, true, true, 5f, 6f)
            arcTo(2.5f, 3.5f, 0f, true, true, 8f, 10f)
            moveTo(15f, 20f)
            verticalLineTo(17.5f)
            arcTo(2.5f, 2.5f, 0f, false, true, 20f, 17.5f)
            verticalLineTo(20f)
            close()
            moveTo(19f, 14f)
            arcTo(2.5f, 3.5f, 0f, true, true, 16f, 10f)
            arcTo(2.5f, 3.5f, 0f, true, true, 19f, 14f)
        }
    }

    val Droplet: ImageVector = strokeIcon("Droplet") {
        strokePath {
            moveTo(12f, 2.69f)
            lineTo(17.66f, 8.35f)
            arcTo(8f, 8f, 0f, true, true, 6.34f, 8.35f)
            close()
        }
    }

    val Video: ImageVector = strokeIcon("Video") {
        strokePath {
            moveTo(23f, 7f)
            lineTo(16f, 12f)
            lineTo(23f, 17f)
            verticalLineTo(7f)
            close()
            moveTo(4f, 5f)
            horizontalLineTo(14f)
            arcTo(2f, 2f, 0f, false, true, 16f, 7f)
            verticalLineTo(17f)
            arcTo(2f, 2f, 0f, false, true, 14f, 19f)
            horizontalLineTo(4f)
            arcTo(2f, 2f, 0f, false, true, 2f, 17f)
            verticalLineTo(7f)
            arcTo(2f, 2f, 0f, false, true, 4f, 5f)
            close()
        }
    }

    val Play: ImageVector = ImageVector.Builder(
        name = "Play",
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f
    ).apply {
        path(fill = SolidColor(Color.Black)) {
            moveTo(7f, 4.5f)
            lineTo(19.5f, 12f)
            lineTo(7f, 19.5f)
            close()
        }
    }.build()

    val Pause: ImageVector = ImageVector.Builder(
        name = "Pause",
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f
    ).apply {
        path(fill = SolidColor(Color.Black)) {
            moveTo(6f, 4f)
            horizontalLineTo(10f)
            verticalLineTo(20f)
            horizontalLineTo(6f)
            close()
            moveTo(14f, 4f)
            horizontalLineTo(18f)
            verticalLineTo(20f)
            horizontalLineTo(14f)
            close()
        }
    }.build()

    val HeartOutline: ImageVector = strokeIcon("HeartOutline") {
        strokePath {
            moveTo(19f, 14f)
            curveTo(20.49f, 12.54f, 22f, 10.79f, 22f, 8.5f)
            arcTo(5.5f, 5.5f, 0f, false, false, 16.5f, 3f)
            curveTo(14.74f, 3f, 13.5f, 3.5f, 12f, 5f)
            curveTo(10.5f, 3.5f, 9.26f, 3f, 7.5f, 3f)
            arcTo(5.5f, 5.5f, 0f, false, false, 2f, 8.5f)
            curveTo(2f, 10.8f, 3.5f, 12.55f, 5f, 14f)
            lineTo(12f, 21f)
            close()
        }
    }

    val HeartFilled: ImageVector = ImageVector.Builder(
        name = "HeartFilled",
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 24f,
        viewportHeight = 24f
    ).apply {
        path(fill = SolidColor(Color.Black)) {
            moveTo(19f, 14f)
            curveTo(20.49f, 12.54f, 22f, 10.79f, 22f, 8.5f)
            arcTo(5.5f, 5.5f, 0f, false, false, 16.5f, 3f)
            curveTo(14.74f, 3f, 13.5f, 3.5f, 12f, 5f)
            curveTo(10.5f, 3.5f, 9.26f, 3f, 7.5f, 3f)
            arcTo(5.5f, 5.5f, 0f, false, false, 2f, 8.5f)
            curveTo(2f, 10.8f, 3.5f, 12.55f, 5f, 14f)
            lineTo(12f, 21f)
            close()
        }
    }.build()

    val ChevronRight: ImageVector = strokeIcon("ChevronRight") {
        strokePath {
            moveTo(9f, 18f)
            lineTo(15f, 12f)
            lineTo(9f, 6f)
        }
    }

    val MessageCircle: ImageVector = strokeIcon("MessageCircle") {
        strokePath {
            moveTo(7.9f, 20f)
            arcTo(9f, 9f, 0f, true, false, 4f, 16.1f)
            lineTo(2f, 22f)
            close()
        }
    }

    val HeartHandshake: ImageVector = strokeIcon("HeartHandshake") {
        strokePath {
            moveTo(19f, 14f)
            curveTo(20.49f, 12.54f, 22f, 10.79f, 22f, 8.5f)
            arcTo(5.5f, 5.5f, 0f, false, false, 16.5f, 3f)
            curveTo(14.74f, 3f, 13.5f, 3.5f, 12f, 5f)
            curveTo(10.5f, 3.5f, 9.26f, 3f, 7.5f, 3f)
            arcTo(5.5f, 5.5f, 0f, false, false, 2f, 8.5f)
            curveTo(2f, 10.8f, 3.5f, 12.55f, 5f, 14f)
            lineTo(12f, 21f)
            close()
            moveTo(12f, 5f)
            lineTo(9.04f, 7.96f)
            arcTo(2.17f, 2.17f, 0f, false, false, 9.04f, 11.04f)
            curveTo(9.86f, 11.86f, 11.17f, 11.89f, 12.04f, 11.12f)
            lineTo(14.1f, 9.2f)
        }
    }

    val Settings: ImageVector = strokeIcon("Settings") {
        strokePath {
            moveTo(15f, 12f)
            arcTo(3f, 3f, 0f, true, true, 9f, 12f)
            arcTo(3f, 3f, 0f, true, true, 15f, 12f)
            moveTo(12f, 2f); verticalLineTo(4f)
            moveTo(12f, 20f); verticalLineTo(22f)
            moveTo(4.93f, 4.93f); lineTo(6.34f, 6.34f)
            moveTo(17.66f, 17.66f); lineTo(19.07f, 19.07f)
            moveTo(2f, 12f); horizontalLineTo(4f)
            moveTo(20f, 12f); horizontalLineTo(22f)
            moveTo(4.93f, 19.07f); lineTo(6.34f, 17.66f)
            moveTo(17.66f, 6.34f); lineTo(19.07f, 4.93f)
        }
    }

    val Keyboard: ImageVector = strokeIcon("Keyboard") {
        strokePath {
            moveTo(4f, 5f)
            horizontalLineTo(20f)
            arcTo(2f, 2f, 0f, false, true, 22f, 7f)
            verticalLineTo(17f)
            arcTo(2f, 2f, 0f, false, true, 20f, 19f)
            horizontalLineTo(4f)
            arcTo(2f, 2f, 0f, false, true, 2f, 17f)
            verticalLineTo(7f)
            arcTo(2f, 2f, 0f, false, true, 4f, 5f)
            close()
            moveTo(8f, 15f)
            horizontalLineTo(16f)
            moveTo(7f, 10f); horizontalLineTo(7.01f)
            moveTo(12f, 10f); horizontalLineTo(12.01f)
            moveTo(17f, 10f); horizontalLineTo(17.01f)
        }
    }

    val Close: ImageVector = strokeIcon("Close", 2.6f) {
        strokePath(2.6f) {
            moveTo(18f, 6f)
            lineTo(6f, 18f)
            moveTo(6f, 6f)
            lineTo(18f, 18f)
        }
    }

    val Bot: ImageVector = strokeIcon("Bot") {
        strokePath {
            moveTo(12f, 8f)
            verticalLineTo(4f)
            horizontalLineTo(8f)
            moveTo(6f, 8f)
            horizontalLineTo(18f)
            arcTo(2f, 2f, 0f, false, true, 20f, 10f)
            verticalLineTo(18f)
            arcTo(2f, 2f, 0f, false, true, 18f, 20f)
            horizontalLineTo(6f)
            arcTo(2f, 2f, 0f, false, true, 4f, 18f)
            verticalLineTo(10f)
            arcTo(2f, 2f, 0f, false, true, 6f, 8f)
            close()
            moveTo(9f, 14f); verticalLineTo(14.01f)
            moveTo(15f, 14f); verticalLineTo(14.01f)
        }
    }
}
