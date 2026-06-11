import json
import os
import urllib.parse
import urllib.request
from typing import Any

from utils.config_handler import agent_conf
from utils.logger_handler import logger


AMAP_API_KEY_ENV = "AMAP_API_KEY"
AMAP_MCP_URL_ENV = "AMAP_MCP_URL"
AMAP_REST_TIMEOUT_SECONDS = 4


def _json_dumps(data: dict[str, Any]) -> str:
    """序列化 fallback 结果，保留中文并兼容少量非 JSON 原生对象。"""
    return json.dumps(data, ensure_ascii=False, default=str)


def _get_amap_api_key() -> str:
    """按优先级获取高德 API Key：环境变量 -> 项目配置 -> MCP URL 的 key 参数。"""
    key = os.getenv(AMAP_API_KEY_ENV)
    if key:
        return key.strip()

    configured_key = (agent_conf or {}).get("amap_api_key")
    if isinstance(configured_key, str) and configured_key.strip():
        return configured_key.strip()

    mcp_url = os.getenv(AMAP_MCP_URL_ENV) or (agent_conf or {}).get("amap_mcp_url", "")
    if not isinstance(mcp_url, str) or not mcp_url.strip():
        return ""

    # urlparse(...).query 取出 ? 后面的查询字符串；parse_qs 会把 key=xxx 解析成 {"key": ["xxx"]}。
    query = urllib.parse.urlparse(mcp_url).query
    values = urllib.parse.parse_qs(query)
    return (values.get("key") or [""])[0].strip()


def _first_present(args: dict[str, Any], names: tuple[str, ...]) -> str:
    """从多个候选参数名中取第一个非空值。"""
    for name in names:
        value = args.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _call_amap_rest(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """调用高德 REST API，失败时抛错交给外层 fallback 处理。"""
    key = _get_amap_api_key()
    if not key:
        raise RuntimeError("未配置高德 REST API Key")

    clean_params = {k: v for k, v in params.items() if v not in (None, "")}
    clean_params["key"] = key
    url = "https://restapi.amap.com" + path + "?" + urllib.parse.urlencode(clean_params)

    with urllib.request.urlopen(url, timeout=AMAP_REST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if str(payload.get("status")) != "1":
        raise RuntimeError(payload.get("info") or "高德 REST API 返回失败")

    return payload


def _backup_api_payload(tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """
    MCP 工具失败后的备用 HTTP API（三级兜底策略的第二级）。

    根据 tool_name 匹配对应的高德 REST API：
      - weather  → /v3/weather/weatherInfo     （天气查询）
      - transit  → /v3/direction/transit/integrated（公交路径规划）
      - driving / take_taxi → /v3/direction/driving（驾车路径规划）
      - distance → /v3/distance                 （距离测量）

    参数提取使用 _first_present 支持别名（如 city/adcode/district 均可作为城市参数），
    参数不足时返回 None，让外层 _mock_payload（第三级）兜底。
    """
    lower_name = tool_name.lower()

    # 天气：提取城市标识，支持 city / adcode / district / destination 参数名
    if "weather" in lower_name:
        city = _first_present(args, ("city", "adcode", "district", "destination"))
        if city:
            return _call_amap_rest(
                "/v3/weather/weatherInfo",
                {"city": city, "extensions": args.get("extensions", "base")},
            )

    # 公交路径规划：需要起点、终点、城市三个参数，缺少任一个则降级到 mock
    if "transit" in lower_name:
        origin = _first_present(args, ("origin", "start", "from"))
        destination = _first_present(args, ("destination", "end", "to"))
        city = _first_present(args, ("city", "city1"))
        if origin and destination and city:
            return _call_amap_rest(
                "/v3/direction/transit/integrated",
                {"origin": origin, "destination": destination, "city": city},
            )

    # 驾车 / 打车：只需起点和终点
    if "driving" in lower_name or "take_taxi" in lower_name:
        origin = _first_present(args, ("origin", "start", "from"))
        destination = _first_present(args, ("destination", "end", "to"))
        if origin and destination:
            return _call_amap_rest(
                "/v3/direction/driving",
                {"origin": origin, "destination": destination},
            )

    # 距离测量：支持多起点（origins）到单一终点的批量距离计算
    if "distance" in lower_name:
        origins = _first_present(args, ("origins", "origin", "start"))
        destination = _first_present(args, ("destination", "end", "to"))
        if origins and destination:
            return _call_amap_rest(
                "/v3/distance",
                {"origins": origins, "destination": destination},
            )

    return None


def _mock_payload(tool_name: str, args: dict[str, Any], error: str) -> dict[str, Any]:
    """最后一级静态兜底，保证 Agent 不因地图工具失败而中断。"""
    lower_name = tool_name.lower()
    origin = _first_present(args, ("origin", "start", "from")) or "起点待确认"
    destination = _first_present(args, ("destination", "end", "to", "city")) or "目的地待确认"

    if "weather" in lower_name:
        summary = "天气暂不可实时确认，建议同时准备晴天和雨天两套出行方案。"
    elif "transit" in lower_name:
        summary = f"公交路线暂不可实时确认，可先以 {origin} 到 {destination} 的地铁/公交常规方案作为占位。"
    elif "driving" in lower_name or "take_taxi" in lower_name:
        summary = f"打车方案暂不可实时确认，可先按 {origin} 到 {destination} 的常规道路路线估算。"
    else:
        summary = "地图工具暂不可实时确认，已返回静态占位信息。"

    return {
        "status": "degraded",
        "fallback_level": "mock",
        "tool_name": tool_name,
        "summary": summary,
        "reason": error,
        "args": args,
    }


def get_tool_fallback_response(tool_name: str, args: dict[str, Any], error: str) -> str:
    """工具层三级兜底：MCP 失败 -> 高德 REST 备用 API -> 静态 mock。"""
    try:
        backup_payload = _backup_api_payload(tool_name, args)
        if backup_payload is not None:
            return _json_dumps(
                {
                    "status": "degraded",
                    "fallback_level": "backup_api",
                    "tool_name": tool_name,
                    "data": backup_payload,
                    "reason": error,
                }
            )
    except Exception as backup_exc:
        logger.warning(
            f"[tool fallback] 备用 API 失败：{tool_name}; reason: {backup_exc}",
            exc_info=True,
        )

    return _json_dumps(_mock_payload(tool_name, args, error))
