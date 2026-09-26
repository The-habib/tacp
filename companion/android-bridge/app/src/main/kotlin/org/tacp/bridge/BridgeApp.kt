package org.tacp.bridge

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import org.tacp.bridge.server.BridgeHttpServer
import org.tacp.bridge.service.AccessibilityControlService
import org.tacp.bridge.service.ScreenCaptureService

class BridgeApp : Application() {

    companion object {
        const val CHANNEL_ID = "tacp_bridge_channel"
        const val CHANNEL_NAME = "TACP Android Bridge Service"
        const val DEFAULT_PORT = 8989

        lateinit var instance: BridgeApp
            private set

        var accessibilityService: AccessibilityControlService? = null
        var screenCaptureService: ScreenCaptureService? = null
        var httpServer: BridgeHttpServer? = null
        var authToken: String = "tacp-bridge-local-token"
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        startHttpServer()
    }

    fun startHttpServer(port: Int = DEFAULT_PORT) {
        if (httpServer == null || !httpServer!!.isAlive) {
            try {
                httpServer = BridgeHttpServer(port, authToken)
                httpServer!!.start()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    fun stopHttpServer() {
        httpServer?.stop()
        httpServer = null
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Runs local TACP device control bridge"
            }
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }
}
