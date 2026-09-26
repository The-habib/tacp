package org.tacp.bridge.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import org.tacp.bridge.BridgeApp

class AccessibilityControlService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        BridgeApp.accessibilityService = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Can be used to track window state changes
    }

    override fun onInterrupt() {
        BridgeApp.accessibilityService = null
    }

    override fun onDestroy() {
        super.onDestroy()
        BridgeApp.accessibilityService = null
    }

    fun tap(x: Float, y: Float, callback: (Boolean) -> Unit) {
        val path = Path().apply {
            moveTo(x, y)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 50)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                callback(true)
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                callback(false)
            }
        }, null)
    }

    fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, durationMs: Long, callback: (Boolean) -> Unit) {
        val path = Path().apply {
            moveTo(x1, y1)
            lineTo(x2, y2)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs.coerceAtLeast(100))
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                callback(true)
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                callback(false)
            }
        }, null)
    }

    fun performGlobal(action: String): Boolean {
        return when (action.uppercase()) {
            "BACK" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "HOME" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "RECENTS" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
            "NOTIFICATIONS" -> performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
            "QUICK_SETTINGS" -> performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
            "POWER_DIALOG" -> performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
            "LOCK_SCREEN" -> performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN)
            "TAKE_SCREENSHOT" -> performGlobalAction(GLOBAL_ACTION_TAKE_SCREENSHOT)
            else -> false
        }
    }

    fun setFocusedText(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return false
        val arguments = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
    }

    fun dumpHierarchy(): JSONObject {
        val root = rootInActiveWindow ?: return JSONObject().apply {
            put("error", "No active window")
        }
        return nodeToJson(root)
    }

    private fun nodeToJson(node: AccessibilityNodeInfo): JSONObject {
        val obj = JSONObject()
        obj.put("className", node.className?.toString() ?: "")
        obj.put("packageName", node.packageName?.toString() ?: "")
        obj.put("text", node.text?.toString() ?: "")
        obj.put("contentDescription", node.contentDescription?.toString() ?: "")
        obj.put("viewIdResourceName", node.viewIdResourceName ?: "")
        obj.put("clickable", node.isClickable)
        obj.put("focusable", node.isFocusable)
        obj.put("focused", node.isFocused)
        obj.put("scrollable", node.isScrollable)
        obj.put("editable", node.isEditable)
        obj.put("visibleToUser", node.isVisibleToUser)

        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        val rectObj = JSONObject().apply {
            put("left", bounds.left)
            put("top", bounds.top)
            put("right", bounds.right)
            put("bottom", bounds.bottom)
            put("centerX", bounds.centerX())
            put("centerY", bounds.centerY())
        }
        obj.put("bounds", rectObj)

        val childrenArray = JSONArray()
        for (i in 0 until node.childCount) {
            val child = node.getChild(i)
            if (child != null) {
                childrenArray.put(nodeToJson(child))
            }
        }
        obj.put("children", childrenArray)
        return obj
    }
}
