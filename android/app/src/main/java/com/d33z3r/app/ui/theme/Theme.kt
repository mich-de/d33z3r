package com.d33z3r.app.ui.theme

import android.os.Build
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF1DB954),
    onPrimary = Color.Black,
    primaryContainer = Color(0xFF14803A),
    onPrimaryContainer = Color.White,
    secondary = Color(0xFF19E68C),
    onSecondary = Color.Black,
    secondaryContainer = Color(0xFF119E5F),
    onSecondaryContainer = Color.White,
    tertiary = Color(0xFF1DB954),
    onTertiary = Color.Black,
    background = Color(0xFF040404),
    onBackground = Color.White,
    surface = Color(0xFF121212),
    onSurface = Color.White,
    surfaceVariant = Color(0xFF282828),
    onSurfaceVariant = Color(0xFFB3B3B3),
    surfaceContainerLow = Color(0xFF151515),
    surfaceContainer = Color(0xFF181818),
    surfaceContainerHigh = Color(0xFF242424),
    outline = Color(0xFF3E3E3E),
    outlineVariant = Color(0xFF4F4F4F)
)

@Composable
fun D33Z3RTheme(
    dynamicColor: Boolean = false,
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
