package com.d33z3r.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

@Composable
fun SettingsScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = "Impostazioni",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )

        Spacer(modifier = Modifier.height(24.dp))

        // ARL Info
        SettingsField(
            label = "ARL Token",
            value = "94ddf94ca13fbd3286b6c118010aa6281816a1b3d81827e50687add95ffec321a5948c8d23861b7b629f027c1155b0d101dd8a8c5aaad14a2977609a1b352015e492ad7aeef5ce96892c3c9a0960a04eb1d7caec151ba75b4d0fcaf2f568a6e5",
            maxLines = 4
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Account Info
        SettingsField(
            label = "Account",
            value = "deezerbotyzjpdrgr@outlook.com"
        )

        Spacer(modifier = Modifier.height(12.dp))

        SettingsField(
            label = "Data creazione",
            value = "10/06/2026 20:05"
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Info card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "D33Z3R - Standalone",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "App completamente standalone. Tutte le chiamate API Deezer e la decryption Blowfish vengono eseguite localmente sul dispositivo.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
fun SettingsField(label: String, value: String, maxLines: Int = 1) {
    Column {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.SemiBold
        )
        Spacer(modifier = Modifier.height(4.dp))
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceContainerHigh
            )
        ) {
            Text(
                text = value.ifEmpty { "Non disponibile" },
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodyMedium,
                maxLines = maxLines,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}
