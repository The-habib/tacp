package org.tacp.bridge

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.util.DisplayMetrics
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import org.tacp.bridge.service.ScreenCaptureService

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var btnAccessibility: Button
    private lateinit var btnScreenCapture: Button
    private lateinit var tokenText: TextView

    companion object {
        private const val REQUEST_MEDIA_PROJECTION = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Simple programmatic layout
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 64, 48, 64)
        }

        val title = TextView(this).apply {
            text = "TACP Android Bridge Companion"
            textSize = 22f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 32)
        }
        layout.addView(title)

        statusText = TextView(this).apply {
            textSize = 15f
            setPadding(0, 0, 0, 24)
        }
        layout.addView(statusText)

        btnAccessibility = Button(this).apply {
            text = "Enable Accessibility Service"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }
        layout.addView(btnAccessibility)

        btnScreenCapture = Button(this).apply {
            text = "Start Screen Capture"
            setOnClickListener {
                val projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                startActivityForResult(projectionManager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION)
            }
        }
        layout.addView(btnScreenCapture)

        tokenText = TextView(this).apply {
            text = "Token: ${BridgeApp.authToken}\nPort: ${BridgeApp.DEFAULT_PORT}"
            textSize = 13f
            setPadding(0, 32, 0, 0)
        }
        layout.addView(tokenText)

        setContentView(layout)
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
    }

    private fun updateStatus() {
        val acc = BridgeApp.accessibilityService != null
        val cap = BridgeApp.screenCaptureService != null
        val s = "Bridge Server: Running on 127.0.0.1:${BridgeApp.DEFAULT_PORT}\n" +
                "Accessibility Service: ${if (acc) "ENABLED" else "DISABLED"}\n" +
                "Screen Capture: ${if (cap) "ACTIVE" else "IDLE"}"
        statusText.text = s
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_MEDIA_PROJECTION && resultCode == Activity.RESULT_OK && data != null) {
            val metrics = DisplayMetrics()
            windowManager.defaultDisplay.getRealMetrics(metrics)

            val serviceIntent = Intent(this, ScreenCaptureService::class.java).apply {
                putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode)
                putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, data)
                putExtra(ScreenCaptureService.EXTRA_WIDTH, metrics.widthPixels)
                putExtra(ScreenCaptureService.EXTRA_HEIGHT, metrics.heightPixels)
                putExtra(ScreenCaptureService.EXTRA_DENSITY, metrics.densityDpi)
            }
            startForegroundService(serviceIntent)
            updateStatus()
        }
    }
}
