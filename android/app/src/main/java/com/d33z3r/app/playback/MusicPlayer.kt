package com.d33z3r.app.playback

import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.exoplayer.ExoPlayer

class MusicPlayer(private val context: Context) {

    private var exoPlayer: ExoPlayer? = null
    private var _session: MediaSessionCompat? = null
    val session: MediaSessionCompat get() = _session!!

    private var currentTrackId: String? = null

    init {
        _session = MediaSessionCompat(context, "D33Z3R").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() {
                    exoPlayer?.let {
                        if (it.isPlaying) it.pause() else it.play()
                        updatePlaybackState()
                    }
                }

                override fun onPause() {
                    exoPlayer?.pause()
                    updatePlaybackState()
                }

                override fun onSkipToNext() {
                    // Handle next track
                }

                override fun onSkipToPrevious() {
                    // Handle previous track
                }

                override fun onSeekTo(pos: Long) {
                    exoPlayer?.seekTo(pos)
                    updatePlaybackState()
                }

                override fun onStop() {
                    exoPlayer?.stop()
                    updatePlaybackState()
                }
            })
            isActive = true
        }
    }

    fun play(url: String) {
        if (exoPlayer == null) {
            val audioAttributes = AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                .build()
            exoPlayer = ExoPlayer.Builder(context).build().apply {
                setAudioAttributes(audioAttributes, true)

                addListener(object : Player.Listener {
                    override fun onPlaybackStateChanged(playbackState: Int) {
                        when (playbackState) {
                            Player.STATE_READY -> {
                                updatePlaybackState()
                            }
                            Player.STATE_ENDED -> {
                                updatePlaybackState()
                            }
                            Player.STATE_BUFFERING -> {
                                updatePlaybackState()
                            }
                        }
                    }

                    override fun onIsPlayingChanged(isPlaying: Boolean) {
                        updatePlaybackState()
                    }
                })
            }
        }

        currentTrackId = url
        val mediaItem = MediaItem.fromUri(Uri.parse(url))
        exoPlayer?.setMediaItem(mediaItem)
        exoPlayer?.prepare()
        exoPlayer?.play()
    }

    fun pause() {
        exoPlayer?.pause()
        updatePlaybackState()
    }

    fun resume() {
        exoPlayer?.play()
        updatePlaybackState()
    }

    fun seekTo(position: Long) {
        exoPlayer?.seekTo(position)
        updatePlaybackState()
    }

    fun release() {
        exoPlayer?.release()
        exoPlayer = null
        _session?.release()
        _session = null
    }

    fun isPlaying(): Boolean = exoPlayer?.isPlaying == true

    private fun updatePlaybackState() {
        val player = exoPlayer ?: return
        val state = when (player.playbackState) {
            Player.STATE_READY -> if (player.isPlaying) {
                PlaybackStateCompat.STATE_PLAYING
            } else {
                PlaybackStateCompat.STATE_PAUSED
            }
            Player.STATE_BUFFERING -> PlaybackStateCompat.STATE_BUFFERING
            Player.STATE_ENDED -> PlaybackStateCompat.STATE_STOPPED
            else -> PlaybackStateCompat.STATE_NONE
        }

        val playbackState = PlaybackStateCompat.Builder()
            .setActions(
                PlaybackStateCompat.ACTION_PLAY or
                PlaybackStateCompat.ACTION_PAUSE or
                PlaybackStateCompat.ACTION_SEEK_TO or
                PlaybackStateCompat.ACTION_PLAY_PAUSE
            )
            .setState(state, player.currentPosition, 1f)
            .build()

        session.setPlaybackState(playbackState)
    }

    fun updateMetadata(title: String, artist: String, artUri: String?, duration: Long) {
        val metadata = MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, title)
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, artist)
            .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, duration)
            .apply {
                if (artUri != null) {
                    putString(MediaMetadataCompat.METADATA_KEY_ALBUM_ART_URI, artUri)
                }
            }
            .build()
        session.setMetadata(metadata)
    }
}
