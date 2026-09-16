from __future__ import annotations

import getpass
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config.json"


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    qq = config.setdefault("notification", {}).setdefault("qq_email", {})
    print("QQ 邮箱 SMTP 绑定")
    print(f"当前邮箱：{qq.get('sender') or '未设置'}")
    code = getpass.getpass("请输入 QQ 邮箱 SMTP 授权码（输入不会显示）：").strip()
    if not code:
        print("未输入授权码，配置未修改。")
        return
    qq["auth_code"] = code
    qq["enabled"] = True
    qq["smtp_server"] = qq.get("smtp_server") or "smtp.qq.com"
    qq["smtp_port"] = int(qq.get("smtp_port") or 465)
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("QQ 邮件提醒已启用。重启监控后生效。")


if __name__ == "__main__":
    main()
