package com.d33z3r.app.ui.viewmodel

import android.app.Application
import android.content.ContentValues
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.d33z3r.app.deezer.*
import com.d33z3r.app.playback.MusicPlayer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val arl = "94ddf94ca13fbd3286b6c118010aa6281816a1b3d81827e50687add95ffec321a5948c8d23861b7b629f027c1155b0d101dd8a8c5aaad14a2977609a1b352015e492ad7aeef5ce96892c3c9a0960a04eb1d7caec151ba75b4d0fcaf2f568a6e5"
    private var deezer: DeezerClient? = null
    private val player = MusicPlayer(application)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .dns(com.d33z3r.app.deezer.FallbackDns())
        .build()

    private val _trending = MutableStateFlow<TrendingResponse?>(null)
    val trending: StateFlow<TrendingResponse?> = _trending

    private val _chartTracks = MutableStateFlow<List<Track>>(emptyList())
    val chartTracks: StateFlow<List<Track>> = _chartTracks

    private val _searchResults = MutableStateFlow<SearchResponse?>(null)
    val searchResults: StateFlow<SearchResponse?> = _searchResults

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading

    private val _isLoggedIn = MutableStateFlow(false)
    val isLoggedIn: StateFlow<Boolean> = _isLoggedIn

    private val _currentTrack = MutableStateFlow<Track?>(null)
    val currentTrack: StateFlow<Track?> = _currentTrack

    private val _isPlaying = MutableStateFlow(false)
    val isPlaying: StateFlow<Boolean> = _isPlaying

    private val _playerError = MutableStateFlow<String?>(null)
    val playerError: StateFlow<String?> = _playerError

    // Album, playlist, artist details
    private val _albumDetails = MutableStateFlow<AlbumResponse?>(null)
    val albumDetails: StateFlow<AlbumResponse?> = _albumDetails

    private val _playlistDetails = MutableStateFlow<AlbumResponse?>(null)
    val playlistDetails: StateFlow<AlbumResponse?> = _playlistDetails

    private val _artistDetails = MutableStateFlow<ArtistResponse?>(null)
    val artistDetails: StateFlow<ArtistResponse?> = _artistDetails

    // Download feedback
    private val _downloadProgress = MutableStateFlow<String?>(null)
    val downloadProgress: StateFlow<String?> = _downloadProgress

    // Selected country shared state for Charts Screen
    val selectedCountryForCharts = MutableStateFlow("worldwide")

    init {
        initClient()
    }

    private fun initClient() {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val client = DeezerClient(arl)
                var success = false
                for (attempt in 1..5) {
                    success = client.login()
                    if (success) {
                        Log.d(TAG, "Login succeeded on attempt $attempt")
                        break
                    }
                    Log.d(TAG, "Login attempt $attempt failed, retrying in 2s...")
                    delay(2000)
                }
                deezer = client
                _isLoggedIn.value = success
                Log.d(TAG, "Login success=$success")
                if (success) {
                    loadTrending()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Login failed", e)
                _isLoggedIn.value = false
            }
        }
    }

    fun loadTrending() {
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                _trending.value = deezer?.getTrending()
                Log.d(TAG, "Trending loaded: ${_trending.value?.chartTracks?.size} tracks")
            } catch (e: Exception) {
                Log.e(TAG, "loadTrending failed", e)
            }
            _isLoading.value = false
        }
    }

    fun loadChart(country: String) {
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                val response = deezer?.getChart(country)
                _chartTracks.value = response?.tracks ?: emptyList()
                Log.d(TAG, "Chart loaded: ${_chartTracks.value.size} tracks")
            } catch (e: Exception) {
                Log.e(TAG, "loadChart failed", e)
            }
            _isLoading.value = false
        }
    }

    fun search(query: String) {
        if (query.isBlank()) {
            _searchResults.value = null
            return
        }
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                _searchResults.value = deezer?.search(query)
                Log.d(TAG, "Search results: ${_searchResults.value?.tracks?.size} tracks")
            } catch (e: Exception) {
                Log.e(TAG, "search failed", e)
            }
            _isLoading.value = false
        }
    }

    fun loadAlbumDetails(albumId: Long) {
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                _albumDetails.value = deezer?.getAlbum(albumId)
            } catch (e: Exception) {
                Log.e(TAG, "loadAlbumDetails failed", e)
            }
            _isLoading.value = false
        }
    }

    fun clearAlbumDetails() {
        _albumDetails.value = null
    }

    fun loadPlaylistDetails(playlistId: Long) {
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                _playlistDetails.value = deezer?.getPlaylist(playlistId)
            } catch (e: Exception) {
                Log.e(TAG, "loadPlaylistDetails failed", e)
            }
            _isLoading.value = false
        }
    }

    fun clearPlaylistDetails() {
        _playlistDetails.value = null
    }

    fun loadArtistDetails(artistId: Long) {
        viewModelScope.launch(Dispatchers.IO) {
            _isLoading.value = true
            try {
                _artistDetails.value = deezer?.getArtist(artistId)
            } catch (e: Exception) {
                Log.e(TAG, "loadArtistDetails failed", e)
            }
            _isLoading.value = false
        }
    }

    fun clearArtistDetails() {
        _artistDetails.value = null
    }

    fun playTrack(track: Track) {
        Log.d(TAG, "playTrack: ${track.title} (id=${track.id})")
        _currentTrack.value = track
        _playerError.value = null

        viewModelScope.launch(Dispatchers.IO) {
            try {
                val url = deezer?.getTrackUrl(track.id)
                Log.d(TAG, "Track URL obtained: ${url != null}")

                if (url != null) {
                    val cacheFile = File(getApplication<Application>().cacheDir, "track_${track.id}.mp3")

                    if (!cacheFile.exists() || cacheFile.length() == 0L) {
                        Log.d(TAG, "Downloading encrypted audio...")
                        val encrypted = downloadEncrypted(url)
                        Log.d(TAG, "Downloaded ${encrypted?.size ?: 0} bytes")

                        if (encrypted != null && encrypted.size > 16) {
                            val key = BlowfishDecryptor.generateKey(track.id.toString())
                            Log.d(TAG, "Decrypting...")
                            val decrypted = BlowfishDecryptor.decryptStream(key, encrypted)
                            Log.d(TAG, "Decrypted ${decrypted.size} bytes")
                            cacheFile.writeBytes(decrypted)
                            Log.d(TAG, "Written to ${cacheFile.absolutePath}")
                        } else {
                            Log.e(TAG, "Download failed or empty")
                            _playerError.value = "Download fallito"
                            return@launch
                        }
                    } else {
                        Log.d(TAG, "Using cached: ${cacheFile.length()} bytes")
                    }

                    if (cacheFile.exists() && cacheFile.length() > 0) {
                        val fileUri = Uri.fromFile(cacheFile).toString()
                        Log.d(TAG, "Playing: $fileUri")
                        withContext(Dispatchers.Main) {
                            player.play(fileUri)
                            player.updateMetadata(
                                track.title,
                                track.artist,
                                track.cover,
                                track.duration.toLong() * 1000
                            )
                            _isPlaying.value = true
                        }
                    } else {
                        Log.e(TAG, "Cache file missing")
                        _playerError.value = "File non trovato"
                    }
                } else {
                    Log.e(TAG, "Could not get track URL")
                    _playerError.value = "URL traccia non disponibile"
                }
            } catch (e: Exception) {
                Log.e(TAG, "playTrack error", e)
                _playerError.value = "Errore: ${e.message}"
            }
        }
    }

    fun togglePlayPause() {
        if (player.isPlaying()) {
            player.pause()
            _isPlaying.value = false
        } else {
            player.resume()
            _isPlaying.value = true
        }
    }

    // MediaStore Saving Logic
    private fun saveToDownloads(filename: String, subfolder: String?, data: ByteArray): Boolean {
        val resolver = getApplication<Application>().contentResolver
        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
            put(MediaStore.MediaColumns.MIME_TYPE, "audio/mpeg")
            val relativePath = if (subfolder != null) {
                "${Environment.DIRECTORY_DOWNLOADS}/D33Z3R/$subfolder"
            } else {
                "${Environment.DIRECTORY_DOWNLOADS}/D33Z3R"
            }
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            }
        }

        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, contentValues) ?: return false
        return try {
            resolver.openOutputStream(uri)?.use { outputStream ->
                outputStream.write(data)
                true
            } ?: false
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            Log.e(TAG, "Error saving to Downloads", e)
            false
        }
    }

    fun downloadTrack(track: Track) {
        viewModelScope.launch(Dispatchers.IO) {
            _downloadProgress.value = "Scarico ${track.title}..."
            try {
                val url = deezer?.getTrackUrl(track.id)
                if (url != null) {
                    val encrypted = downloadEncrypted(url)
                    if (encrypted != null && encrypted.size > 16) {
                        val key = BlowfishDecryptor.generateKey(track.id.toString())
                        val decrypted = BlowfishDecryptor.decryptStream(key, encrypted)
                        val safeTitle = track.title.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
                        val safeArtist = track.artist.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
                        val filename = "$safeArtist - $safeTitle.mp3"
                        val success = saveToDownloads(filename, null, decrypted)
                        if (success) {
                            _downloadProgress.value = "Scaricato: $safeTitle"
                        } else {
                            _downloadProgress.value = "Salvataggio fallito"
                        }
                    } else {
                        _downloadProgress.value = "Download fallito"
                    }
                } else {
                    _downloadProgress.value = "Traccia non disponibile"
                }
            } catch (e: Exception) {
                Log.e(TAG, "downloadTrack error", e)
                _downloadProgress.value = "Errore durante il download"
            }
            delay(3000)
            _downloadProgress.value = null
        }
    }

    fun downloadAlbum(album: Album, tracks: List<Track>) {
        viewModelScope.launch(Dispatchers.IO) {
            val total = tracks.size
            val safeAlbumTitle = album.title.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
            val safeArtist = album.artist.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
            val subfolder = "$safeArtist - $safeAlbumTitle"

            tracks.forEachIndexed { index, track ->
                _downloadProgress.value = "Scarico album... (${index + 1}/$total): ${track.title}"
                try {
                    val url = deezer?.getTrackUrl(track.id)
                    if (url != null) {
                        val encrypted = downloadEncrypted(url)
                        if (encrypted != null && encrypted.size > 16) {
                            val key = BlowfishDecryptor.generateKey(track.id.toString())
                            val decrypted = BlowfishDecryptor.decryptStream(key, encrypted)
                            val safeTitle = track.title.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
                            val filename = "${String.format("%02d", index + 1)} - $safeTitle.mp3"
                            saveToDownloads(filename, subfolder, decrypted)
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error downloading album track", e)
                }
            }
            _downloadProgress.value = "Album scaricato!"
            delay(3000)
            _downloadProgress.value = null
        }
    }

    fun downloadPlaylist(playlistName: String, tracks: List<Track>) {
        viewModelScope.launch(Dispatchers.IO) {
            val total = tracks.size
            val safePlaylistName = playlistName.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
            val subfolder = "Playlist - $safePlaylistName"

            tracks.forEachIndexed { index, track ->
                _downloadProgress.value = "Scarico playlist... (${index + 1}/$total): ${track.title}"
                try {
                    val url = deezer?.getTrackUrl(track.id)
                    if (url != null) {
                        val encrypted = downloadEncrypted(url)
                        if (encrypted != null && encrypted.size > 16) {
                            val key = BlowfishDecryptor.generateKey(track.id.toString())
                            val decrypted = BlowfishDecryptor.decryptStream(key, encrypted)
                            val safeTitle = track.title.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
                            val safeArtist = track.artist.replace("[\\\\/:*?\"<>|]".toRegex(), "_")
                            val filename = "${String.format("%02d", index + 1)} - $safeArtist - $safeTitle.mp3"
                            saveToDownloads(filename, subfolder, decrypted)
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error downloading playlist track", e)
                }
            }
            _downloadProgress.value = "Playlist scaricata!"
            delay(3000)
            _downloadProgress.value = null
        }
    }

    private fun downloadEncrypted(url: String): ByteArray? {
        return try {
            val request = Request.Builder()
                .url(url)
                .header("User-Agent", "Mozilla/5.0")
                .build()
            val response = httpClient.newCall(request).execute()
            response.body?.bytes()
        } catch (e: Exception) {
            Log.e(TAG, "downloadEncrypted error", e)
            null
        }
    }

    override fun onCleared() {
        super.onCleared()
        player.release()
    }

    companion object {
        private const val TAG = "D33Z3R"
    }
}
