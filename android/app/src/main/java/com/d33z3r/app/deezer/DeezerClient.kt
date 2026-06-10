package com.d33z3r.app.deezer

import android.util.Log
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import java.net.InetAddress
import java.net.UnknownHostException

data class Track(
    val id: Long,
    val title: String = "",
    val artist: String = "",
    val artistId: Long? = null,
    val album: String = "",
    val albumId: Long? = null,
    val cover: String = "",
    val duration: Int = 0,
    val preview: String = "",
    val position: Int = 0
)

data class Album(
    val id: Long,
    val title: String = "",
    val artist: String = "",
    val artistId: Long? = null,
    val cover: String = "",
    val nbTracks: Int = 0
)

data class Playlist(
    val id: Long,
    val name: String = "",
    val image: String = "",
    val owner: String = "",
    val nbTracks: Int = 0
)

data class Artist(
    val id: Long,
    val name: String = "",
    val image: String = "",
    val nbAlbum: Int = 0
)

data class TrendingResponse(
    @SerializedName("chart_tracks") val chartTracks: List<Track> = emptyList(),
    @SerializedName("chart_albums") val chartAlbums: List<Album> = emptyList(),
    @SerializedName("chart_playlists") val chartPlaylists: List<Playlist> = emptyList(),
    @SerializedName("new_releases") val newReleases: List<Album> = emptyList()
)

data class ChartResponse(
    val playlist: Playlist? = null,
    val tracks: List<Track> = emptyList(),
    val country: String = "",
    val name: String = "",
    val flag: String = ""
)

data class AlbumResponse(
    val album: Album? = null,
    val tracks: List<Track> = emptyList()
)

data class ArtistResponse(
    val artist: Artist? = null,
    val top: List<Track> = emptyList(),
    val albums: List<Album> = emptyList()
)

data class SearchResponse(
    val tracks: List<Track> = emptyList(),
    val playlists: List<Playlist> = emptyList(),
    val albums: List<Album> = emptyList(),
    val artists: List<Artist> = emptyList()
)

class DeezerClient(private val arl: String) {

    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .dns(FallbackDns())
        .build()

    private var gwToken: String? = null
    private var licenseToken: String? = null
    private var loggedIn = false

    companion object {
        private const val TAG = "D33Z3R"
        private const val BLOWFISH_SECRET = "g4el58wc0zvf9na1"
        private const val CDN_URL = "https://media.deezer.com/v1/get_url"
        private const val GW_BASE = "https://www.deezer.com/ajax/gw-light.php"
    }

    fun login(): Boolean {
        if (loggedIn) return true
        try {
            val pageRequest = Request.Builder()
                .url("https://www.deezer.com/")
                .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                .build()
            client.newCall(pageRequest).execute().use { it.close() }

            val tokenRequest = Request.Builder()
                .url("$GW_BASE?method=deezer.getUserData&input=3&api_version=1.0&api_token=null")
                .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                .header("Cookie", "arl=$arl")
                .post(RequestBody.create(null, byteArrayOf()))
                .build()

            client.newCall(tokenRequest).execute().use { tokenResponse ->
                val tokenBody = tokenResponse.body?.string() ?: return false
                Log.d(TAG, "getUserData raw response: ${tokenBody.take(500)}")
                val tokenData = gson.fromJson(tokenBody, Map::class.java)
                val results = tokenData["results"] as? Map<*, *> ?: return false
                
                gwToken = results["checkForm"] as? String
                
                val user = results["USER"] as? Map<*, *>
                val options = user?.get("OPTIONS") as? Map<*, *>
                licenseToken = options?.get("license_token") as? String
                
                Log.d(TAG, "Parsed gwToken: $gwToken, licenseToken: $licenseToken")
                val userIdDouble = user?.get("USER_ID")
                val userId = when (userIdDouble) {
                    is Double -> userIdDouble.toLong()
                    is Long -> userIdDouble
                    is Int -> userIdDouble.toLong()
                    is String -> userIdDouble.toLongOrNull() ?: 0L
                    else -> 0L
                }
                loggedIn = !licenseToken.isNullOrEmpty() && userId != 0L
                return loggedIn
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return false
        }
    }


    fun getTrackUrl(trackId: Long): String? {
        val success = if (!loggedIn) login() else true
        Log.d(TAG, "getTrackUrl trackId=$trackId loggedIn=$loggedIn (success=$success) licenseToken=$licenseToken")
        return try {
            val trackToken = getTrackToken(trackId)
            if (trackToken.isEmpty()) {
                Log.e(TAG, "Empty track token for trackId=$trackId")
                return null
            }

            val body = """
                {
                    "license_token": "$licenseToken",
                    "media": [{"type": "FULL", "formats": [{"cipher": "BF_CBC_STRIPE", "format": "MP3_128"}]}],
                    "track_tokens": ["$trackToken"]
                }
            """.trimIndent()

            Log.d(TAG, "getTrackUrl trackId=$trackId")

            val request = Request.Builder()
                .url(CDN_URL)
                .header("User-Agent", "Deezer/6.23.0.0")
                .header("Cookie", "arl=$arl")
                .header("Content-Type", "application/json")
                .post(RequestBody.create(
                    "application/json".toMediaTypeOrNull(),
                    body.toByteArray()
                ))
                .build()

            val response = client.newCall(request).execute()
            val responseBody = response.body?.string() ?: return null
            Log.d(TAG, "CDN response: ${responseBody.take(300)}")

            val data = gson.fromJson(responseBody, Map::class.java)
            val mediaList = data["data"] as? List<*> ?: return null
            val media = mediaList.firstOrNull() as? Map<*, *> ?: return null
            val mediaItems = media["media"] as? List<*> ?: return null
            val mediaItem = mediaItems.firstOrNull() as? Map<*, *> ?: return null
            val sources = mediaItem["sources"] as? List<*> ?: return null
            val source = sources.firstOrNull() as? Map<*, *>
            val url = source?.get("url") as? String
            Log.d(TAG, "Stream URL: ${url?.take(80)}")
            url
        } catch (e: Exception) {
            Log.e(TAG, "getTrackUrl error", e)
            null
        }
    }

    fun getTrackToken(trackId: Long): String {
        val trackData = getJson("https://api.deezer.com/track/$trackId")
        val token = trackData["track_token"] as? String
        Log.d("D33Z3R", "getTrackToken from API: ${token?.take(30)}...")
        return token ?: ""
    }

    fun getTrending(): TrendingResponse {
        if (!loggedIn) login()
        return try {
            val charts = getJson("https://api.deezer.com/chart")
            val releases = getJson("https://api.deezer.com/editorial/0/releases")

            TrendingResponse(
                chartTracks = parseTracks((charts["tracks"] as? Map<*, *>)?.get("data") as? List<*>),
                chartAlbums = parseAlbums((charts["albums"] as? Map<*, *>)?.get("data") as? List<*>),
                chartPlaylists = parsePlaylists((charts["playlists"] as? Map<*, *>)?.get("data") as? List<*>),
                newReleases = parseAlbums(releases["data"] as? List<*>)
            )
        } catch (e: Exception) {
            TrendingResponse()
        }
    }

    fun getChart(country: String): ChartResponse {
        if (!loggedIn) login()
        val countryIds = mapOf(
            "worldwide" to 3155776842L,
            "italy" to 1116187241L,
            "france" to 1109890291L,
            "usa" to 1313621735L,
            "uk" to 1111142221L,
            "germany" to 1111143121L,
            "spain" to 1116190041L,
            "brazil" to 1111141961L,
            "japan" to 1362508955L
        )

        val countryNames = mapOf(
            "worldwide" to "Worldwide",
            "italy" to "Italia",
            "france" to "France",
            "usa" to "USA",
            "uk" to "UK",
            "germany" to "Germany",
            "spain" to "Spain",
            "brazil" to "Brazil",
            "japan" to "Japan"
        )

        val countryFlags = mapOf(
            "worldwide" to "\uD83C\uDF0D",
            "italy" to "\uD83C\uDDEE\uD83C\uDDF9",
            "france" to "\uD83C\uDDEB\uD83C\uDDF7",
            "usa" to "\uD83C\uDDFA\uD83C\uDDF8",
            "uk" to "\uD83C\uDDEC\uD83C\uDDE7",
            "germany" to "\uD83C\uDDE9\uD83C\uDDEA",
            "spain" to "\uD83C\uDDEA\uD83C\uDDF8",
            "brazil" to "\uD83C\uDDE7\uD83C\uDDF7",
            "japan" to "\uD83C\uDDEF\uD83C\uDDF5"
        )

        val pid = countryIds[country] ?: return ChartResponse()
        return try {
            val plData = getJson("https://api.deezer.com/playlist/$pid")
            val tracksData = getJson("https://api.deezer.com/playlist/$pid/tracks?limit=50")

            ChartResponse(
                playlist = parsePlaylist(plData),
                tracks = parseTracks(tracksData["data"] as? List<*>),
                country = country,
                name = countryNames[country] ?: country,
                flag = countryFlags[country] ?: "\uD83C\uDFB5"
            )
        } catch (e: Exception) {
            ChartResponse()
        }
    }

    fun getAlbum(id: Long): AlbumResponse {
        return try {
            val alData = getJson("https://api.deezer.com/album/$id")
            val tracksData = getJson("https://api.deezer.com/album/$id/tracks")
            val albumCover = alData["cover_medium"] as? String ?: ""

            val tracks = parseTracks(tracksData["data"] as? List<*>).map { t ->
                if (t.cover.isEmpty()) t.copy(cover = albumCover) else t
            }

            AlbumResponse(
                album = parseAlbum(alData),
                tracks = tracks
            )
        } catch (e: Exception) {
            AlbumResponse()
        }
    }

    fun getArtist(id: Long): ArtistResponse {
        return try {
            val artistData = getJson("https://api.deezer.com/artist/$id")
            val topData = getJson("https://api.deezer.com/artist/$id/top?limit=20")
            val albumsData = getJson("https://api.deezer.com/artist/$id/albums?limit=20")

            ArtistResponse(
                artist = parseArtist(artistData),
                top = parseTracks(topData["data"] as? List<*>),
                albums = parseAlbums(albumsData["data"] as? List<*>)
            )
        } catch (e: Exception) {
            ArtistResponse()
        }
    }

    fun getPlaylist(id: Long): AlbumResponse {
        return try {
            val plData = getJson("https://api.deezer.com/playlist/$id")
            val tracksData = getJson("https://api.deezer.com/playlist/$id/tracks?limit=100")

            AlbumResponse(
                album = Album(
                    id = plData["id"] as? Long ?: 0,
                    title = plData["title"] as? String ?: "",
                    artist = (plData["user"] as? Map<*, *>)?.get("name") as? String ?: "",
                    cover = plData["picture_medium"] as? String ?: "",
                    nbTracks = (plData["nb_tracks"] as? Long)?.toInt() ?: 0
                ),
                tracks = parseTracks(tracksData["data"] as? List<*>)
            )
        } catch (e: Exception) {
            AlbumResponse()
        }
    }

    fun search(query: String): SearchResponse {
        if (!loggedIn) login()
        return try {
            val tracks = getJson("https://api.deezer.com/search?q=$query&limit=30")
            val playlists = getJson("https://api.deezer.com/search/playlist?q=$query&limit=10")
            val albums = getJson("https://api.deezer.com/search/album?q=$query&limit=10")
            val artists = getJson("https://api.deezer.com/search/artist?q=$query&limit=8")

            SearchResponse(
                tracks = parseTracks(tracks["data"] as? List<*>),
                playlists = parsePlaylists(playlists["data"] as? List<*>),
                albums = parseAlbums(albums["data"] as? List<*>),
                artists = parseArtists(artists["data"] as? List<*>)
            )
        } catch (e: Exception) {
            SearchResponse()
        }
    }

    private fun getJson(url: String): Map<*, *> {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "Mozilla/5.0")
            .build()
        val response = client.newCall(request).execute()
        val body = response.body?.string() ?: "{}"
        return gson.fromJson(body, Map::class.java)
    }

    private fun parseTracks(data: List<*>?): List<Track> {
        return data?.mapNotNull { item ->
            val t = item as? Map<*, *> ?: return@mapNotNull null
            val album = t["album"] as? Map<*, *>
            Track(
                id = toLong(t["id"]),
                title = t["title"] as? String ?: "",
                artist = (t["artist"] as? Map<*, *>)?.get("name") as? String ?: "",
                artistId = toLongOrNull((t["artist"] as? Map<*, *>)?.get("id")),
                album = album?.get("title") as? String ?: "",
                albumId = toLongOrNull(album?.get("id")),
                cover = album?.get("cover_medium") as? String ?: "",
                duration = toInt(t["duration"]),
                preview = t["preview"] as? String ?: "",
                position = toInt(t["position"])
            )
        } ?: emptyList()
    }

    private fun parseAlbums(data: List<*>?): List<Album> {
        return data?.mapNotNull { item ->
            val a = item as? Map<*, *> ?: return@mapNotNull null
            parseAlbum(a)
        } ?: emptyList()
    }

    private fun parseAlbum(a: Map<*, *>): Album {
        return Album(
            id = toLong(a["id"]),
            title = a["title"] as? String ?: "",
            artist = (a["artist"] as? Map<*, *>)?.get("name") as? String ?: "",
            artistId = toLongOrNull((a["artist"] as? Map<*, *>)?.get("id")),
            cover = a["cover_medium"] as? String ?: a["cover"] as? String ?: "",
            nbTracks = toInt(a["nb_tracks"])
        )
    }

    private fun parsePlaylists(data: List<*>?): List<Playlist> {
        return data?.mapNotNull { item ->
            val p = item as? Map<*, *> ?: return@mapNotNull null
            parsePlaylist(p)
        } ?: emptyList()
    }

    private fun parsePlaylist(p: Map<*, *>): Playlist {
        return Playlist(
            id = toLong(p["id"]),
            name = p["title"] as? String ?: "",
            image = p["picture_medium"] as? String ?: "",
            owner = (p["user"] as? Map<*, *>)?.get("name") as? String ?: "",
            nbTracks = toInt(p["nb_tracks"])
        )
    }

    private fun parseArtists(data: List<*>?): List<Artist> {
        return data?.mapNotNull { item ->
            val a = item as? Map<*, *> ?: return@mapNotNull null
            Artist(
                id = toLong(a["id"]),
                name = a["name"] as? String ?: "",
                image = a["picture_medium"] as? String ?: "",
                nbAlbum = toInt(a["nb_album"])
            )
        } ?: emptyList()
    }

    private fun parseArtist(a: Map<*, *>): Artist {
        return Artist(
            id = toLong(a["id"]),
            name = a["name"] as? String ?: "",
            image = a["picture_medium"] as? String ?: "",
            nbAlbum = toInt(a["nb_album"])
        )
    }

    private fun toLong(value: Any?): Long {
        return when (value) {
            is Long -> value
            is Double -> value.toLong()
            is Int -> value.toLong()
            is String -> value.toLongOrNull() ?: 0L
            else -> 0L
        }
    }

    private fun toLongOrNull(value: Any?): Long? {
        return when (value) {
            is Long -> value
            is Double -> value.toLong()
            is Int -> value.toLong()
            is String -> value.toLongOrNull()
            else -> null
        }
    }

    private fun toInt(value: Any?): Int {
        return when (value) {
            is Long -> value.toInt()
            is Double -> value.toInt()
            is Int -> value
            is String -> value.toIntOrNull() ?: 0
            else -> 0
        }
    }
}

object BlowfishDecryptor {
    private val BLOWFISH_SECRET = "g4el58wc0zvf9na1"
    private val CHUNK_SIZE = 2048 * 3

    fun generateKey(trackId: String): ByteArray {
        val md5 = MessageDigest.getInstance("MD5")
        val key = md5.digest(trackId.toByteArray())
        val secret = BLOWFISH_SECRET.toByteArray()

        val generatedKey = ByteArray(16)
        for (i in 0 until 16) {
            generatedKey[i] = (key[i].toInt() xor secret[i % secret.size].toInt()).toByte()
        }
        return generatedKey
    }

    fun decryptChunk(key: ByteArray, data: ByteArray, offset: Int = 0): ByteArray {
        val iv = ByteArray(8)
        for (i in 0 until 8) {
            iv[i] = if (offset + i < data.size) data[offset + i] else 0
        }

        val cipher = Cipher.getInstance("Blowfish/CBC/PKCS5Padding")
        val keySpec = SecretKeySpec(key, "Blowfish")
        val ivSpec = IvParameterSpec(iv)
        cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec)

        val input = data.copyOfRange(offset + 8, minOf(offset + CHUNK_SIZE, data.size))
        return cipher.doFinal(input)
    }

    fun decryptStream(key: ByteArray, encryptedData: ByteArray): ByteArray {
        val result = mutableListOf<Byte>()
        var offset = 0

        while (offset < encryptedData.size) {
            val chunkSize = minOf(CHUNK_SIZE, encryptedData.size - offset)
            val chunk = encryptedData.copyOfRange(offset, offset + chunkSize)

            if (chunk.size >= 16) {
                val decrypted = decryptChunk(key, chunk, 0)
                result.addAll(decrypted.toList())
            } else {
                result.addAll(chunk.toList())
            }

            offset += CHUNK_SIZE
        }

        return result.toByteArray()
    }
}

class FallbackDns : Dns {
    override fun lookup(hostname: String): List<InetAddress> {
        try {
            return Dns.SYSTEM.lookup(hostname)
        } catch (e: UnknownHostException) {
            Log.w("D33Z3R", "System DNS failed for $hostname, trying fallback DoH via 8.8.8.8")
            try {
                val trustAllCerts = arrayOf<javax.net.ssl.TrustManager>(
                    object : javax.net.ssl.X509TrustManager {
                        override fun checkClientTrusted(chain: Array<java.security.cert.X509Certificate>, authType: String) {}
                        override fun checkServerTrusted(chain: Array<java.security.cert.X509Certificate>, authType: String) {}
                        override fun getAcceptedIssuers(): Array<java.security.cert.X509Certificate> = arrayOf()
                    }
                )
                val sslContext = javax.net.ssl.SSLContext.getInstance("SSL")
                sslContext.init(null, trustAllCerts, java.security.SecureRandom())

                val client = okhttp3.OkHttpClient.Builder()
                    .connectTimeout(5, java.util.concurrent.TimeUnit.SECONDS)
                    .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as javax.net.ssl.X509TrustManager)
                    .hostnameVerifier { _, _ -> true }
                    .build()

                val req = okhttp3.Request.Builder()
                    .url("https://8.8.8.8/resolve?name=$hostname&type=A")
                    .build()

                val resp = client.newCall(req).execute()
                val body = resp.body?.string() ?: ""
                val gson = com.google.gson.Gson()
                val data = gson.fromJson(body, Map::class.java)
                val answer = data["Answer"] as? List<*>
                val addresses = mutableListOf<InetAddress>()
                if (answer != null) {
                    for (item in answer) {
                        val map = item as? Map<*, *>
                        val type = (map?.get("type") as? Double)?.toInt() ?: 0
                        val ip = map?.get("data") as? String
                        if (type == 1 && ip != null) {
                            addresses.add(InetAddress.getByName(ip))
                        }
                    }
                }
                if (addresses.isNotEmpty()) {
                    Log.d("D33Z3R", "Fallback DNS resolved $hostname to ${addresses.map { it.hostAddress }}")
                    return addresses
                }
            } catch (ex: Exception) {
                Log.e("D33Z3R", "Fallback DNS lookup failed for $hostname", ex)
            }
            throw e
        }
    }
}
