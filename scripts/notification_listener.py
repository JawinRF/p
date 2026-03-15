"""
notification_listener.py - Phase 2
Intercepts Android notifications via logcat and routes through PRISM.
"""
import subprocess, threading, requests, json, time, logging, re
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

PRISM_URL = "http://localhost:8765/v1/inspect"
AUDIT_LOG = Path("/home/jrf/Desktop/samsung_prism_project/data/audit_log.jsonl")
ADB_SERIAL = "emulator-5554"

NOTIF_LOGCAT_TAGS = ["NotificationService", "NotificationManager", "StatusBarManagerService"]

@dataclass
class CapturedNotification:
    timestamp: str
    package: str
    title: str
    text: str
    raw_log: str

@dataclass
class PRISMDecision:
    notification: CapturedNotification
    verdict: str
    confidence: float
    reason: str
    prism_latency_ms: float

_NOTIF_RE = re.compile(
    r"pkg=(?P<pkg>\S+).*?(?:title|tickerText)=(?P<title>[^,\n]+).*?text=(?P<text>[^\n]+)",
    re.IGNORECASE,
)
_BROAD_RE = re.compile(r"notification.*?['\"](?P<text>[^'\"]{10,})['\"]", re.IGNORECASE)

def parse_notification_line(line: str):
    m = _NOTIF_RE.search(line)
    if m:
        return CapturedNotification(
            timestamp=datetime.now(timezone.utc).isoformat(),
            package=m.group("pkg"),
            title=m.group("title").strip(),
            text=m.group("text").strip(),
            raw_log=line.strip(),
        )
    if any(tag in line for tag in NOTIF_LOGCAT_TAGS):
        m2 = _BROAD_RE.search(line)
        if m2:
            return CapturedNotification(
                timestamp=datetime.now(timezone.utc).isoformat(),
                package="unknown",
                title="",
                text=m2.group("text").strip(),
                raw_log=line.strip(),
            )
    return None

def inspect_with_prism(notif: CapturedNotification) -> PRISMDecision:
    import uuid
    payload = {
        "entry_id":      str(uuid.uuid4()),
        "text":          f"{notif.title} {notif.text}".strip(),
        "ingestion_path":"notifications",
        "source_type":   "notification",
        "source_name":   notif.package,
        "session_id":    "phase2-demo",
        "run_id":        "phase2-run",
        "metadata":      {"timestamp": notif.timestamp},
    }
    start = time.perf_counter()
    try:
        resp = requests.post(PRISM_URL, json=payload, timeout=5)
        latency_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()
        return PRISMDecision(
            notification=notif,
            verdict=data.get("verdict", "ALLOW"),
            confidence=data.get("confidence", 0.0),
            reason=data.get("reason", ""),
            prism_latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error(f"PRISM error: {exc}")
        return PRISMDecision(
            notification=notif,
            verdict="BLOCK",
            confidence=1.0,
            reason=f"PRISM error: {exc}",
            prism_latency_ms=latency_ms,
        )

def write_audit(decision: PRISMDecision):
    record = {
        "timestamp": decision.notification.timestamp,
        "event": "notification_intercepted",
        "verdict": decision.verdict,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "notification": asdict(decision.notification),
        "prism_latency_ms": round(decision.prism_latency_ms, 1),
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info(f"[AUDIT] {decision.verdict} — {decision.notification.text[:60]}")

class NotificationListener(threading.Thread):
    def __init__(self, serial=ADB_SERIAL, on_block=None, on_allow=None):
        super().__init__(daemon=True)
        self.serial = serial
        self.on_block = on_block or (lambda d: None)
        self.on_allow = on_allow or (lambda d: None)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info("Notification listener started")
        # Clear old logcat then stream new lines only
        subprocess.run(["adb", "-s", self.serial, "logcat", "-c"], capture_output=True)
        cmd = ["adb", "-s", self.serial, "logcat", "-v", "tag"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, bufsize=1)
            for line in proc.stdout:
                if self._stop_event.is_set():
                    break
                # Also catch adb shell cmd notification post output
                if any(x in line for x in ["NotificationService", "NotificationManager",
                                            "shell_cmd", "prism.demo"]):
                    notif = parse_notification_line(line)
                    if notif is None:
                        # Try direct text extraction for adb-posted notifications
                        if "prism.demo" in line or "shell_cmd" in line:
                            notif = CapturedNotification(
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                package="prism.demo",
                                title="ADB Notification",
                                text=line.strip()[:200],
                                raw_log=line.strip(),
                            )
                    if notif:
                        decision = inspect_with_prism(notif)
                        write_audit(decision)
                        if decision.verdict == "BLOCK":
                            logger.warning(f"BLOCKED: '{notif.text[:80]}'")
                            self.on_block(decision)
                        else:
                            logger.info(f"ALLOWED: '{notif.text[:60]}'")
                            self.on_allow(decision)
            proc.terminate()
        except Exception as exc:
            logger.error(f"Listener error: {exc}")
        logger.info("Notification listener stopped")
