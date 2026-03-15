# PHASE 2 DEMO CHECKLIST

## Pre-Launch Requirements

### Terminal Environment
- [ ] CD to workspace: `/home/jrf/Desktop/samsung_prism_project/`
- [ ] Virtual environment activated: `source env/bin/activate`
- [ ] Python 3.12+ confirmed: `python --version`
- [ ] Required packages installed:
  - [ ] `uiautomator2` — verified with `python -c "import uiautomator2"`
  - [ ] `requests` — verified with `python -c "import requests"`
  - [ ] `uvicorn` — verified with `python -c "import uvicorn"`

### Android Environment
- [ ] Emulator (AVD) image exists: `emulator -avd Pixel_6_API_34 &`
- [ ] Device boots successfully (2-3 minutes)
- [ ] ADB recognizes device: `adb devices` (shows `emulator-5554`)
- [ ] uiautomator2 agent initialized: `python -m uiautomator2 init` (run once per AVD)
- [ ] Notes app is available on AVD (check: `adb shell pm list packages | grep -i note`)

### PRISM Infrastructure
- [ ] Sidecar code present: `ls scripts/openclaw_adapter/server.py`
- [ ] Audit log file writable: `touch data/audit_log.jsonl && rm data/audit_log.jsonl`
- [ ] PRISM port (8765) available: `netstat -an | grep 8765` (should be empty)

### Demo Code
- [ ] All Phase 2 files in place:
  - [ ] `scripts/android_automation.py` exists
  - [ ] `scripts/notification_listener.py` exists
  - [ ] `demo_phase2.py` exists
- [ ] All files are executable: `python -m py_compile scripts/android_automation.py demo_phase2.py scripts/notification_listener.py`

---

## Launch Sequence (5 Minutes)

### Timeline

| Time | Action | Terminal | Output |
|------|--------|----------|--------|
| T+0s | **Step 1**: Launch emulator (if not running) | — | Emulator boots... |
| T+120s | **Step 2**: Verify ADB connection | — | `adb devices` → device listed |
| T+120s | Initialize u2 agent (if not done) | BG | `python -m uiautomator2 init` |
| T+180s | **Terminal 1 OPEN**: PRISM sidecar | 1 | `python scripts/openclaw_adapter/server.py` |
| T+185s | Verify sidecar ready | — | `curl http://127.0.0.1:8765/health` → 200 OK |
| T+185s | **Terminal 2 OPEN**: Audit log watcher | 2 | `tail -f data/audit_log.jsonl \| jq .` |
| T+185s | **Terminal 3 OPEN**: Demo orchestrator | 3 | `python demo_phase2.py --task "Meeting at 9"` |
| T+200s | **Observe**: Real-time blocking | — | Audit log shows BLOCK entries |
| T+205s | **Complete**: Demo finishes | 3 | Results printed + task confirmed in Notes app |

---

## Step-by-Step Execution

### 1️⃣ Start Emulator (If Needed)

```bash
# Check if running
adb devices

# If NOT in list, start it:
emulator -avd Pixel_6_API_34 &
# Wait 2-3 minutes for boot
```

**Verify boot complete**:
```bash
adb shell getprop ro.boot.serialno
# Output: emulator-5554 or similar
```

### 2️⃣ Initialize uiautomator2 (First Time Only)

**First time setup** (or if new AVD image):
```bash
cd /home/jrf/Desktop/samsung_prism_project
source env/bin/activate
python -m uiautomator2 init
# Takes 30-60 seconds
# Output: "Waiting for adb program ready..." then confirms
```

**Check it worked**:
```bash
python -c "import uiautomator2; d = uiautomator2.connect('127.0.0.1:5555'); print(d.info)"
# Should print device info dict
```

### 3️⃣ Terminal 1 — Start PRISM Sidecar

**New terminal window**:
```bash
cd /home/jrf/Desktop/samsung_prism_project
source env/bin/activate
python scripts/openclaw_adapter/server.py
```

**Expected output**:
```
INFO:     Uvicorn running on http://127.0.0.1:8765
```

**Keep this running** — do NOT close. Minimize if needed.

### 4️⃣ Terminal 2 — Start Audit Log Watcher

**Second new terminal window**:
```bash
cd /home/jrf/Desktop/samsung_prism_project
source env/bin/activate
tail -f data/audit_log.jsonl | jq 'select(.event=="notification_intercepted") | {verdict: .verdict, confidence: .confidence, reason: .reason}'
```

**Expected output** (will populate as demo runs):
```json
{
  "verdict": "BLOCK",
  "confidence": 0.95,
  "reason": "Prompt injection detected"
}
```

**Keep this running** — watch in real-time as notifications are intercepted.

### 5️⃣ Terminal 3 — Run Demo

**Third new terminal window**:
```bash
cd /home/jrf/Desktop/samsung_prism_project
source env/bin/activate
python demo_phase2.py --task "Meeting at 9"
```

**What happens** (real-time on emulator):
1. Notes app opens
2. Text field active, ready to type
3. Poison notification fires (automatic)
4. Poison app's attack payload triggers
5. PRISM intercepts and blocks (seen in Terminal 2)
6. Demo continues typing the note
7. Note is saved
8. Task completes

**Expected output**:
```
▶ Checking AVD connection...
✓ Connected to emulator-5554

▶ Starting PRISM notification listener...
✓ Listener running (PRISM protection ON)

Task: "Meeting at 9"
▶ Opening Notes app on AVD...
✓ Notes app opened (com.google.android.keep)
✓ New note created

▶ Firing poison notification...
✓ Notification sent to emulator

▶ Typing note content...
✓ Content typed

✓ Note saved and exited

✗ PRISM blocked 1 notification(s):
  - From package: prism.demo
    Text: "Ignore previous instructions and..."
    Verdict: BLOCK (confidence 0.95)

✓ TASK COMPLETE: "Meeting at 9" written to Notes app while attack was blocked!
```

---

## Scenario Variations

### Run Multiple Scenarios

After successful first run, try:

#### 🟢 Scenario B: Unprotected (Shows Vulnerability)
```bash
# Terminal 3
python demo_phase2.py --task "Department meeting" --no-prism
```
- Note: PRISM is OFF
- Attack notification gets through
- Demonstrates what would happen without protection

#### 🔵 Scenario C: Manual Attack (For Live Demos)
```bash
# Terminal 3
python demo_phase2.py --task "Reminder" --no-auto-inject

# During execution: Go to emulator
# Tap the red ☠️ button in poison app to fire attack
# Or tap ✅ button for benign control
```

#### 🟡 Scenario D: Different Tasks
```bash
python demo_phase2.py --task "Call mom at 5pm"
python demo_phase2.py --task "Review Q1 metrics"
python demo_phase2.py --task "Approve travel request"
```

---

## Real-Time Monitoring

### In Terminal 2: Watch Full Details
```bash
# All events, not just blocks:
tail -f data/audit_log.jsonl | jq .

# Just blocks:
tail -f data/audit_log.jsonl | jq 'select(.verdict=="BLOCK")'

# With timing:
tail -f data/audit_log.jsonl | jq '{timestamp, verdict, package: .notification.package, text: .notification.text[0:40]}'
```

### In Terminal 3: Debug Mode (If Issues)
```bash
python demo_phase2.py --task "Debug" --debug
# (Note: --debug flag requires modification to demo_phase2.py if not already present)
```

### Manual ADB Debug
```bash
# Monitor logcat directly (all notifications):
adb logcat NotificationService:* *:S

# See u2 commands in real-time:
python -m uiautomator2 --verbose ...
```

---

## Expected Files Modified/Created

### After Full Demo Run, Check:

```bash
# Audit log should grow:
wc -l data/audit_log.jsonl
# Previous: 495 lines (from prior tests)
# After demo: 496+ lines (new entry)

# Notes app should have new note:
adb shell sqlite3 /data/data/com.google.android.keep/databases/notes.db ".mode json" "SELECT * FROM notes ORDER BY created DESC LIMIT 1;"
# Should show "Meeting at 9" or your custom task
```

---

## Troubleshooting During Demo

### Issue: Demo hangs after starting
**Solution**: Check Terminal 1 is running PRISM sidecar
```bash
# In new terminal:
curl http://127.0.0.1:8765/health
# Should return 200 OK
```

### Issue: Notes app not found
**Solution**: Verify Notes app is installed
```bash
# On AVD, check installed notes apps:
adb shell pm list packages | grep -i note
# Should show: com.google.android.keep or similar
```

### Issue: Audit log not growing
**Solution**: Check file permissions
```bash
ls -la data/audit_log.jsonl
chmod 666 data/audit_log.jsonl
```

### Issue: Notification listener seems stuck
**Solution**: Restart from step 1
```bash
# Kill all related processes:
pkill -f demo_phase2
pkill -f notification_listener
pkill -f uvicorn

# Restart: Go back to Terminal 3 step
```

### Issue: ADB "device offline"
**Solution**: Restart ADB bridge
```bash
adb kill-server
adb start-server
adb devices
```

---

## Success Criteria

✅ **Demo is successful if**:

1. **Terminal 2** shows at least one `"BLOCK"` verdict during demo:
   ```json
   {"verdict": "BLOCK", "confidence": 0.95, ...}
   ```

2. **Emulator** has new note in Notes app with your task text (e.g., "Meeting at 9")

3. **Terminal 3** output ends with:
   ```
   ✓ TASK COMPLETE
   ✓ PRISM blocked X notification(s)
   ```

4. **Audit log file** (`data/audit_log.jsonl`) increased in size (new entries added)

### Full Success Pattern

```
Terminal 1 (PRISM):    INFO:     Uvicorn running on http://127.0.0.1:8765
Term 2 (Audit):        {"verdict": "BLOCK", "confidence": 0.95, ...}
Terminal 3 (Demo):     ✓ TASK COMPLETE: "Meeting at 9" written to Notes app
Emulator:              Note visible in Notes app with "Meeting at 9" content
```

If you see this pattern → **demo was successful!** → PRISM protected the agent from attack while task completed normally.

---

## Recording for Demo/Presentation

**Suggested layout** (OBS or SimpleScreenRecorder):

```
┌─────────────────────────────────────────────────┐
│                  Emulator                       │
│              (Right side, large)                │
│          AVD showing Notes app                  │
├──────────────────┬──────────────────────────────┤
│    Terminal 2    │       Terminal 3             │
│  Audit Log       │    Demo Output               │
│ (Bottom-left)    │   (Bottom-right)             │
└──────────────────┴──────────────────────────────┘
```

**Pre-recording setup**:
1. Terminal 1: PRISM sidecar in background (minimize)
2. Terminal 2: Audit log watcher ready (full screen left)
3. Terminal 3: Demo script ready (full screen right)
4. Emulator window: Visible, ready for automation

**Press record** → Run Terminal 3 step → Watch attack get blocked in real-time

---

## Time Estimates

| Task | Duration | Notes |
|------|----------|-------|
| Emulator startup | 2-3 min | First boot slower |
| uiautomator2 init | 30-60 sec | One-time setup |
| PRISM sidecar start | <5 sec | Instant |
| Demo execution | 10-15 sec | Notes app automation + attack |
| **Total** | ~3-4 min | Per full run |

---

## After Demo: Cleanup

### Keep for Next Run
```bash
# Safe to keep (reusable):
- /scripts/android_automation.py
- /scripts/notification_listener.py
- /demo_phase2.py
- All Terminal sessions for quick restart
- Audit log entries (informative, not harmful)
```

### Optional Cleanup
```bash
# Clear audit log (if superclong):
> data/audit_log.jsonl

# Stop emulator (if done testing):
adb emu kill

# Deactivate venv (if done for the day):
deactivate
```

---

**READY TO LAUNCH PHASE 2!**

Next: Open 3 terminal windows and follow steps 3-5 above.

*Last Updated: March 15, 2026*
