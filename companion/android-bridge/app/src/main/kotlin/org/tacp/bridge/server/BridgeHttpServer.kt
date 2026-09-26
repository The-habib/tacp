package org.tacp.bridge.server

import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import org.tacp.bridge.BridgeApp
import java.io.ByteArrayInputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class BridgeHttpServer(port: Int, private val authToken: String) : NanoHTTPD("127.0.0.1", port) {

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri
        val method = session.method

        if (authToken.isNotEmpty()) {
            val authHeader = session.headers["authorization"] ?: ""
            val expectedHeader = "Bearer $authToken"
            if (!authHeader.equals(expectedHeader, ignoreCase = true) && !authHeader.equals(authToken, ignoreCase = true)) {
                val err = JSONObject().apply {
                    put("error", "Unauthorized")
                    put("message", "Invalid or missing Authorization header")
                }
                return newFixedLengthResponse(Response.Status.UNAUTHORIZED, "application/json", err.toString())
            }
        }

        return when {
            method == Method.GET && uri == "/health" -> handleHealth()
            method == Method.POST && uri == "/tap" -> handleTap(session)
            method == Method.POST && uri == "/swipe" -> handleSwipe(session)
            method == Method.POST && uri == "/key" -> handleKey(session)
            method == Method.POST && uri == "/text" -> handleText(session)
            method == Method.GET && (uri == "/dump" || uri == "/nodes") -> handleDump()
            method == Method.GET && uri == "/screenshot" -> handleScreenshot()
            else -> newFixedLengthResponse(Response.Status.NOT_FOUND, "application/json", "{"error": "Not Found"}")
        }
    }

    private fun handleHealth(): Response {
        val acc = BridgeApp.accessibilityService != null
        val cap = BridgeApp.screenCaptureService != null
        val obj = JSONObject().apply {
            put("status", "ok")
            put("service", "tacp-android-bridge")
            put("version", "1.0.0")
            put("accessibility_enabled", acc)
            put("screen_capture_enabled", cap)
            put("port", listeningPort)
        }
        return newFixedLengthResponse(Response.Status.OK, "application/json", obj.toString())
    }

    private fun handleTap(session: IHTTPSession): Response {
        val acc = BridgeApp.accessibilityService
            ?: return serviceUnavailable("Accessibility service not enabled")

        val body = parseBody(session)
        val x = body.optDouble("x", 0.0).toFloat()
        val y = body.optDouble("y", 0.0).toFloat()

        val latch = CountDownLatch(1)
        var success = false

        acc.tap(x, y) { res ->
            success = res
            latch.countDown()
        }

        latch.await(2, TimeUnit.SECONDS)
        val resp = JSONObject().apply {
            put("success", success)
            put("x", x)
            put("y", y)
        }
        return newFixedLengthResponse(Response.Status.OK, "application/json", resp.toString())
    }

    private fun handleSwipe(session: IHTTPSession): Response {
        val acc = BridgeApp.accessibilityService
            ?: return serviceUnavailable("Accessibility service not enabled")

        val body = parseBody(session)
        val x1 = body.optDouble("x1", 0.0).toFloat()
        val y1 = body.optDouble("y1", 0.0).toFloat()
        val x2 = body.optDouble("x2", 0.0).toFloat()
        val y2 = body.optDouble("y2", 0.0).toFloat()
        val duration = body.optLong("duration", 300L)

        val latch = CountDownLatch(1)
        var success = false

        acc.swipe(x1, y1, x2, y2, duration) { res ->
            success = res
            latch.countDown()
        }

        latch.await(3, TimeUnit.SECONDS)
        val resp = JSONObject().apply {
            put("success", success)
            put("x1", x1)
            put("y1", y1)
            put("x2", x2)
            put("y2", y2)
        }
        return newFixedLengthResponse(Response.Status.OK, "application/json", resp.toString())
    }

    private fun handleKey(session: IHTTPSession): Response {
        val acc = BridgeApp.accessibilityService
            ?: return serviceUnavailable("Accessibility service not enabled")

        val body = parseBody(session)
        val key = body.optString("key", "BACK")
        val success = acc.performGlobal(key)

        val resp = JSONObject().apply {
            put("success", success)
            put("key", key)
        }
        return newFixedLengthResponse(Response.Status.OK, "application/json", resp.toString())
    }

    private fun handleText(session: IHTTPSession): Response {
        val acc = BridgeApp.accessibilityService
            ?: return serviceUnavailable("Accessibility service not enabled")

        val body = parseBody(session)
        val text = body.optString("text", "")
        val success = acc.setFocusedText(text)

        val resp = JSONObject().apply {
            put("success", success)
            put("text", text)
        }
        return newFixedLengthResponse(Response.Status.OK, "application/json", resp.toString())
    }

    private fun handleDump(): Response {
        val acc = BridgeApp.accessibilityService
            ?: return serviceUnavailable("Accessibility service not enabled")

        val dump = acc.dumpHierarchy()
        return newFixedLengthResponse(Response.Status.OK, "application/json", dump.toString())
    }

    private fun handleScreenshot(): Response {
        val cap = BridgeApp.screenCaptureService
            ?: return serviceUnavailable("Screen capture service not running")

        val bytes = cap.captureScreenshotJpeg(80)
            ?: return newFixedLengthResponse(Response.Status.INTERNAL_ERROR, "application/json", "{"error":"Capture failed"}")

        return newFixedLengthResponse(
            Response.Status.OK,
            "image/jpeg",
            ByteArrayInputStream(bytes),
            bytes.size.toLong()
        )
    }

    private fun parseBody(session: IHTTPSession): JSONObject {
        val files = HashMap<String, String>()
        session.parseBody(files)
        val postData = files["postData"] ?: ""
        return if (postData.isNotEmpty()) {
            try { JSONObject(postData) } catch (e: Exception) { JSONObject() }
        } else {
            JSONObject()
        }
    }

    private fun serviceUnavailable(message: String): Response {
        val obj = JSONObject().apply {
            put("error", message)
            put("available", false)
        }
        return newFixedLengthResponse(Response.Status.SERVICE_UNAVAILABLE, "application/json", obj.toString())
    }
}
