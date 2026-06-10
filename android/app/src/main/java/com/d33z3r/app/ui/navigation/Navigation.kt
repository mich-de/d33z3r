package com.d33z3r.app.ui.navigation

import androidx.compose.animation.*
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.d33z3r.app.deezer.Track
import com.d33z3r.app.ui.screens.*
import com.d33z3r.app.ui.viewmodel.MainViewModel
import coil.compose.AsyncImage

sealed class Screen(
    val route: String,
    val title: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector
) {
    data object Home : Screen("home", "Home", Icons.Filled.Home, Icons.Outlined.Home)
    data object Charts : Screen("charts", "Charts", Icons.Filled.TrendingUp, Icons.Outlined.TrendingUp)
    data object Search : Screen("search", "Cerca", Icons.Filled.Search, Icons.Outlined.Search)
    data object Library : Screen("library", "Libreria", Icons.Filled.LibraryMusic, Icons.Outlined.LibraryMusic)
    data object Settings : Screen("settings", "Impostazioni", Icons.Filled.Settings, Icons.Outlined.Settings)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun D33Z3RNavHost(viewModel: MainViewModel) {
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Home) }
    val currentTrack by viewModel.currentTrack.collectAsState()
    val isPlaying by viewModel.isPlaying.collectAsState()
    val configuration = LocalConfiguration.current
    val isTablet = configuration.screenWidthDp >= 600

    Scaffold(
        bottomBar = {
            Column {
                // Mini player
                AnimatedVisibility(
                    visible = currentTrack != null,
                    enter = slideInVertically(initialOffsetY = { it }),
                    exit = slideOutVertically(targetOffsetY = { it })
                ) {
                    currentTrack?.let { track ->
                        MiniPlayer(
                            track = track,
                            isPlaying = isPlaying,
                            onPlayPause = { viewModel.togglePlayPause() },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 4.dp)
                        )
                    }
                }

                // Bottom navigation (only on phones)
                if (!isTablet) {
                    NavigationBar(
                        containerColor = MaterialTheme.colorScheme.surfaceContainer,
                        tonalElevation = 0.dp
                    ) {
                        val screens = listOf(Screen.Home, Screen.Charts, Screen.Search, Screen.Library, Screen.Settings)
                        screens.forEach { screen ->
                            val selected = currentScreen.route == screen.route
                            NavigationBarItem(
                                icon = {
                                    Icon(
                                        imageVector = if (selected) screen.selectedIcon else screen.unselectedIcon,
                                        contentDescription = screen.title
                                    )
                                },
                                label = { Text(screen.title) },
                                selected = selected,
                                onClick = { currentScreen = screen },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = MaterialTheme.colorScheme.primary,
                                    indicatorColor = MaterialTheme.colorScheme.primaryContainer
                                )
                            )
                        }
                    }
                }
            }
        }
    ) { padding ->
        Row(modifier = Modifier.fillMaxSize()) {
            // Navigation rail (tablets)
            if (isTablet) {
                NavigationRail(
                    containerColor = MaterialTheme.colorScheme.surfaceContainer,
                    modifier = Modifier.padding(padding)
                ) {
                    val screens = listOf(Screen.Home, Screen.Charts, Screen.Search, Screen.Library, Screen.Settings)
                    screens.forEach { screen ->
                        val selected = currentScreen.route == screen.route
                        NavigationRailItem(
                            icon = {
                                Icon(
                                    imageVector = if (selected) screen.selectedIcon else screen.unselectedIcon,
                                    contentDescription = screen.title
                                )
                            },
                            label = { Text(screen.title) },
                            selected = selected,
                            onClick = { currentScreen = screen }
                        )
                    }
                }
            }

            // Content
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
            ) {
                when (currentScreen) {
                    Screen.Home -> HomeScreen(
                        viewModel = viewModel,
                        onTrackClick = { track -> viewModel.playTrack(track) },
                        onAlbumClick = { album -> viewModel.loadAlbumDetails(album.id) },
                        onPlaylistClick = { playlist -> viewModel.loadPlaylistDetails(playlist.id) },
                        onChartClick = { countryCode ->
                            viewModel.selectedCountryForCharts.value = countryCode
                            currentScreen = Screen.Charts
                        }
                    )
                    Screen.Charts -> ChartsScreen(
                        viewModel = viewModel,
                        onTrackClick = { track -> viewModel.playTrack(track) }
                    )
                    Screen.Search -> SearchScreen(
                        viewModel = viewModel,
                        onTrackClick = { track -> viewModel.playTrack(track) },
                        onArtistClick = { artist -> viewModel.loadArtistDetails(artist.id) },
                        onAlbumClick = { album -> viewModel.loadAlbumDetails(album.id) },
                        onPlaylistClick = { playlist -> viewModel.loadPlaylistDetails(playlist.id) }
                    )
                    Screen.Library -> LibraryScreen()
                    Screen.Settings -> SettingsScreen()
                }

                // Download floating progress banner
                val downloadProgress by viewModel.downloadProgress.collectAsState()
                androidx.compose.animation.AnimatedVisibility(
                    visible = downloadProgress != null,
                    enter = fadeIn() + slideInVertically(initialOffsetY = { -it }),
                    exit = fadeOut() + slideOutVertically(targetOffsetY = { -it }),
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 16.dp)
                ) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer
                        ),
                        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = downloadProgress ?: "",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                    }
                }

                // Details Bottom Sheets
                val albumDetails by viewModel.albumDetails.collectAsState()
                val playlistDetails by viewModel.playlistDetails.collectAsState()
                val artistDetails by viewModel.artistDetails.collectAsState()

                if (albumDetails != null) {
                    ModalBottomSheet(
                        onDismissRequest = { viewModel.clearAlbumDetails() },
                        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
                    ) {
                        AlbumDetailSheet(
                            response = albumDetails!!,
                            onTrackClick = { track ->
                                viewModel.playTrack(track)
                                viewModel.clearAlbumDetails()
                            },
                            onDownloadTrack = { track -> viewModel.downloadTrack(track) },
                            onDownloadAlbum = { album, tracks -> viewModel.downloadAlbum(album, tracks) }
                        )
                    }
                }

                if (playlistDetails != null) {
                    ModalBottomSheet(
                        onDismissRequest = { viewModel.clearPlaylistDetails() },
                        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
                    ) {
                        PlaylistDetailSheet(
                            response = playlistDetails!!,
                            onTrackClick = { track ->
                                viewModel.playTrack(track)
                                viewModel.clearPlaylistDetails()
                            },
                            onDownloadTrack = { track -> viewModel.downloadTrack(track) },
                            onDownloadPlaylist = { name, tracks -> viewModel.downloadPlaylist(name, tracks) }
                        )
                    }
                }

                if (artistDetails != null) {
                    ModalBottomSheet(
                        onDismissRequest = { viewModel.clearArtistDetails() },
                        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
                    ) {
                        ArtistDetailSheet(
                            response = artistDetails!!,
                            onTrackClick = { track ->
                                viewModel.playTrack(track)
                                viewModel.clearArtistDetails()
                            },
                            onDownloadTrack = { track -> viewModel.downloadTrack(track) },
                            onAlbumClick = { album ->
                                viewModel.loadAlbumDetails(album.id)
                                viewModel.clearArtistDetails()
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun MiniPlayer(
    track: Track,
    isPlaying: Boolean,
    onPlayPause: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            AsyncImage(
                model = track.cover,
                contentDescription = null,
                modifier = Modifier.size(48.dp)
            )

            Spacer(modifier = Modifier.width(12.dp))

            // Track info
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = track.title,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
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

            // Controls
            IconButton(onClick = onPlayPause) {
                Icon(
                    imageVector = if (isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = if (isPlaying) "Pausa" else "Riproduci",
                    tint = MaterialTheme.colorScheme.primary
                )
            }
        }
    }
}
