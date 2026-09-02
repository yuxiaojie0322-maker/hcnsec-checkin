#!/usr/bin/env python3
"""
hcnsec.cn 每日登录签到脚本（多账号）
====================================
站点: https://api.hcnsec.cn（New API 面板 - 新疆幻城网安科技公益大模型API网关）
流程: 登录(拿session cookie + uid) -> GET /api/user/checkin 查今日状态 -> POST /api/user/checkin 签到

多账号配置（环境变量 HCN_ACCOUNTS）:
  格式1: "user1:pass1|user2:pass2|user3:pass3"   （竖线分隔多账号，冒号分隔用户名密码）
  格式2: JSON 数组: [{"username":"u1","password":"p1"},{"username":"u2","password":"p2"}]
  密码中含冒号时建议用格式2（JSON）

可选环境变量:
  TG_BOT_TOKEN / TG_CHAT_ID  配置后推送结果到 Telegram
  HCN_BASE_URL               默认 https://api.hcnsec.cn

使用示例:
  HCN_ACCOUNTS="yxj0322:YxJ223512@|user2:pass2" python3 hcnsec_checkin.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE_URL = os.environ.get("HCN_BASE_URL", "https://api.hcnsec.cn")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")


def parse_accounts(raw: str):
    """解析多账号配置，支持 'u:p|u:p' 或 JSON 数组"""
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.lstrip().startswith("["):
        try:
            data = json.loads(raw)
            accounts = []
            for item in data:
                accounts.append({
                    "username": str(item.get("username", "")).strip(),
                    "password": str(item.get("password", "")).strip(),
                })
            return [a for a in accounts if a["username"]]
        except Exception as e:
            print(f"[WARN] JSON 账号解析失败({e})，回退到冒号分隔格式")
    accounts = []
    for seg in raw.split("|"):
        seg = seg.strip()
        if not seg:
            continue
        if ":" in seg:
            u, _, p = seg.partition(":")
            accounts.append({"username": u.strip(), "password": p.strip()})
    return accounts


def api_request(method: str, path: str, data=None, cookie=None, uid=None, timeout=30):
    """发起 API 请求，返回 (json_dict, http_code)，失败返回 (None, code)"""
    url = BASE_URL.rstrip("/") + path
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
    if uid:
        headers["New-Api-User"] = str(uid)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(text), resp.status
            except Exception:
                return {"raw": text}, resp.status
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode("utf-8", errors="replace")
            return json.loads(text), e.code
        except Exception:
            return {"raw": str(e)}, e.code
    except Exception as e:
        print(f"[ERR] 请求异常 {method} {path}: {e}")
        return None, -1


def login(username: str, password: str):
    """登录，返回 (cookie, uid, display_name) 或 (None, None, None)"""
    data, code = api_request("POST", "/api/user/login", {"username": username, "password": password})
    if not data or not data.get("success"):
        msg = (data or {}).get("message", f"HTTP {code}")
        print(f"[{username}] 登录失败: {msg}")
        return None, None, None

    # 从响应头提取 session cookie
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/api/user/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            session_cookie = ""
            for k, v in resp.headers.items():
                if k.lower() == "set-cookie" and "session=" in v:
                    for part in v.split(","):
                        if "session=" in part:
                            session_cookie = "session=" + part.split("session=")[1].split(";")[0]
                            break
    except Exception as e:
        print(f"[{username}] 获取 session cookie 失败: {e}")
        return None, None, None

    info = data.get("data", {})
    uid = info.get("id")
    display = info.get("display_name") or username
    print(f"[{username}] 登录成功 (uid={uid}, 显示名={display})")
    return session_cookie, uid, display


def get_checkin_status(cookie: str, uid: str):
    """查询今日签到状态，返回 (checked_in_today, stats)"""
    data, code = api_request("GET", "/api/user/checkin", cookie=cookie, uid=uid)
    if not data or not data.get("success"):
        print(f"[uid={uid}] 查询签到状态失败: {(data or {}).get('message', f'HTTP {code}')}")
        return None, None
    info = data.get("data", {})
    stats = info.get("stats", {})
    return stats.get("checked_in_today", False), stats


def do_checkin(cookie: str, uid: str):
    """执行签到，返回 (success, message, detail)"""
    data, code = api_request("POST", "/api/user/checkin", data={}, cookie=cookie, uid=uid)
    if not data:
        return False, f"网络错误 HTTP {code}", None
    if data.get("success"):
        detail = data.get("data", {})
        awarded = detail.get("quota_awarded")
        awarded_str = f"{awarded/1000000:.2f}M" if awarded and awarded > 1000000 else (f"{awarded:,}" if awarded else "?")
        return True, f"签到成功 +{awarded_str} 额度", detail
    return False, data.get("message", f"HTTP {code}"), data.get("data")


def send_tg(text: str):
    """推送结果到 Telegram（可选）"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        body = json.dumps({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[TG] 推送失败: {e}")
        return False


def process_account(acc):
    username = acc["username"]
    password = acc["password"]
    cookie, uid, display = login(username, password)
    if not cookie or not uid:
        return {"username": username, "ok": False, "msg": "登录失败"}

    # 先查状态
    checked_in, stats = get_checkin_status(cookie, uid)
    if checked_in:
        total = stats.get("total_checkins", "?")
        total_q = stats.get("total_quota", 0)
        total_q_str = f"{total_q/1000000:.1f}M" if total_q and total_q > 1000000 else f"{total_q:,}"
        msg = "今日已签到（跳过）"
        print(f"[{username}] {msg} | 累计{total}次, 总{total_q_str}")
        return {"username": username, "ok": True, "msg": f"今日已签到 | 累计{total}次, 总{total_q_str}", "skipped": True}

    # 执行签到
    ok, msg, detail = do_checkin(cookie, uid)
    print(f"[{username}] {msg}")
    return {"username": username, "ok": ok, "msg": msg}


def main():
    raw = os.environ.get("HCN_ACCOUNTS", "")
    accounts = parse_accounts(raw)
    if not accounts:
        print("错误: 未配置账号。请设置环境变量 HCN_ACCOUNTS（格式: user1:pass1|user2:pass2）")
        sys.exit(1)

    print(f"开始签到，共 {len(accounts)} 个账号\n" + "=" * 40)
    results = []
    for i, acc in enumerate(accounts):
        print(f"\n--- 账号 {i+1}/{len(accounts)}: {acc['username']} ---")
        results.append(process_account(acc))
        time.sleep(1)

    # 汇总
    print("\n" + "=" * 40)
    print("签到结果汇总:")
    success_n = sum(1 for r in results if r["ok"])
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        print(f"  {mark} {r['username']}: {r['msg']}")

    # TG 推送
    lines = [f"<b>hcnsec 每日签到</b> ({len(results)} 账号, 成功 {success_n})"]
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        lines.append(f"{mark} {r['username']}: {r['msg']}")
    send_tg("\n".join(lines))

    if success_n == len(results) and len(results) > 0:
        sys.exit(0)
    sys.exit(1 if success_n < len(results) else 0)


if __name__ == "__main__":
    main()
