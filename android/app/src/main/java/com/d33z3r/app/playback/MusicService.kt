package com.d33z3r.app.playback

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.support.v4.media.MediaBrowserCompat.MediaItem
import android.support.v4.media.MediaDescriptionCompat
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.core.app.NotificationCompat
import androidx.media.MediaBrowserServiceCompat
import androidx.media.session.MediaButtonReceiver
import com.d33z3r.app.deezer.BlowfishDecryptor
import com.d33z3r.app.deezer.DeezerClient
import com.d33z3r.app.MainActivity
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

class MusicService : MediaBrowserServiceCompat() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private lateinit var player: MusicPlayer
    private var deezer: DeezerClient? = null
    private lateinit var notificationManager: NotificationManager

    private val CHANNEL_ID = "d33z3r_playback"
    private val NOTIFICATION_ID = 1

    companion object {
        private val ROOT_ID = "D33Z3R_ROOT"
        private val CATEGORY_CHARTS = "charts"
        private val CATEGORY_TRENDING = "trending"
        private val CATEGORY_NEW = "new_releases"

        private val CHART_COUNTRIES = listOf(
            Triple("worldwide", "Worldwide", "\uD83C\uDF0D"),
            Triple("italy", "Italia", "\uD83C\uDDEE\uD83C\uDDF9"),
            Triple("france", "France", "\uD83C\uDDEB\uD83C\uDDF7"),
            Triple("usa", "USA", "\uD83C\uDDFA\uD83C\uDDF8"),
            Triple("uk", "UK", "\uD83C\uDDEC\uD83C\uDDE7"),
            Triple("germany", "Germany", "\uD83C\uDDE9\uD83C\uDDEA"),
            Triple("spain", "Spain", "\uD83C\uDDEA\uD83C\uDDF8"),
            Triple("brazil", "Brazil", "\uD83C\uDDE7\uD83C\uDDF7"),
            Triple("japan", "Japan", "\uD83C\uDDEF\uD83C\uDDF5")
        )
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .dns(com.d33z3r.app.deezer.FallbackDns())
        .build()

    override fun onCreate() {
        super.onCreate()
        player = MusicPlayer(this)
        notificationManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        createNotificationChannel()

        sessionToken = player.session.sessionToken

        // Init DeezerClient on background thread
        scope.launch(Dispatchers.IO) {
            val client = DeezerClient("94ddf94ca13fbd3286b6c118010aa6281816a1b3d81827e50687add95ffec321a5948c8d23861b7b629f027c1155b0d101dd8a8c5aaad14a2977609a1b352015e492ad7aeef5ce96892c3c9a0960a04eb1d7caec151ba75b4d0fcaf2f568a6e5")
            var success = false
            for (attempt in 1..5) {
                success = client.login()
                if (success) {
                    android.util.Log.d("D33Z3R", "Service login succeeded on attempt $attempt")
                    break
                }
                android.util.Log.d("D33Z3R", "Service login attempt $attempt failed, retrying in 2s...")
                delay(2000)
            }
            deezer = client
        }
        notificationManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        createNotificationChannel()

        sessionToken = player.session.sessionToken

        player.session.setCallback(object : MediaSessionCompat.Callback() {
            override fun onPlay() {
                player.resume()
                showNotification()
            }

            override fun onPause() {
                player.pause()
                showNotification()
            }

            override fun onStop() {
                player.release()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }

            override fun onSkipToNext() {}
            override fun onSkipToPrevious() {}
            override fun onSeekTo(pos: Long) { player.seekTo(pos) }
        })
    }

    override fun onGetRoot(
        clientPackageName: String,
        clientUid: Int,
        rootHints: Bundle?
    ): BrowserRoot {
        val extras = Bundle().apply {
            putBoolean("android.media.browseable", true)
        }
        return BrowserRoot(ROOT_ID, extras)
    }

    override fun onLoadChildren(parentId: String, result: Result<List<MediaItem>>) {
        result.detach()
        scope.launch(Dispatchers.IO) {
            try {
                val items = when (parentId) {
                    ROOT_ID -> getRootItems()
                    CATEGORY_CHARTS -> getChartCategories()
                    CATEGORY_TRENDING -> getTrendingTracks()
                    CATEGORY_NEW -> getNewReleases()
                    else -> {
                        if (parentId.startsWith("chart_")) {
                            getChartTracks(parentId.removePrefix("chart_"))
                        } else if (parentId.startsWith("album_")) {
                            getAlbumTracks(parentId.removePrefix("album_").toLong())
                        } else {
                            emptyList()
                        }
                    }
                }
                withContext(Dispatchers.Main) {
                    result.sendResult(items)
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    result.sendResult(emptyList())
                }
            }
        }
    }

    private fun getRootItems(): List<MediaItem> {
        return listOf(
            createBrowsableItem(CATEGORY_CHARTS, "Top 50 Charts", "Ascolta le classifiche mondiali"),
            createBrowsableItem(CATEGORY_TRENDING, "Del Momento", "I brani più popolari"),
            createBrowsableItem(CATEGORY_NEW, "Novità", "Le ultime uscite")
        )
    }

    private fun getChartCategories(): List<MediaItem> {
        return CHART_COUNTRIES.map { (code, name, flag) ->
            createBrowsableItem("chart_$code", "$flag Top 50 $name", "Classifica $name")
        }
    }

    private fun getChartTracks(country: String): List<MediaItem> {
        return try {
            val response = deezer?.getChart(country) ?: return emptyList()
            response.tracks.map { track ->
                createPlayableItem(
                    mediaId = track.id.toString(),
                    title = track.title,
                    artist = track.artist,
                    album = track.album,
                    artUri = track.cover,
                    duration = track.duration.toLong() * 1000
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun getTrendingTracks(): List<MediaItem> {
        return try {
            val response = deezer?.getTrending() ?: return emptyList()
            response.chartTracks.map { track ->
                createPlayableItem(
                    mediaId = track.id.toString(),
                    title = track.title,
                    artist = track.artist,
                    album = track.album,
                    artUri = track.cover,
                    duration = track.duration.toLong() * 1000
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun getNewReleases(): List<MediaItem> {
        return try {
            val response = deezer?.getTrending() ?: return emptyList()
            response.newReleases.map { album ->
                createBrowsableItem(
                    mediaId = "album_${album.id}",
                    title = album.title,
                    subtitle = album.artist
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun getAlbumTracks(albumId: Long): List<MediaItem> {
        return try {
            val response = deezer?.getAlbum(albumId) ?: return emptyList()
            response.tracks.map { track ->
                createPlayableItem(
                    mediaId = track.id.toString(),
                    title = track.title,
                    artist = track.artist,
                    album = track.album,
                    artUri = track.cover,
                    duration = track.duration.toLong() * 1000
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun createBrowsableItem(mediaId: String, title: String, subtitle: String = ""): MediaItem {
        val description = MediaDescriptionCompat.Builder()
            .setMediaId(mediaId)
            .setTitle(title)
            .setSubtitle(subtitle)
            .build()
        return MediaItem(description, MediaItem.FLAG_BROWSABLE)
    }

    private fun createPlayableItem(
        mediaId: String,
        title: String,
        artist: String,
        album: String = "",
        artUri: String,
        duration: Long
    ): MediaItem {
        val description = MediaDescriptionCompat.Builder()
            .setMediaId(mediaId)
            .setTitle(title)
            .setSubtitle(artist)
            .setDescription(album)
            .setIconUri(Uri.parse(artUri))
            .build()

        return MediaItem(description, MediaItem.FLAG_PLAYABLE)
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "D33Z3R Playback",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Riproduzione musicale"
            setShowBadge(false)
        }
        notificationManager.createNotificationChannel(channel)
    }

    private fun showNotification() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val metadata = player.session.controller.metadata
        val title = metadata?.getString(MediaMetadataCompat.METADATA_KEY_TITLE) ?: "D33Z3R"
        val artist = metadata?.getString(MediaMetadataCompat.METADATA_KEY_ARTIST) ?: ""

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(title)
            .setContentText(artist)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .addAction(android.R.drawable.ic_media_previous, "Previous",
                MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS))
            .addAction(
                if (player.isPlaying()) android.R.drawable.ic_media_pause
                else android.R.drawable.ic_media_play,
                if (player.isPlaying()) "Pause" else "Play",
                MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_PLAY_PAUSE)
            )
            .addAction(android.R.drawable.ic_media_next, "Next",
                MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_SKIP_TO_NEXT))
            .setStyle(
                androidx.media.app.NotificationCompat.MediaStyle()
                    .setMediaSession(player.session.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2)
                    .setShowCancelButton(true)
                    .setCancelButtonIntent(
                        MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_STOP)
                    )
            )

        notificationManager.notify(NOTIFICATION_ID, builder.build())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        MediaButtonReceiver.handleIntent(player.session, intent)
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        player.release()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    fun playTrack(trackId: String) {
        scope.launch(Dispatchers.IO) {
            try {
                android.util.Log.d("D33Z3R", "playTrack called: $trackId")
                val url = deezer?.getTrackUrl(trackId.toLong())
                android.util.Log.d("D33Z3R", "Got URL: ${url?.take(80)}")
                if (url != null) {
                    val tempFile = File(cacheDir, "track_${trackId}.mp3")

                    if (!tempFile.exists()) {
                        android.util.Log.d("D33Z3R", "Downloading encrypted...")
                        val encrypted = downloadEncrypted(url)
                        android.util.Log.d("D33Z3R", "Downloaded ${encrypted?.size ?: 0} bytes")
                        if (encrypted != null && encrypted.isNotEmpty()) {
                            val key = BlowfishDecryptor.generateKey(trackId)
                            android.util.Log.d("D33Z3R", "Decrypting...")
                            val decrypted = BlowfishDecryptor.decryptStream(key, encrypted)
                            android.util.Log.d("D33Z3R", "Decrypted ${decrypted.size} bytes, writing to ${tempFile.absolutePath}")
                            tempFile.writeBytes(decrypted)
                        }
                    } else {
                        android.util.Log.d("D33Z3R", "Using cached file: ${tempFile.absolutePath} (${tempFile.length()} bytes)")
                    }

                    if (tempFile.exists() && tempFile.length() > 0) {
                        withContext(Dispatchers.Main) {
                            android.util.Log.d("D33Z3R", "Playing from file: ${Uri.fromFile(tempFile)}")
                            player.play(Uri.fromFile(tempFile).toString())
                            showNotification()
                        }
                    } else {
                        android.util.Log.e("D33Z3R", "Temp file missing or empty")
                    }
                } else {
                    android.util.Log.e("D33Z3R", "Track URL is null for trackId=$trackId")
                }
            } catch (e: Exception) {
                android.util.Log.e("D33Z3R", "playTrack error", e)
            }
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
            null
        }
    }
}
