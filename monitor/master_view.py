from __future__ import annotations

from typing import Any

MASTER_LABELS = {
    "buffett": "巴菲特：先看生意质量与安全边际",
    "graham": "格雷厄姆：不接加速下跌的飞刀",
    "lynch": "林奇：只买能看懂、逻辑未破坏的成长",
    "friess": "佛莱斯：等强势确认，不猜底",
    "oelschlager": "欧斯拉格：合理价格成长，不追高",
    "sivy": "喜伟：重视收益稳定性",
    "rossman": "罗斯曼：买对后长期拿住",
}


def master_view(holding: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    names = [MASTER_LABELS.get(name, name) for name in holding.get("masters", [])]
    action = signal.get("action", "继续持有")
    return {
        "masters": names,
        "summary": f"当前适配大师：{'、'.join(names)}。操作提示：{action}。",
    }
