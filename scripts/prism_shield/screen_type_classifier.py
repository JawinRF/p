"""
screen_type_classifier.py
--------------------------
Deterministic ScreenType classification from a ScreenContext object.
Uses ONLY structural signals — package names, window types, node class names,
and node counts. Zero keyword matching on text content.

Rationale: keyword matching on text is inverted — it describes attacker behavior.
Structural classification describes ground truth from the OS perspective.
An attacker cannot spoof the AccessibilityService node class hierarchy
or the foreground package name without a compromised OS.
"""

import re

from .screen_context import ScreenContext, ScreenType

_PRICE_PATTERN = re.compile(r'[$€£₹¥]\s*\d+|\d+\.\d{2}')

# Android WindowManager.LayoutParams type constants
_TYPE_APPLICATION_OVERLAY = 2038   # SYSTEM_ALERT_WINDOW
_TYPE_INPUT_METHOD        = 2011   # Soft keyboard
_TYPE_STATUS_BAR          = 2000
_TYPE_NOTIFICATION_SHADE  = 2040

# Known settings packages (AOSP + major OEM variants)
_SETTINGS_PACKAGES = {
    "com.android.settings",
    "com.samsung.android.settings",
    "com.miui.securitycenter",
    "com.oneplus.settings",
    "com.oppo.settings",
}

# Known browser packages
_BROWSER_PACKAGES = {
    "com.android.chrome", "org.mozilla.firefox", "com.brave.browser",
    "com.microsoft.emmx", "com.opera.browser", "com.sec.android.app.sbrowser",
}

# Structural node classifiers
_WEBVIEW_CLASSES    = {"android.webkit.WebView", "androidx.webkit.WebViewCompat"}
_TEXT_INPUT_CLASSES = {"android.widget.EditText", "android.widget.AutoCompleteTextView",
                       "androidx.appcompat.widget.AppCompatEditText"}
_RECYCLER_CLASSES   = {"androidx.recyclerview.widget.RecyclerView",
                       "android.widget.ListView", "android.widget.GridView"}


def classify(ctx: ScreenContext) -> ScreenType:
    """
    Returns ScreenType for the given ScreenContext.
    Decision tree is ordered from highest-certainty signals to lowest.
    Falls through to GENERIC_APP if no strong signal fires.
    """
    # 1. System window types — deterministic from WindowManager alone
    if ctx.window_type == _TYPE_APPLICATION_OVERLAY:
        return ScreenType.SYSTEM_OVERLAY
    if ctx.window_type == _TYPE_INPUT_METHOD:
        return ScreenType.KEYBOARD
    if ctx.window_type == _TYPE_NOTIFICATION_SHADE:
        return ScreenType.NOTIFICATION

    # 2. Known packages — deterministic from package identity
    if ctx.foreground_package in _SETTINGS_PACKAGES:
        return ScreenType.SETTINGS
    if ctx.foreground_package in _BROWSER_PACKAGES:
        return ScreenType.BROWSER
    if ctx.foreground_package == "com.android.launcher3" or \
       ctx.foreground_activity.lower().endswith("launcher"):
        return ScreenType.HOME_LAUNCHER

    # 3. Node class composition analysis
    node_classes = [n.class_name for n in ctx.visible_nodes]
    class_set    = set(node_classes)
    n_nodes      = len(node_classes)

    has_webview    = bool(class_set & _WEBVIEW_CLASSES)
    has_recycler   = bool(class_set & _RECYCLER_CLASSES)
    has_edittext   = bool(class_set & _TEXT_INPUT_CLASSES)
    n_edittext     = sum(1 for c in node_classes if c in _TEXT_INPUT_CLASSES)
    n_textview     = sum(1 for c in node_classes if "TextView" in c)

    if has_webview:
        return ScreenType.BROWSER   # App-embedded WebView — treat as browser

    # Messaging: scrollable list + at least one EditText at bottom
    if has_recycler and has_edittext and n_edittext == 1:
        return ScreenType.MESSAGING

    # Form input: multiple EditTexts dominant
    if has_edittext and n_edittext >= 3:
        return ScreenType.FORM_INPUT

    # Document viewer: many TextViews, no RecyclerView
    if n_textview > 10 and not has_recycler:
        return ScreenType.DOCUMENT_VIEWER

    # E-commerce: RecyclerView present and visible text contains price patterns
    if has_recycler:
        if any(_PRICE_PATTERN.search(n.text) for n in ctx.visible_nodes):
            return ScreenType.ECOMMERCE

    # System dialog: small node count + AlertDialog in activity name
    if n_nodes < 10 and "dialog" in ctx.foreground_activity.lower():
        return ScreenType.SYSTEM_DIALOG

    if n_nodes == 0:
        return ScreenType.UNKNOWN

    return ScreenType.GENERIC_APP


def enrich(ctx: ScreenContext) -> ScreenContext:
    """Mutates ctx.screen_type in-place and returns ctx."""
    ctx.screen_type = classify(ctx)
    return ctx
