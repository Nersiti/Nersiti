package com.nersiti.prokachka.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val Orange = Color(0xFFFF6B2C)
private val OrangeDark = Color(0xFFB8420F)

private val DarkColors = darkColorScheme(
    primary = Orange,
    onPrimary = Color(0xFF2A0E00),
    primaryContainer = Color(0xFF5A2408),
    onPrimaryContainer = Color(0xFFFFDBCC),
    secondary = Color(0xFF7DD3FC),
    onSecondary = Color(0xFF00283A),
    tertiary = Color(0xFF86EFAC),
    background = Color(0xFF12121A),
    onBackground = Color(0xFFECECF4),
    surface = Color(0xFF12121A),
    onSurface = Color(0xFFECECF4),
    surfaceVariant = Color(0xFF262633),
    onSurfaceVariant = Color(0xFFB9B9CC),
    surfaceContainer = Color(0xFF1C1C26),
    surfaceContainerHigh = Color(0xFF242430),
    outline = Color(0xFF4A4A5C),
)

private val LightColors = lightColorScheme(
    primary = OrangeDark,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDBCC),
    onPrimaryContainer = Color(0xFF3A1400),
    secondary = Color(0xFF0369A1),
    tertiary = Color(0xFF15803D),
    background = Color(0xFFFBF8F6),
    surface = Color(0xFFFBF8F6),
    surfaceContainer = Color(0xFFF1ECE8),
    surfaceContainerHigh = Color(0xFFEAE4DF),
)

private val AppTypography = Typography().run {
    copy(
        displaySmall = displaySmall.copy(fontWeight = FontWeight.Black),
        headlineMedium = headlineMedium.copy(fontWeight = FontWeight.Bold),
        headlineSmall = headlineSmall.copy(fontWeight = FontWeight.Bold),
        titleLarge = titleLarge.copy(fontWeight = FontWeight.Bold),
        labelLarge = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 15.sp),
    )
}

@Composable
fun ProkachkaTheme(darkTheme: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = AppTypography,
        content = content,
    )
}
