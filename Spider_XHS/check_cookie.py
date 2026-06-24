#!/usr/bin/env python3
"""验证 .env 里的小红书 cookie 是「过期」还是「软封/限流」。"""
import sys
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from loguru import logger
logger.remove()

from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.common_util import load_env

ck = (load_env() or "").replace("\r", "").replace("\n", "").strip()
print("cookie 长度:", len(ck))

ok, msg, res = XHS_Apis().get_user_self_info(ck)
print("接口 success =", ok, "| msg =", repr(msg))

data = (res or {}).get("data", {}) if isinstance(res, dict) else {}
nickname = data.get("nickname") or (data.get("basic_info", {}) or {}).get("nickname")
guest = data.get("guest")
print("当前登录用户 =", nickname, "| guest =", guest)
print("-" * 50)

if ok and nickname and not guest:
    print("✅ cookie 有效（还登录着，是你本人）")
    print("   → 不是过期，是【软封 / 限流】。搜索给空数据是被限制，等等或换小号。")
else:
    print("❌ cookie 已失效 / 过期（取不到本人账号信息）")
    print("   → 重新登录小红书，复制新 cookie 覆盖 Spider_XHS/.env 即可。")
