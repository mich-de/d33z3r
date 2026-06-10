package com.d33z3r.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import com.d33z3r.app.deezer.Track
import com.d33z3r.app.ui.viewmodel.MainViewModel

@Composable
fun ChartsScreen(
    viewModel: MainViewModel,
    onTrackClick: (Track) -> Unit
) {
    val selectedCountry by viewModel.selectedCountryForCharts.collectAsState()
    val chartTracks by viewModel.chartTracks.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()

    val countries = listOf(
        Triple("worldwide", "Worldwide", "🌍"),
        Triple("italy", "Italia", "🇮🇹"),
        Triple("france", "France", "🇫🇷"),
        Triple("usa", "USA", "🇺🇸"),
        Triple("uk", "UK", "🇬🇧"),
        Triple("germany", "Germany", "🇩🇪"),
        Triple("spain", "Spain", "🇪🇸"),
        Triple("brazil", "Brazil", "🇧🇷"),
        Triple("japan", "Japan", "🇯🇵")
    )

    LaunchedEffect(selectedCountry) {
        viewModel.loadChart(selectedCountry)
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Country selector
        ScrollableTabRow(
            selectedTabIndex = countries.indexOfFirst { it.first == selectedCountry },
            containerColor = MaterialTheme.colorScheme.surface,
            edgePadding = 16.dp
        ) {
            countries.forEach { (code, name, flag) ->
                Tab(
                    selected = selectedCountry == code,
                    onClick = { viewModel.selectedCountryForCharts.value = code },
                    text = { Text("$flag $name") }
                )
            }
        }

        // Track list
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                items(chartTracks) { track ->
                    TrackListItem(
                        track = track,
                        onClick = { onTrackClick(track) },
                        onDownloadClick = { viewModel.downloadTrack(track) }
                    )
                }
            }
        }
    }
}

@Composable
fun TrackListItem(
    track: Track,
    onClick: () -> Unit,
    onDownloadClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "${track.position}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(32.dp)
        )
        AsyncImage(
            model = track.cover,
            contentDescription = track.title,
            modifier = Modifier
                .size(48.dp)
                .clip(MaterialTheme.shapes.small),
            contentScale = ContentScale.Crop
        )
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = track.title,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = track.artist,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        Text(
            text = formatDuration(track.duration),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.width(8.dp))
        IconButton(onClick = onDownloadClick) {
            Icon(
                imageVector = Icons.Default.Download,
                contentDescription = "Scarica Traccia",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
