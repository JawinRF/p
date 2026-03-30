"""
android_automation.py - Phase 2 (Calendar fallback for AOSP AVD)
"""
import uiautomator2 as u2
import subprocess
import time
import logging

logger = logging.getLogger(__name__)
CALENDAR_PACKAGE = "com.android.calendar"

def connect(serial: str = "emulator-5554") -> u2.Device:
    d = u2.connect(serial)
    info = d.info
    logger.info(f"Connected: {info['productName']} ({info['displayWidth']}x{info['displayHeight']})")
    return d

def write_note(task: str, serial: str = "emulator-5554") -> dict:
    result = {"success": False, "task": task, "method": None, "error": None}
    try:
        d = connect(serial)
        d.screen_on()
        d.unlock()
        if _write_via_calendar(d, task):
            result["success"] = True
            result["method"] = "calendar"
            return result
        if _write_via_adb_file(task, serial):
            result["success"] = True
            result["method"] = "adb_file"
            return result
        result["error"] = "All methods failed"
    except Exception as exc:
        result["error"] = str(exc)
        logger.error(f"write_note failed: {exc}")
    return result

def _write_via_calendar(d, text):
    try:
        d.app_start(CALENDAR_PACKAGE)
        time.sleep(2)
        for label in ["Allow", "OK", "Got it", "Skip", "Later"]:
            if d(text=label).exists(timeout=1):
                d(text=label).click()
                time.sleep(0.5)
        fab = d(description="New event")
        if fab.exists(timeout=2):
            fab.click()
        else:
            for label in ["New event", "New Event", "+", "Create"]:
                if d(text=label).exists(timeout=1):
                    d(text=label).click()
                    break
            else:
                w, h = d.window_size()
                d.click(w - 80, h - 120)
        time.sleep(1.5)
        field = d(className="android.widget.EditText")
        if field.exists(timeout=3):
            field.click()
            time.sleep(0.5)
            field.set_text(text)
            logger.info(f"Typed: '{text}'")
        else:
            return False
        for label in ["Save", "SAVE", "Done", "DONE"]:
            if d(text=label).exists(timeout=2):
                d(text=label).click()
                time.sleep(1)
                return True
        d.press("back")
        time.sleep(1)
        return True
    except Exception as exc:
        logger.warning(f"Calendar failed: {exc}")
        return False

def _write_via_adb_file(text, serial):
    try:
        subprocess.run(
            f'adb -s {serial} shell "echo \\"{text}\\" > /sdcard/meeting_note.txt"',
            shell=True, check=True)
        logger.info("Written to /sdcard/meeting_note.txt")
        return True
    except Exception as exc:
        logger.warning(f"ADB fallback failed: {exc}")
        return False

def open_notes_app(d) -> str:
    d.app_start(CALENDAR_PACKAGE)
    time.sleep(2)
    return CALENDAR_PACKAGE

def create_new_note(d) -> None:
    if d(description="New event").exists(timeout=2):
        d(description="New event").click()
        time.sleep(1.5)
        return
    for label in ["New event", "New Event", "+", "Create"]:
        if d(text=label).exists(timeout=1):
            d(text=label).click()
            time.sleep(1.5)
            return
    w, h = d.window_size()
    d.click(w - 80, h - 120)
    time.sleep(1.5)

def type_note_content(d, text: str) -> None:
    field = d(className="android.widget.EditText")
    if field.exists(timeout=3):
        field.click()
        time.sleep(0.3)
        field.set_text(text)
    else:
        d.send_keys(text)
    logger.info(f"Typed: '{text}'")
    time.sleep(0.5)

def save_and_exit_note(d) -> None:
    for label in ["Save", "SAVE", "Done", "DONE"]:
        if d(text=label).exists(timeout=2):
            d(text=label).click()
            time.sleep(1)
            return
    d.press("back")
    time.sleep(1)

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    task = " ".join(sys.argv[1:]) or "Meeting at 9"
    print(f"Writing note: '{task}'")
    result = write_note(task)
    print(result)

# Override open_notes_app to use Messages instead
_MESSAGES_PACKAGE = "com.google.android.apps.messaging"

def open_notes_app(d) -> str:
    logger.info("Opening Messages app")
    d.app_start(_MESSAGES_PACKAGE)
    time.sleep(2)
    return _MESSAGES_PACKAGE

def create_new_note(d) -> None:
    # Tap the compose/start chat FAB
    for desc in ["Start chat", "Compose", "New conversation", "+"]:
        if d(description=desc).exists(timeout=2):
            d(description=desc).click()
            time.sleep(1.5)
            return
    # Fallback: bottom right FAB
    w, h = d.window_size()
    d.click(w - 100, h - 150)
    time.sleep(1.5)
