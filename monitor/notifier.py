from __future__ import annotations

import smtplib
import subprocess
import tempfile
from email.mime.text import MIMEText
from pathlib import Path


def send_alert(title: str, message: str, config: dict, dry_run: bool = False) -> list[dict[str, str]]:
    results = []
    if dry_run:
        return [{"channel": "dry-run", "status": "suppressed"}]
    if config.get("notification", {}).get("windows", True):
        try:
            _windows_alert(title, message)
            results.append({"channel": "windows", "status": "sent"})
        except Exception as exc:
            results.append({"channel": "windows", "status": f"failed: {exc}"})
    qq = config.get("notification", {}).get("qq_email", {})
    if qq.get("enabled") and qq.get("sender") and qq.get("receiver") and qq.get("auth_code"):
        try:
            _qq_alert(qq, title, message)
            results.append({"channel": "qq_email", "status": "sent"})
        except Exception as exc:
            results.append({"channel": "qq_email", "status": f"failed: {exc}"})
    return results


def _qq_alert(qq: dict, title: str, message: str) -> None:
    msg = MIMEText(message, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = qq["sender"]
    msg["To"] = qq["receiver"]
    port = int(qq.get("smtp_port", 587))
    if port == 465:
        with smtplib.SMTP_SSL(qq["smtp_server"], port, timeout=15) as server:
            server.login(qq["sender"], qq["auth_code"])
            server.sendmail(qq["sender"], [qq["receiver"]], msg.as_string())
        return
    with smtplib.SMTP(qq["smtp_server"], port, timeout=15) as server:
        server.starttls()
        server.login(qq["sender"], qq["auth_code"])
        server.sendmail(qq["sender"], [qq["receiver"]], msg.as_string())


def _windows_alert(title: str, message: str) -> None:
    try:
        subprocess.run(
            ["msg.exe", "*", f"{title}\n{message}"],
            check=False,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    except Exception:
        pass
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False, encoding="utf-8") as handle:
        path = Path(handle.name)
        escaped_title = title.replace('"', "'")
        escaped_message = message.replace('"', "'").replace("\n", " ")
        handle.write(f'MsgBox "{escaped_title}\\n{escaped_message}", vbInformation, "Trading Monitor"\n')
    subprocess.Popen(["wscript.exe", str(path)])
