#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

DAY_NAMES = {
    0: ["pondeli", "pondělí"],
    1: ["utery", "úterý"],
    2: ["streda", "středa"],
    3: ["ctvrtek", "čtvrtek"],
    4: ["patek", "pátek"],
    5: ["sobota"],
    6: ["nedele", "neděle"],
}

USER_AGENT = "LunchBoardBot/1.0 (+office menu sync)"


@dataclass
class ParseResult:
    items: list[dict[str, Any]]
    raw_lines: list[str]
    notes: list[str]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_day(text: str) -> str:
    value = normalize_space(text).lower()
    value = (
        value.replace("á", "a")
        .replace("č", "c")
        .replace("ď", "d")
        .replace("é", "e")
        .replace("ě", "e")
        .replace("í", "i")
        .replace("ň", "n")
        .replace("ó", "o")
        .replace("ř", "r")
        .replace("š", "s")
        .replace("ť", "t")
        .replace("ú", "u")
        .replace("ů", "u")
        .replace("ý", "y")
        .replace("ž", "z")
    )
    return value


def split_price(line: str) -> dict[str, Any]:
    cleaned = normalize_space(line)
    m = re.search(r"^(.*?)(\d{2,4}\s*(?:Kc|Kč|,-|,-\s*Kc|,-\s*Kč)?)$", cleaned, flags=re.IGNORECASE)
    if not m:
        return {"title": cleaned, "price": None}

    raw_price = normalize_space(m.group(2))
    digits_match = re.search(r"(\d{2,3})", raw_price)
    normalized_price = None
    if digits_match:
        amount = int(digits_match.group(1))
        if 0 < amount < 1000:
            normalized_price = f"{amount} Kč"

    return {"title": normalize_space(m.group(1)), "price": normalized_price}


def normalize_price_value(raw_price: str | None) -> str | None:
    if not raw_price:
        return None
    digits_match = re.search(r"(\d{2,3})", raw_price)
    if not digits_match:
        return None
    amount = int(digits_match.group(1))
    if not (0 < amount < 1000):
        return None
    return f"{amount} Kč"


def parse_zlatyklas_items(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for raw_line in lines:
        line = normalize_space(raw_line)
        if not line:
            continue

        norm = normalize_day(line)

        # Ignore placeholder row labels from the source CMS.
        if norm == "polozka":
            continue

        # Pattern: "Polozka 189 Kč" -> attach price to previous item when possible.
        placeholder_price = re.match(r"^polozka\s+(\d{2,3})\s*(?:kc|kč|,-)?$", norm, flags=re.IGNORECASE)
        if placeholder_price:
            price_value = normalize_price_value(placeholder_price.group(1))
            if items and not items[-1].get("price") and price_value:
                items[-1]["price"] = price_value
            continue

        # Pattern: "49 Kč" as a standalone line.
        price_only = re.match(r"^(\d{2,3})\s*(?:Kc|Kč|,-)\s*$", line, flags=re.IGNORECASE)
        if price_only:
            price_value = normalize_price_value(price_only.group(1))
            if items and not items[-1].get("price") and price_value:
                items[-1]["price"] = price_value
            continue

        # Pattern: "189 Kč Název jídla"
        leading = re.match(r"^(\d{2,3})\s*(?:Kc|Kč|,-)?\s+(.+)$", line, flags=re.IGNORECASE)
        if leading:
            price_value = normalize_price_value(leading.group(1))
            title = normalize_space(leading.group(2))
            if title:
                items.append({"title": title, "price": price_value})
            continue

        # Pattern: "Název jídla 189 Kč"
        trailing = split_price(line)
        if trailing.get("title"):
            items.append(trailing)

    return items


def day_aliases_for_date(target: datetime) -> list[str]:
    return DAY_NAMES[target.weekday()]


def text_contains_today(text: str, target: datetime) -> bool:
    normalized = normalize_day(text)
    return any(alias in normalized for alias in day_aliases_for_date(target))


def parse_week_sections_from_headers(soup: BeautifulSoup) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    for heading in soup.find_all(["h2", "h3", "p", "strong"]):
        heading_text = normalize_space(heading.get_text(" ", strip=True))
        norm_heading = normalize_day(heading_text)
        for aliases in DAY_NAMES.values():
            for alias in aliases:
                if alias in norm_heading:
                    lines: list[str] = []
                    node = heading.find_next_sibling()
                    while node is not None:
                        node_name = getattr(node, "name", "")
                        if node_name in {"h2", "h3"}:
                            break
                        line = normalize_space(getattr(node, "get_text", lambda *args, **kwargs: "")(" ", strip=True))
                        if line:
                            lines.append(line)
                        node = node.find_next_sibling()
                    sections[alias] = lines
    return sections


def parse_tradice(html: str, target: datetime) -> ParseResult:
    soup = BeautifulSoup(html, "lxml")
    blocks: dict[str, list[str]] = {}

    for h2 in soup.select("h2.center"):
        heading = normalize_space(h2.get_text(" ", strip=True))
        day_key = None
        heading_norm = normalize_day(heading)
        for aliases in DAY_NAMES.values():
            for alias in aliases:
                if alias in heading_norm:
                    day_key = alias
                    break
            if day_key:
                break
        if not day_key:
            continue

        section = h2.find_next_sibling("div", class_="separator-section")
        if not section:
            continue

        lines: list[str] = []
        for row in section.select("div.row.item"):
            title = normalize_space(row.select_one(".fourfifth").get_text(" ", strip=True) if row.select_one(".fourfifth") else "")
            price = normalize_space(row.select_one(".fifth.price").get_text(" ", strip=True) if row.select_one(".fifth.price") else "")
            if title and price:
                lines.append(f"{title} {price}")
            elif title:
                lines.append(title)
        blocks[day_key] = lines

    today_lines: list[str] = []
    for alias in day_aliases_for_date(target):
        if alias in blocks:
            today_lines = blocks[alias]
            break

    if not today_lines:
        return ParseResult(items=[], raw_lines=[], notes=["No section for today found"])

    return ParseResult(items=[split_price(line) for line in today_lines], raw_lines=today_lines, notes=[])


def parse_formanka(html: str, target: datetime) -> ParseResult:
    soup = BeautifulSoup(html, "lxml")

    source_text_container = None
    for div in soup.select("div.et_pb_text_inner"):
        txt = normalize_day(div.get_text(" ", strip=True))
        if "polevka" in txt and any(alias in txt for aliases in DAY_NAMES.values() for alias in aliases):
            source_text_container = div
            break

    if source_text_container is None:
        return ParseResult(items=[], raw_lines=[], notes=["Menu container not found"])

    paragraphs = [normalize_space(p.get_text(" ", strip=True)) for p in source_text_container.find_all("p")]
    sections: dict[str, list[str]] = {}
    current_day: str | None = None

    for line in paragraphs:
        if not line:
            continue
        norm = normalize_day(line)
        matched_day = None
        for aliases in DAY_NAMES.values():
            for alias in aliases:
                if alias in norm:
                    matched_day = alias
                    break
            if matched_day:
                break

        if matched_day and ("." in line or "(" in line or "_" not in line):
            current_day = matched_day
            sections[current_day] = []
            continue

        if current_day is None:
            continue

        if norm in {"hlavni jidla:", "doporucujeme:", "hlavni jidla", "doporucujeme"}:
            continue

        sections[current_day].append(line)

    today_lines: list[str] = []
    for alias in day_aliases_for_date(target):
        if alias in sections:
            today_lines = sections[alias]
            break

    if not today_lines:
        return ParseResult(items=[], raw_lines=[], notes=["No section for today found"])

    return ParseResult(items=[split_price(line) for line in today_lines], raw_lines=today_lines, notes=[])


def parse_zlatyklas(html: str, target: datetime) -> ParseResult:
    soup = BeautifulSoup(html, "lxml")

    menu_wrap = soup.select_one(".lunch_menu-wrapper.denni-menu")
    if not menu_wrap:
        return ParseResult(items=[], raw_lines=[], notes=["Daily menu wrapper missing"])

    lines = [normalize_space(x.get_text(" ", strip=True)) for x in menu_wrap.find_all(["p", "li", "div"])]
    lines = [
        line
        for line in lines
        if line
        and "Denní menu" not in line
        and "Nabídka hotových jídel" not in line
        and "registrovat" not in normalize_day(line)
    ]

    has_real_menu = any(re.search(r"\b\d{2,4}\s*(Kc|Kč|,-)\b", line, flags=re.IGNORECASE) for line in lines)
    if not has_real_menu:
        return ParseResult(items=[], raw_lines=[], notes=["Menu likely unpublished or already removed on source site"])

    weekly_sections = parse_week_sections_from_headers(menu_wrap)
    today_lines: list[str] = []
    for alias in day_aliases_for_date(target):
        if alias in weekly_sections:
            today_lines = weekly_sections[alias]
            break

    chosen_lines = today_lines if today_lines else lines
    parsed_items = parse_zlatyklas_items(chosen_lines)
    return ParseResult(items=parsed_items, raw_lines=chosen_lines, notes=[])


def read_previous_output(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def should_keep_previous(
    now: datetime,
    policy: dict[str, Any],
    previous_entry: dict[str, Any] | None,
) -> bool:
    if not policy.get("keep_last_successful", True):
        return False
    if not previous_entry or not previous_entry.get("items"):
        return False

    fetched_at = previous_entry.get("fetched_at")
    if not fetched_at:
        return False

    try:
        prev_dt = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False

    age_hours = (now - prev_dt).total_seconds() / 3600
    max_age = float(policy.get("max_age_hours", 36))
    if age_hours > max_age:
        return False

    hold_after = int(policy.get("hold_after_hour", 15))
    if now.hour >= hold_after:
        return True

    # Before hold hour, keep previous only when it is already today's menu.
    return previous_entry.get("menu_date") == now.date().isoformat()


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch lunch menus and write current snapshot")
    parser.add_argument("--config", default="config/restaurants.yaml")
    parser.add_argument("--output", default="data/current_menu.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg.get("timezone", "Europe/Prague"))
    now = datetime.now(tz)

    parsers = {
        "tradice": parse_tradice,
        "formanka": parse_formanka,
        "zlatyklas": parse_zlatyklas,
    }

    previous = read_previous_output(output_path)
    prev_map = {entry.get("id"): entry for entry in previous.get("restaurants", [])}

    results: list[dict[str, Any]] = []
    for r in cfg.get("restaurants", []):
        rid = r["id"]
        entry: dict[str, Any] = {
            "id": rid,
            "name": r["name"],
            "url": r["url"],
            "fetched_at": now.isoformat(),
            "menu_date": now.date().isoformat(),
            "status": "ok",
            "items": [],
            "notes": [],
        }

        parser_name = r["parser"]
        parser_fn = parsers.get(parser_name)
        if not parser_fn:
            entry["status"] = "error"
            entry["notes"].append(f"Unknown parser: {parser_name}")
            results.append(entry)
            continue

        try:
            html = fetch_html(r["url"])
            parsed = parser_fn(html, now)
            entry["items"] = parsed.items
            entry["notes"].extend(parsed.notes)
            if not parsed.items:
                entry["status"] = "empty"
        except Exception as exc:
            entry["status"] = "error"
            entry["notes"].append(str(exc))

        prev = prev_map.get(rid)
        if entry["status"] in {"empty", "error"} and should_keep_previous(now, cfg.get("stale_policy", {}), prev):
            entry = {
                **prev,
                "fetched_at": now.isoformat(),
                "status": "stale-kept",
                "notes": (entry.get("notes", []) + ["Kept previous successful menu because source is empty/unavailable now"])[:8],
            }

        results.append(entry)

    payload = {
        "generated_at": now.isoformat(),
        "timezone": str(tz),
        "day": now.strftime("%A"),
        "restaurants": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)

    print(f"Wrote {output_path} with {len(results)} restaurants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
