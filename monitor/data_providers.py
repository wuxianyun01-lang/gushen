from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn/",
}


def _http_text(url: str, referer: str = "https://finance.sina.com.cn/") -> str:
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer}, timeout=15)
    resp.raise_for_status()
    if isinstance(resp.content, bytes):
        return resp.content.decode("utf-8", errors="ignore")
    return resp.text


def fetch_sina_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    code_map = {code: f"sh{code}" if code.startswith(("5", "6", "9")) else f"sz{code}" for code in codes}
    url = "https://hq.sinajs.cn/list=" + ",".join(code_map.values())
    text = _http_text(url)
    result: dict[str, dict[str, Any]] = {}
    for raw in re.findall(r'var hq_str_(\w+)="([^"]*)"', text):
        symbol, payload = raw
        fields = payload.split(",")
        if len(fields) < 32:
            continue
        code = symbol[2:]
        try:
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]),
                "prev_close": float(fields[2]),
                "price": float(fields[3]),
                "high": float(fields[4]),
                "low": float(fields[5]),
                "bid": float(fields[6]),
                "ask": float(fields[7]),
                "volume": int(fields[8]),
                "amount": float(fields[9]),
                "datetime": f"{fields[30]} {fields[31]}",
            }
        except (ValueError, IndexError):
            continue
    return result


def fetch_fund_snapshots(codes: list[str]) -> dict[str, dict[str, Any]]:
    fcodes = ",".join(codes)
    url = (
        "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo"
        "?pageIndex=1&pageSize=50&plat=Android&appType=ttjj&product=EFund"
        "&Version=1&deviceid=monitor&Fcodes=" + fcodes
    )
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result: dict[str, dict[str, Any]] = {}
    for item in data.get("Datas") or []:
        code = str(item.get("FCODE"))
        result[code] = {
            "name": item.get("SHORTNAME", ""),
            "nav": float(item.get("NAV") or 0),
            "nav_date": item.get("PDATE", ""),
            "nav_change_pct": float(item.get("NAVCHGRT") or 0),
            "estimate": item.get("GSZ"),
            "estimate_change_pct": item.get("GSZZL"),
            "estimate_time": item.get("GZTIME") or data.get("Expansion", {}).get("GZTIME"),
        }
    return result


def fetch_fund_history(code: str, limit: int = 60) -> list[dict[str, float | str]]:
    try:
        rows = []
        page_count = max(1, (limit + 19) // 20)
        for page in range(1, page_count + 1):
            url = (
                "https://api.fund.eastmoney.com/f10/lsjz"
                f"?fundCode={code}&pageIndex={page}&pageSize=20"
            )
            resp = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://fundf10.eastmoney.com/",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            page_rows = (data.get("Data") or {}).get("LSJZList") or []
            for item in page_rows:
                nav = float(item.get("DWJZ") or 0)
                if nav <= 0:
                    continue
                rows.append({
                    "date": item.get("FSRQ", ""),
                    "close": nav,
                    "open": nav,
                    "high": nav,
                    "low": nav,
                    "volume": 0.0,
                    "amount": 0.0,
                    "change_pct": float(item.get("JZZZL") or 0),
                })
        rows.sort(key=lambda row: str(row["date"]))
        return rows[-limit:]
    except Exception:
        return []


def fetch_history(code: str, market: str = "sh") -> list[dict[str, float | str]]:
    rows = _fetch_history_eastmoney(code, market)
    if rows:
        return rows
    return _fetch_history_sina(code, market)


def _fetch_history_eastmoney(code: str, market: str) -> list[dict[str, float | str]]:
    secid = f"1.{code}" if market == "sh" else f"0.{code}"
    start = (dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")
    end = dt.date.today().strftime("%Y%m%d")
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0&beg={start}&end={end}"
    )
    try:
        text = _http_text(url, referer="https://quote.eastmoney.com/")
        data = _try_json(text)
        klines = ((data or {}).get("data") or {}).get("klines") or []
    except Exception:
        return []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        try:
            rows.append(_row_from_parts(parts))
        except ValueError:
            continue
    return rows


def _fetch_history_sina(code: str, market: str) -> list[dict[str, float | str]]:
    prefix = "sh" if market == "sh" else "sz"
    url = (
        "https://quotes.sina.cn/cn/api/jsonp_v2.php/var/CN_MarketDataService.getKLineData"
        f"?symbol={prefix}{code}&scale=240&ma=no&datalen=60"
    )
    try:
        text = _http_text(url, referer="https://finance.sina.com.cn/")
        match = re.search(r"var\((.*)\);", text, re.S)
        if not match:
            return []
        data = _try_json(match.group(1))
        if not isinstance(data, list):
            return []
        rows = []
        for item in data:
            rows.append({
                "date": item.get("day", ""),
                "open": float(item.get("open", 0)),
                "close": float(item.get("close", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "volume": float(item.get("volume", 0)),
                "amount": 0.0,
                "change_pct": 0.0,
            })
        return rows
    except Exception:
        return []


def _row_from_parts(parts: list[str]) -> dict[str, float | str]:
    return {
        "date": parts[0],
        "open": float(parts[1]),
        "close": float(parts[2]),
        "high": float(parts[3]),
        "low": float(parts[4]),
        "volume": float(parts[5]),
        "amount": float(parts[6]),
        "change_pct": float(parts[8]),
    }


def fetch_global_news(limit: int = 10) -> list[dict[str, str]]:
    url = f"https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_{limit}_1_.html"
    try:
        text = _http_text(url, referer="https://kuaixun.eastmoney.com/")
        match = re.search(r"var ajaxResult=(.*)$", text, re.S)
        if not match:
            return []
        data = _try_json(match.group(1))
        items = []
        for row in (data or {}).get("LivesList") or []:
            items.append({
                "title": row.get("title", ""),
                "digest": row.get("digest", ""),
                "time": row.get("showtime", ""),
                "url": row.get("url_w") or row.get("url_m", ""),
            })
        return items
    except Exception:
        return []


def fetch_guba_posts(code: str, limit: int = 10) -> list[dict[str, Any]]:
    url = f"https://guba.eastmoney.com/list,{code}.html"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://guba.eastmoney.com/",
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.text
        marker = "var article_list="
        start = text.find(marker)
        if start < 0:
            return []
        payload = text[start + len(marker):]
        data, _ = json.JSONDecoder().raw_decode(payload)
        items = []
        for post in (data.get("re") or [])[:limit]:
            title = post.get("post_title") or post.get("post_abstract") or ""
            content = post.get("post_content") or post.get("post_abstract") or ""
            if not title and not content:
                continue
            items.append({
                "title": title.strip(),
                "digest": content.strip().replace("\n", " ")[:240],
                "time": post.get("post_publish_time") or post.get("post_display_time") or "",
                "url": f"https://guba.eastmoney.com/news,{code},{post.get('post_id', '')}.html",
                "read_count": int(post.get("post_click_count") or 0),
                "comment_count": int(post.get("post_comment_count") or 0),
            })
        return items
    except Exception:
        return []


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None
