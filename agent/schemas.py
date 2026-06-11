import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError


class WeatherResult(BaseModel):
    """天气节点的结构化输出，解析失败时也能承载降级说明。"""

    summary: str = "天气暂不可实时确认。"
    source: str = "weather_node"
    status: str = "ok"
    suggestions: list[str] = Field(default_factory=list)


class TravelRequirements(BaseModel):
    """用户旅游需求的结构化结果，用于条件边判断是否需要追问。"""

    destination: str = ""
    origin: str | None = None
    travel_days: int | None = None
    travel_date: str | None = None
    must_see_places: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class TransitRoute(BaseModel):
    """公交路线结构，字段允许为空，避免缺少单项数据时整条路线不可用。"""

    origin: str = ""
    destination: str = ""
    duration_minutes: int | None = None
    cost_yuan: float | None = None
    transfers: int | None = None
    walking_distance_meters: int | None = None
    summary: str
    source: str = "transit_node"
    status: str = "ok"


class TaxiRoute(BaseModel):
    """打车路线结构，费用和距离通常来自实时工具，因此允许降级为空。"""

    origin: str = ""
    destination: str = ""
    duration_minutes: int | None = None
    distance_km: float | None = None
    estimated_cost_yuan: float | None = None
    summary: str
    source: str = "taxi_node"
    status: str = "ok"


ModelT = TypeVar("ModelT", bound=BaseModel)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """兼容 Pydantic v1/v2 的模型转 dict。"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def extract_json_payload(text: str) -> Any:
    """
    从 LLM 输出中提取第一段 JSON。

    LLM 常把 JSON 包在说明文字或 ```json 代码块里，这里先处理代码块，
    再用 JSONDecoder 从任意位置尝试解析，降低格式波动带来的失败率。
    """
    content = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.IGNORECASE | re.DOTALL)
    if fenced:
        content = fenced.group(1).strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(content[index:])
            return payload
        except json.JSONDecodeError:
            continue

    raise ValueError("未找到可解析的 JSON 片段")


def parse_model_from_text(
    model_cls: type[ModelT],
    text: str,
    fallback: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """
    model_cls：你希望解析成的 Pydantic 模型类，比如 TravelPlan、WeatherResult
    text：LLM 输出的原始文本
    fallback：解析失败时使用的默认兜底字典

    将 LLM 文本解析为 Pydantic 模型。

    解析失败时不抛异常，而是把原文写入 fallback 的 summary，并返回错误原因，
    供节点记录到 TravelState.errors，保证工作流继续执行。
    """
    try:
        payload = extract_json_payload(text)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        model = model_cls(**payload)
        return model_to_dict(model), None
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        degraded = dict(fallback)
        if text and not degraded.get("summary"):
            degraded["summary"] = text.strip()
        degraded.setdefault("status", "degraded")
        return degraded, f"{model_cls.__name__} 结构化解析失败：{exc}"
