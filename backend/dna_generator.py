import hashlib
import random
from typing import Any, Dict, List, Optional, Tuple

from .fonts_manager import list_fonts
from .learning import get_blocked_sets, get_recent_combo_hashes, get_usage_counts, get_weights

STYLE_DIRECTIONS = [
    {"id": "auto", "label": "おまかせ"},
    {"id": "luxury", "label": "高級感・ラグジュアリー"},
    {"id": "calm", "label": "落ち着いた・上品"},
    {"id": "stylish", "label": "スタイリッシュ"},
    {"id": "pop", "label": "ポップ・明るい"},
    {"id": "minimal", "label": "シンプル・ミニマル"},
    {"id": "cool", "label": "寒色系"},
    {"id": "warm", "label": "暖色系"},
    {"id": "monotone", "label": "モノトーン"},
    {"id": "natural", "label": "ナチュラル"},
]

STYLE_LABEL_MAP = {s["id"]: s["label"] for s in STYLE_DIRECTIONS}

ANIMATION_POOL = [
    {"id": "fade_in", "label": "フェードイン", "energy": "calm", "styles": ["luxury", "calm", "minimal", "natural"]},
    {"id": "slide_in", "label": "スライドイン", "energy": "medium", "styles": ["stylish", "minimal", "cool", "warm", "monotone"]},
    {"id": "zoom_in", "label": "ズームイン", "energy": "impact", "styles": ["luxury", "stylish", "pop"]},
    {"id": "char_reveal", "label": "文字単位の順次出現", "energy": "medium", "styles": ["calm", "luxury", "natural", "stylish"]},
    {"id": "mask_wipe", "label": "マスクワイプ表示", "energy": "sharp", "styles": ["stylish", "minimal", "monotone", "cool"]},
    {"id": "typing", "label": "タイピング風表示", "energy": "sharp", "styles": ["stylish", "minimal", "pop"]},
    {"id": "popup", "label": "ポップアップ", "energy": "lively", "styles": ["pop", "warm", "natural"]},
    {"id": "blur_in", "label": "ブラーからの出現", "energy": "calm", "styles": ["luxury", "calm", "stylish", "cool"]},
    {"id": "split_reveal", "label": "上下・左右分割展開", "energy": "sharp", "styles": ["stylish", "luxury", "monotone"]},
    {"id": "clip_expand", "label": "クリップ・フレーム展開", "energy": "medium", "styles": ["luxury", "minimal", "warm", "stylish"]},
]

DECORATION_POOL = [
    {"id": "none", "label": "背景なし（文字装飾のみ）", "styles": ["minimal", "luxury", "calm", "monotone"]},
    {"id": "pill_bg", "label": "角丸バッジ背景", "styles": ["pop", "warm", "stylish", "natural"]},
    {"id": "frosted_card", "label": "半透明カード背景", "styles": ["calm", "stylish", "cool", "luxury"]},
    {"id": "left_accent_bar", "label": "左アクセント縦ライン", "styles": ["stylish", "minimal", "cool", "warm"]},
    {"id": "underline_sweep", "label": "アンダーライン強調", "styles": ["luxury", "calm", "stylish", "natural"]},
    {"id": "box_outline", "label": "細枠フレーム囲み", "styles": ["luxury", "minimal", "monotone"]},
    {"id": "corner_brackets", "label": "コーナーブラケット枠", "styles": ["stylish", "luxury", "cool"]},
    {"id": "double_line", "label": "上下ダブルライン", "styles": ["luxury", "calm", "natural"]},
]

PALETTE_SEEDS = [
    {
        "id": "champagne_obsidian",
        "name": "シャンパンゴールド × 漆黒",
        "text": (250, 245, 232),
        "accent": (218, 182, 112),
        "stroke": (20, 18, 15),
        "badge_bg": (18, 16, 14, 210),
        "scrim": (10, 10, 12),
        "styles": ["luxury", "calm", "warm"],
    },
    {
        "id": "pure_monochrome",
        "name": "ピュアホワイト × モノトーン",
        "text": (255, 255, 255),
        "accent": (210, 214, 220),
        "stroke": (15, 17, 20),
        "badge_bg": (15, 17, 20, 210),
        "scrim": (8, 10, 14),
        "styles": ["monotone", "minimal", "stylish"],
    },
    {
        "id": "inverted_editorial",
        "name": "チャコール文字 × クリーン白帯",
        "text": (26, 28, 34),
        "accent": (175, 130, 72),
        "stroke": (255, 255, 255),
        "badge_bg": (248, 247, 244, 235),
        "scrim": (15, 18, 22),
        "styles": ["minimal", "calm", "monotone", "luxury"],
        "requires_badge": True,
    },
    {
        "id": "deep_ocean_cyan",
        "name": "日本海ディープブルー × シアン",
        "text": (246, 251, 255),
        "accent": (94, 212, 236),
        "stroke": (10, 24, 42),
        "badge_bg": (12, 28, 48, 215),
        "scrim": (8, 20, 36),
        "styles": ["cool", "stylish", "calm"],
    },
    {
        "id": "nordic_ice",
        "name": "アイスホワイト × スレートブルー",
        "text": (244, 248, 252),
        "accent": (138, 180, 248),
        "stroke": (22, 30, 44),
        "badge_bg": (28, 38, 56, 205),
        "scrim": (18, 26, 38),
        "styles": ["cool", "minimal", "stylish"],
    },
    {
        "id": "terracotta_warm",
        "name": "ウォームアイボリー × テラコッタ",
        "text": (255, 250, 242),
        "accent": (240, 138, 93),
        "stroke": (38, 22, 16),
        "badge_bg": (46, 26, 18, 215),
        "scrim": (30, 18, 12),
        "styles": ["warm", "natural", "pop"],
    },
    {
        "id": "sunset_amber",
        "name": "サンセットアンバー × ダークブラウン",
        "text": (255, 252, 245),
        "accent": (251, 191, 36),
        "stroke": (35, 24, 14),
        "badge_bg": (34, 24, 16, 215),
        "scrim": (24, 16, 10),
        "styles": ["warm", "pop", "luxury"],
    },
    {
        "id": "forest_sage",
        "name": "ナチュラルセージ × オフホワイト",
        "text": (248, 250, 245),
        "accent": (163, 209, 158),
        "stroke": (22, 34, 24),
        "badge_bg": (26, 42, 28, 215),
        "scrim": (18, 28, 20),
        "styles": ["natural", "calm"],
    },
    {
        "id": "kominka_wafu",
        "name": "和紙クリーム × 墨黒 × 朱アクセント",
        "text": (32, 28, 24),
        "accent": (196, 69, 54),
        "stroke": (246, 241, 231),
        "badge_bg": (245, 239, 228, 235),
        "scrim": (20, 16, 14),
        "styles": ["natural", "calm", "warm"],
        "requires_badge": True,
    },
    {
        "id": "pop_emerald",
        "name": "ブライトホワイト × エメラルド",
        "text": (255, 255, 255),
        "accent": (52, 211, 153),
        "stroke": (14, 30, 26),
        "badge_bg": (16, 42, 36, 220),
        "scrim": (10, 22, 20),
        "styles": ["pop", "stylish", "cool"],
    },
    {
        "id": "pop_coral",
        "name": "クリーンホワイト × コーラルピンク",
        "text": (255, 255, 255),
        "accent": (251, 113, 133),
        "stroke": (36, 14, 22),
        "badge_bg": (40, 16, 26, 215),
        "scrim": (24, 10, 16),
        "styles": ["pop", "warm"],
    },
    {
        "id": "urban_slate",
        "name": "アーバンシルバー × ネオンブルー",
        "text": (245, 247, 250),
        "accent": (56, 189, 248),
        "stroke": (15, 23, 42),
        "badge_bg": (15, 23, 42, 220),
        "scrim": (10, 15, 28),
        "styles": ["stylish", "cool", "monotone"],
    },
]

CAMERA_MOTIONS = [
    "zoom_in_punch",
    "zoom_in_slow",
    "zoom_out_reveal",
    "pan_left",
    "pan_right",
    "static_clean",
]

TRANSITIONS = ["fade", "wipeleft", "wiperight", "slideup", "smoothleft", "fadeblack"]

FONT_CATEGORY_STYLES = {
    "mincho": ["luxury", "calm", "natural"],
    "gothic": ["stylish", "pop", "cool", "warm", "monotone"],
    "modern": ["stylish", "minimal", "cool", "monotone"],
    "minimal": ["minimal", "calm", "monotone", "cool"],
    "rounded": ["pop", "natural", "warm", "calm"],
    "pop": ["pop", "warm"],
    "display": ["pop", "stylish", "luxury"],
    "brush": ["natural", "luxury", "warm"],
}


# テロップの文字装飾（縁取り・光・立体影・グラデ塗り・傾き）。全パターンに必ず1つ適用される。
# *_ratio は文字サイズに対する比率。fill は [上の色, 下の色]。
TELOP_STYLES = [
    {"id": "blue_glow", "label": "ブルーグロー×白縁",
     "fill": [[95, 145, 255], [25, 50, 230]], "outline_color": [255, 255, 255], "outline_ratio": 0.11,
     "glow_color": [40, 110, 255], "glow_ratio": 0.16, "glow_gain": 2.4,
     "skew_choices": [0, 0, 0.18], "styles": ["cool", "stylish", "pop"]},
    {"id": "yellow_3d", "label": "イエロー立体影",
     "fill": [[255, 247, 60], [255, 214, 0]], "outline_color": [95, 62, 0], "outline_ratio": 0.05,
     "extrude_color": [176, 128, 0], "extrude_ratio": 0.09, "extrude_dir": [1, 1],
     "skew_choices": [0, 0.2, 0.2], "styles": ["pop", "warm"]},
    {"id": "red_glow", "label": "レッドグロー×黄白グラデ",
     "fill": [[255, 255, 255], [255, 226, 0]], "outline_color": [255, 40, 30], "outline_ratio": 0.07,
     "glow_color": [255, 30, 30], "glow_ratio": 0.18, "glow_gain": 2.6,
     "skew_choices": [0], "styles": ["pop", "warm", "stylish"]},
    {"id": "white_black_italic", "label": "白文字×黒縁イタリック",
     "fill": [[255, 255, 255], [255, 255, 255]], "outline_color": [0, 0, 0], "outline_ratio": 0.13,
     "skew_choices": [0.18, 0.22], "styles": ["monotone", "stylish", "minimal", "pop"]},
    {"id": "orange_yellow_glow", "label": "オレンジ×白縁×黄グロー",
     "fill": [[255, 184, 0], [255, 100, 0]], "outline_color": [255, 255, 255], "outline_ratio": 0.10,
     "glow_color": [255, 230, 70], "glow_ratio": 0.15, "glow_gain": 2.2,
     "skew_choices": [0, 0.18], "styles": ["warm", "pop"]},
    {"id": "yellow_black", "label": "黄文字×黒縁",
     "fill": [[255, 230, 50], [255, 198, 0]], "outline_color": [0, 0, 0], "outline_ratio": 0.13,
     "extrude_color": [0, 0, 0], "extrude_ratio": 0.05, "extrude_dir": [1, 1],
     "skew_choices": [0, 0.18], "styles": ["pop", "warm", "stylish"]},
    {"id": "white_navy_3d", "label": "白文字×ネイビー立体",
     "fill": [[255, 255, 255], [215, 232, 255]], "outline_color": [10, 30, 90], "outline_ratio": 0.08,
     "extrude_color": [10, 30, 90], "extrude_ratio": 0.10, "extrude_dir": [1, 1],
     "skew_choices": [0, 0.18], "styles": ["cool", "stylish", "calm"]},
    {"id": "pink_neon", "label": "ピンクネオン",
     "fill": [[255, 255, 255], [255, 225, 240]], "outline_color": [255, 70, 170], "outline_ratio": 0.07,
     "glow_color": [255, 70, 170], "glow_ratio": 0.2, "glow_gain": 2.6,
     "skew_choices": [0], "styles": ["pop", "stylish"]},
    {"id": "cyan_neon", "label": "シアンネオン",
     "fill": [[255, 255, 255], [215, 250, 255]], "outline_color": [40, 220, 255], "outline_ratio": 0.07,
     "glow_color": [40, 220, 255], "glow_ratio": 0.2, "glow_gain": 2.6,
     "skew_choices": [0], "styles": ["cool", "stylish"]},
    {"id": "red_white_black", "label": "赤文字×白縁×黒影",
     "fill": [[255, 90, 75], [220, 10, 30]], "outline_color": [255, 255, 255], "outline_ratio": 0.10,
     "extrude_color": [0, 0, 0], "extrude_ratio": 0.07, "extrude_dir": [1, 1],
     "skew_choices": [0, 0.18], "styles": ["pop", "warm"]},
    {"id": "lime_green", "label": "ライムグリーン×濃緑縁",
     "fill": [[200, 255, 80], [40, 200, 90]], "outline_color": [8, 70, 32], "outline_ratio": 0.09,
     "glow_color": [160, 255, 70], "glow_ratio": 0.14, "glow_gain": 2.0,
     "skew_choices": [0, 0.18], "styles": ["natural", "pop"]},
    {"id": "gold_brown", "label": "ゴールド×焦げ茶縁",
     "fill": [[255, 242, 175], [214, 160, 40]], "outline_color": [60, 35, 10], "outline_ratio": 0.07,
     "glow_color": [255, 200, 80], "glow_ratio": 0.10, "glow_gain": 1.6,
     "extrude_color": [90, 55, 10], "extrude_ratio": 0.05, "extrude_dir": [1, 1],
     "skew_choices": [0], "styles": ["luxury", "warm", "calm"]},
    {"id": "silver_black", "label": "シルバー×黒縁",
     "fill": [[255, 255, 255], [170, 182, 198]], "outline_color": [15, 20, 30], "outline_ratio": 0.09,
     "extrude_color": [15, 20, 30], "extrude_ratio": 0.05, "extrude_dir": [1, 1],
     "skew_choices": [0, 0.18], "styles": ["monotone", "minimal", "luxury", "stylish"]},
]


def _build_telop(base: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    t = {k: v for k, v in base.items() if k not in ("styles", "skew_choices")}
    t["outline_ratio"] = round(base["outline_ratio"] * rng.uniform(0.9, 1.2), 3)
    t["skew"] = rng.choice(base["skew_choices"]) if base.get("skew_choices") else 0.0
    return t


def _relative_luminance(rgb: Tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def _contrast_ratio(rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int]) -> float:
    l1 = _relative_luminance(rgb1)
    l2 = _relative_luminance(rgb2)
    bright, dark = max(l1, l2), min(l1, l2)
    return (bright + 0.05) / (dark + 0.05)


def _clamp_rgb(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return (max(0, min(255, rgb[0])), max(0, min(255, rgb[1])), max(0, min(255, rgb[2])))


def _jitter_palette(seed: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    delta = lambda s: rng.randint(-s, s)
    accent = _clamp_rgb((seed["accent"][0] + delta(14), seed["accent"][1] + delta(14), seed["accent"][2] + delta(14)))
    text = seed["text"]
    badge_bg = seed["badge_bg"]
    scrim = seed["scrim"]
    stroke = seed["stroke"]

    bg_ref = (badge_bg[0], badge_bg[1], badge_bg[2])
    if _contrast_ratio(text, bg_ref) < 4.5:
        text = (255, 255, 255) if _relative_luminance(bg_ref) < 0.4 else (20, 22, 26)

    return {
        "id": seed["id"],
        "name": seed["name"],
        "text": list(text),
        "accent": list(accent),
        "stroke": list(stroke),
        "badge_bg": list(badge_bg),
        "scrim": list(scrim),
        "styles": seed["styles"],
        "requires_badge": seed.get("requires_badge", False),
    }


def _build_narrative_segments(project: Dict[str, Any], duration_mode: str, asset_count: int, rng: random.Random) -> Dict[str, Any]:
    bullets = [b.strip() for b in project.get("appeal_bullets", []) if b and b.strip()]
    free_lines = [
        ln.strip()
        for ln in project.get("appeal_free_text", "").replace("\r\n", "\n").split("\n")
        if ln.strip()
    ]
    all_appeals: List[str] = []
    seen = set()
    for item in bullets + free_lines:
        if item not in seen:
            seen.add(item)
            all_appeals.append(item)

    prop = project.get("property_info", {})
    spec_lines: List[str] = []
    if prop.get("price", "").strip():
        p = prop["price"].strip()
        spec_lines.append(p if "価格" in p else f"価格 {p}")
    if prop.get("location", "").strip():
        spec_lines.append(f"所在地 {prop['location'].strip()}")
    if prop.get("land_area", "").strip():
        spec_lines.append(f"土地 {prop['land_area'].strip()}")
    if prop.get("building_area", "").strip():
        spec_lines.append(f"建物 {prop['building_area'].strip()}")
    if prop.get("other_info", "").strip():
        spec_lines.append(prop["other_info"].strip())

    hook_main = all_appeals[0] if all_appeals else (spec_lines[0] if spec_lines else "物件のご紹介")
    hook_sub = ""
    if prop.get("location", "").strip() and prop["location"].strip() not in hook_main:
        hook_sub = prop["location"].strip()
    elif prop.get("price", "").strip() and prop["price"].strip() not in hook_main:
        p = prop["price"].strip()
        hook_sub = p if "価格" in p else f"価格 {p}"

    remaining_appeals = all_appeals[1:]
    body_slides: List[Dict[str, Any]] = []

    if remaining_appeals:
        body_slides.append({
            "headline": remaining_appeals[0],
            "sublines": remaining_appeals[1:2],
        })
    if len(remaining_appeals) > 2 or spec_lines:
        extra_head = remaining_appeals[2] if len(remaining_appeals) > 2 else (spec_lines[0] if spec_lines else "")
        extra_subs = spec_lines[:3] if len(remaining_appeals) > 2 else spec_lines[1:4]
        if extra_head or extra_subs:
            body_slides.append({
                "headline": extra_head,
                "sublines": extra_subs,
            })

    if duration_mode == "short":
        hook_dur = round(rng.uniform(1.8, 2.1), 2)
        seg_body_dur = round(rng.uniform(1.6, 2.0), 2)
        if len(body_slides) > 1:
            body_slides = body_slides[:1]
    elif duration_mode == "long":
        hook_dur = round(rng.uniform(2.0, 2.4), 2)
        seg_body_dur = round(rng.uniform(2.2, 2.8), 2)
    elif duration_mode == "medium":
        hook_dur = round(rng.uniform(1.9, 2.2), 2)
        seg_body_dur = round(rng.uniform(1.8, 2.4), 2)
    else:
        hook_dur = round(rng.uniform(1.85, 2.25), 2)
        seg_body_dur = round(rng.uniform(1.75, 2.35), 2)

    if not body_slides and (asset_count > 1 or spec_lines):
        body_slides.append({
            "headline": spec_lines[0] if spec_lines else hook_main,
            "sublines": spec_lines[1:3],
        })

    scenes: List[Dict[str, Any]] = [
        {
            "role": "hook",
            "duration": hook_dur,
            "headline": hook_main,
            "sublines": [hook_sub] if hook_sub else [],
        }
    ]
    for bs in body_slides:
        scenes.append(
            {
                "role": "body",
                "duration": seg_body_dur,
                "headline": bs["headline"],
                "sublines": bs["sublines"],
            }
        )

    trans_dur = 0.35 if len(scenes) > 1 else 0.0
    total_dur = sum(s["duration"] for s in scenes) - max(0, len(scenes) - 1) * trans_dur
    return {
        "hook_duration": hook_dur,
        "transition_duration": trans_dur,
        "total_duration": round(total_dur, 2),
        "scenes": scenes,
    }


def _weighted_pick(
    candidates: List[Dict[str, Any]],
    id_key: str,
    weights_map: Dict[str, float],
    usage_map: Dict[str, int],
    mode: str,
    rng: random.Random,
    preferred_styles: List[str],
    style_weights: Dict[str, float],
) -> Dict[str, Any]:
    if not candidates:
        raise ValueError("候補が存在しません。")

    if mode == "explore_novel":
        min_use = min(usage_map.get(c[id_key], 0) for c in candidates)
        novel = [c for c in candidates if usage_map.get(c[id_key], 0) <= min_use + 1]
        return rng.choice(novel)

    if mode == "uniform":
        return rng.choice(candidates)

    scored: List[float] = []
    for c in candidates:
        cid = c[id_key]
        w = 1.0
        raw_score = weights_map.get(cid, 0.0)
        w *= max(0.3, min(2.8, 1.0 + raw_score * 0.35))

        c_styles = c.get("styles") or FONT_CATEGORY_STYLES.get(c.get("category", "gothic"), [])
        if preferred_styles and "auto" not in preferred_styles:
            if any(st in c_styles for st in preferred_styles):
                w *= 2.2
        for st in c_styles:
            if style_weights.get(st, 0.0) > 0:
                w *= min(1.8, 1.0 + style_weights[st] * 0.15)

        scored.append(w)

    return rng.choices(candidates, weights=scored, k=1)[0]


def generate_batch_dnas(
    project: Dict[str, Any],
    count: int = 10,
    assets: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rng = random.Random()
    # 商用利用が不可・要確認のフォント(commercial_ok=0)は自動生成に使わない
    fonts = [f for f in list_fonts(only_enabled=True) if f.get("commercial_ok", 1)]
    if not fonts:
        raise ValueError("有効なフォントがありません。フォントライブラリから1つ以上有効にしてください。")

    blocked = get_blocked_sets()
    weights = get_weights()
    usage = get_usage_counts()
    recent_combos = get_recent_combo_hashes(150)

    valid_fonts = [f for f in fonts if f["id"] not in blocked["font"]] or fonts
    valid_anims = [a for a in ANIMATION_POOL if a["id"] not in blocked["animation"]] or ANIMATION_POOL
    valid_palettes = [p for p in PALETTE_SEEDS if p["id"] not in blocked["palette"]] or PALETTE_SEEDS

    selected_styles = project.get("styles") or ["auto"]
    duration_mode = project.get("duration_mode", "auto")
    asset_count = len(assets or [])

    modes_pool = ["weighted"] * 4 + ["uniform"] * 4 + ["explore_novel"] * 2
    rng.shuffle(modes_pool)

    generated: List[Dict[str, Any]] = []
    used_in_batch_combos = set()
    used_fonts_count: Dict[str, int] = {}
    used_anims_count: Dict[str, int] = {}
    used_telop_count: Dict[str, int] = {}

    for idx in range(count):
        mode = modes_pool[idx % len(modes_pool)]
        best_dna: Optional[Dict[str, Any]] = None

        for attempt in range(25):
            font_candidates = [
                f for f in valid_fonts
                if len(valid_fonts) < 4 or used_fonts_count.get(f["id"], 0) < 2
            ] or valid_fonts
            font = _weighted_pick(
                font_candidates, "id", weights["font"], usage["font"], mode, rng, selected_styles, weights["style"]
            )

            palette_seed = _weighted_pick(
                valid_palettes, "id", weights["palette"], usage["palette"], mode, rng, selected_styles, weights["style"]
            )
            palette = _jitter_palette(palette_seed, rng)

            # テロップの文字装飾は必ず1つ適用する（選んだスタイル方向に合うものを優先）
            tel_pool = TELOP_STYLES
            if selected_styles and "auto" not in selected_styles:
                styled_tel = [t for t in TELOP_STYLES if any(s in t["styles"] for s in selected_styles)]
                if styled_tel and rng.random() < 0.8:
                    tel_pool = styled_tel
            min_tel = min(used_telop_count.get(t["id"], 0) for t in tel_pool)
            tel_pool = [t for t in tel_pool if used_telop_count.get(t["id"], 0) <= min_tel + 1]
            telop = _build_telop(rng.choice(tel_pool), rng)
            # 文字色はテロップ装飾が決めるので、帯の背景は暗めに揃えて読みやすくする
            if _relative_luminance(tuple(palette["badge_bg"][:3])) > 0.4:
                palette["badge_bg"] = [20, 22, 28, 215]
            palette["requires_badge"] = False

            anim_candidates = [
                a for a in valid_anims
                if len(valid_anims) < 5 or used_anims_count.get(a["id"], 0) < 2
            ] or valid_anims
            hook_anim = _weighted_pick(
                anim_candidates, "id", weights["animation"], usage["animation"], mode, rng, selected_styles, weights["style"]
            )

            body_anim_pool = [a for a in valid_anims if a["energy"] != "lively" or hook_anim["energy"] == "lively"] or valid_anims
            body_anim = rng.choice(body_anim_pool)

            if palette.get("requires_badge"):
                deco_candidates = [d for d in DECORATION_POOL if d["id"] in ("pill_bg", "frosted_card")]
            else:
                deco_candidates = DECORATION_POOL
                if selected_styles and "auto" not in selected_styles:
                    styled_decos = [d for d in deco_candidates if any(s in d["styles"] for s in selected_styles)]
                    if styled_decos and rng.random() < 0.75:
                        deco_candidates = styled_decos
            decoration = rng.choice(deco_candidates)

            hook_zone = rng.choices(["center", "lower_third", "top"], weights=[0.45, 0.35, 0.20], k=1)[0]
            body_zone = rng.choice(["lower_third", "center"])
            align = rng.choices(["center", "left", "right"], weights=[0.6, 0.3, 0.1], k=1)[0]

            hook_size = rng.randint(68, 92)
            body_size = rng.randint(50, 66)
            letter_spacing = rng.randint(0, 6)
            line_spacing = round(rng.uniform(1.20, 1.40), 2)

            use_stroke = rng.random() < 0.65 and not palette.get("requires_badge")
            stroke_width = rng.randint(2, 4) if use_stroke else 0
            shadow_blur = rng.randint(4, 12) if not palette.get("requires_badge") else 0
            shadow_opacity = round(rng.uniform(0.35, 0.75), 2) if shadow_blur > 0 else 0.0

            slide_dir = rng.choice(["up", "down", "left", "right"])
            anim_speed = round(rng.uniform(0.45, 0.80), 2)

            hook_camera = rng.choice(["zoom_in_punch", "zoom_in_slow", "zoom_out_reveal", "pan_left", "pan_right"])
            body_cameras = [rng.choice(CAMERA_MOTIONS) for _ in range(3)]
            transition = rng.choice(TRANSITIONS)
            scrim_strength = round(rng.uniform(0.36, 0.58), 2)

            matched_styles = [s for s in selected_styles if s != "auto"]
            primary_style = rng.choice(matched_styles) if matched_styles else rng.choice(palette["styles"])

            combo_key = f"{font['id']}|{palette['id']}|{hook_anim['id']}|{decoration['id']}|{hook_zone}|{align}|{telop['id']}"
            combo_hash = hashlib.sha1(combo_key.encode("utf-8")).hexdigest()[:12]

            if (
                combo_hash in blocked["combo"]
                or combo_hash in used_in_batch_combos
                or (attempt < 15 and combo_hash in recent_combos)
            ):
                continue

            narrative = _build_narrative_segments(project, duration_mode, asset_count, rng)

            best_dna = {
                "combo_hash": combo_hash,
                "generation_mode": mode,
                "primary_style": primary_style,
                "primary_style_label": STYLE_LABEL_MAP.get(primary_style, primary_style),
                "font_id": font["id"],
                "font_name": font["display_name"],
                "font_path": font["file_path"],
                "font_category": font["category"],
                "font_weight": rng.choice([700, 800, 900]),  # 可変フォントの太さ（静的フォントでは無視）
                "palette_id": palette["id"],
                "palette_name": palette["name"],
                "palette": palette,
                "hook_animation": hook_anim["id"],
                "hook_animation_label": hook_anim["label"],
                "body_animation": body_anim["id"],
                "body_animation_label": body_anim["label"],
                "slide_direction": slide_dir,
                "anim_duration": anim_speed,
                "decoration": decoration["id"],
                "decoration_label": decoration["label"],
                "telop": telop,
                "telop_label": telop["label"],
                "hook_zone": hook_zone,
                "body_zone": body_zone,
                "align": align,
                "hook_size": hook_size,
                "body_size": body_size,
                "letter_spacing": letter_spacing,
                "line_spacing": line_spacing,
                "stroke_width": stroke_width,
                "shadow_blur": shadow_blur,
                "shadow_opacity": shadow_opacity,
                "shadow_offset": [3, 5],
                "hook_camera": hook_camera,
                "body_cameras": body_cameras,
                "transition": transition,
                "scrim_strength": scrim_strength,
                "narrative": narrative,
                "summary_title": f"{font['display_name']} × {hook_anim['label']} × {telop['label']}",
            }
            break

        if best_dna is None:
            best_dna = generated[-1].copy() if generated else {}

        used_in_batch_combos.add(best_dna["combo_hash"])
        used_fonts_count[best_dna["font_id"]] = used_fonts_count.get(best_dna["font_id"], 0) + 1
        used_anims_count[best_dna["hook_animation"]] = used_anims_count.get(best_dna["hook_animation"], 0) + 1
        tid = best_dna.get("telop", {}).get("id")
        if tid:
            used_telop_count[tid] = used_telop_count.get(tid, 0) + 1
        generated.append(best_dna)

    return generated