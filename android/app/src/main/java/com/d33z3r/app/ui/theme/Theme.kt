package com.d33z3r.app.ui.theme

import android.os.Build
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFFA238FF),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF7B1FD6),
    onPrimaryContainer = Color.White,
    secondary = Color(0xFFFF2D87),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFCC1A6B),
    onSecondaryContainer = Color.White,
    tertiary = Color(0xFF1DB954),
    onTertiary = Color.White,
    background = Color(0xFF0A0A0F),
    onBackground = Color.White,
    surface = Color(0xFF12121A),
    onSurface = Color.White,
    surfaceVariant = Color(0xFF1E1E2E),
    onSurfaceVariant = Color(0xFFB3B3B3),
    surfaceContainerLow = Color(0xFF141420),
    surfaceContainer = Color(0xFF1A1A28),
    surfaceContainerHigh = Color(0xFF222236),
    outline = Color(0xFF333344),
    outlineVariant = Color(0xFF444455)
)

@Composable
fun D33Z3RTheme(
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            dynamicDarkColorScheme(androidx.compose.ui.platform.LocalContext.current)
        }
        else -> DarkColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography(),
        content = content
    )
}
