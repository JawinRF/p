#!/usr/bin/env bash
################################################################################
# run_android_demo.sh — End-to-end PRISM Shield Android PoC demo
#
# Prerequistes:
#   - Android emulator running (API 34, x86_64)
#   - Both APKs built:
#       cd android/prism-shield-service && ./gradlew assembleDebug
#       cd android/poison-app && ./gradlew assembleDebug
#   - Python venv active with: uiautomator2, requests
#   - GROQ_API_KEY set (for agent.py)
#
# Usage:
#   ./scripts/demo/run_android_demo.sh              # full demo
#   ./scripts/demo/run_android_demo.sh --skip-install  # skip APK install
################################################################################
set -euo pipefail

SERIAL="${ANDROID_SERIAL:-emulator-5554}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SHIELD_APK="$PROJECT_ROOT/android/prism-shield-service/app/build/outputs/apk/debug/app-debug.apk"
POISON_APK="$PROJECT_ROOT/android/poison-app/build/outputs/apk/debug/poison-android-app-debug.apk"

BOLD="\033[1m"
RED="\033[91m"
GREEN="\033[92m"
YELLOW="\033[93m"
CYAN="\033[96m"
RESET="\033[0m"

header() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; echo -e "${BOLD}  $1${RESET}"; echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }
ok()     { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()   { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail()   { echo -e "  ${RED}✗${RESET} $1"; }

# ── Pre-flight checks ────────────────────────────────────────────────────────

header "PRISM Shield — Android PoC Demo"

echo -e "\n${BOLD}[1/6] Pre-flight checks${RESET}"

# Check ADB
if ! command -v adb &>/dev/null; then
    fail "adb not found. Install Android SDK platform-tools."
    exit 1
fi
ok "adb found"

# Check emulator
if ! adb -s "$SERIAL" get-state &>/dev/null; then
    fail "Emulator $SERIAL not running. Start it first:"
    echo "    emulator -avd <your_avd_name>"
    exit 1
fi
ok "Emulator $SERIAL is running"

# ── Install APKs ─────────────────────────────────────────────────────────────

if [[ "${1:-}" != "--skip-install" ]]; then
    echo -e "\n${BOLD}[2/6] Installing APKs${RESET}"

    if [[ ! -f "$SHIELD_APK" ]]; then
        fail "Shield APK not found. Build first:"
        echo "    cd android/prism-shield-service && ./gradlew assembleDebug"
        exit 1
    fi
    adb -s "$SERIAL" install -r "$SHIELD_APK" 2>/dev/null
    ok "prism-shield-service installed"

    if [[ ! -f "$POISON_APK" ]]; then
        warn "Poison APK not found. Build it:"
        echo "    cd android/poison-app && ./gradlew assembleDebug"
        echo "    Continuing without poison-app..."
    else
        adb -s "$SERIAL" install -r "$POISON_APK" 2>/dev/null
        ok "poison-app installed"
    fi
else
    echo -e "\n${BOLD}[2/6] Skipping APK install (--skip-install)${RESET}"
fi

# ── Grant permissions ─────────────────────────────────────────────────────────

echo -e "\n${BOLD}[3/6] Granting permissions${RESET}"

# Grant notification permission to poison-app (API 33+)
adb -s "$SERIAL" shell pm grant com.prism.poisonapp android.permission.POST_NOTIFICATIONS 2>/dev/null \
    && ok "POST_NOTIFICATIONS granted to poison-app" \
    || warn "Could not grant POST_NOTIFICATIONS (may need manual grant)"

# Port forward so host Python can reach the on-device sidecar
adb -s "$SERIAL" forward tcp:8766 tcp:8766 2>/dev/null
ok "Port forward: host:8766 → device:8766 (on-device dashboard)"

echo ""
echo -e "  ${YELLOW}Manual step required:${RESET}"
echo "  1. Open Settings > Accessibility on the emulator"
echo "     Enable 'PRISM Shield' accessibility service"
echo "  2. Open Settings > Apps > Special access > Notification access"
echo "     Enable 'PRISM Shield'"
echo ""
read -rp "  Press Enter when permissions are granted..."

# ── Launch PRISM Shield ──────────────────────────────────────────────────────

echo -e "\n${BOLD}[4/6] Launching PRISM Shield${RESET}"

adb -s "$SERIAL" shell am start -n com.prismshield/.MainActivity 2>/dev/null
ok "PRISM Shield launched"
sleep 2

# Verify sidecar is running
if curl -sf http://localhost:8766/v1/status &>/dev/null; then
    ok "On-device sidecar responding on :8766"
else
    warn "Sidecar not responding yet — it starts when the foreground service runs"
    echo "  Open the PRISM Shield app on the emulator and wait for it to initialize."
    read -rp "  Press Enter when ready..."
fi

# ── Demo: Test scenarios against sidecar ─────────────────────────────────────

echo -e "\n${BOLD}[5/6] Running PRISM Shield test scenarios${RESET}"
echo ""

python3 "$PROJECT_ROOT/scripts/demo/run_demo.py"

# ── Demo: Poison notification attack ─────────────────────────────────────────

echo -e "\n${BOLD}[6/6] Poison notification attack demo${RESET}"

echo "  Sending poisoned notification via ADB..."
bash "$PROJECT_ROOT/scripts/send_poison_notification.sh"

echo ""
echo "  Check the PRISM Shield dashboard on the emulator."
echo "  The poisoned notification should appear as BLOCKED in the audit log."

# ── Summary ──────────────────────────────────────────────────────────────────

header "Demo Complete"
echo ""
echo "  What was demonstrated:"
echo "    1. PRISM Shield installed and running as an accessibility service"
echo "    2. Multi-layer defense pipeline (Heuristics → TinyBERT → DeBERTa)"
echo "    3. Real-time interception of poisoned notifications"
echo "    4. Audit logging of all verdicts"
echo ""
echo "  To run the full agent demo (requires GROQ_API_KEY):"
echo "    ENABLE_PRISM=1 python scripts/agent.py --task 'Add a new todo: Buy groceries'"
echo ""
echo "  To see what happens WITHOUT PRISM:"
echo "    ENABLE_PRISM=0 python scripts/agent.py --task 'Add a new todo: Buy groceries'"
echo ""
