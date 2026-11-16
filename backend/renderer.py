import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .fontutil import load_font
from .vertical_text import glyph_kind, to_vertical_text, wrap_vertical

from .database import BASE_DIR

TARGET_W = 1080
TARGET_H = 1920
FPS = 30

SAFE_LEFT = 76
SAFE_RIGHT = 76
SAFE_TOP = 210
SAFE_BOTTOM = 300


def find_ffmpeg() -> str:
    local_bin = BASE_DIR / "bin" / "ffmpeg.exe"
    if local_bin.exists():
        return str(local_bin)
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_media(file_path: str, media_type: str) -> Dict[str, Any]:
    if media_type == "image":
        with Image.open(file_path) as im:
            im = ImageOps.exif_transpose(im)
            return {"width": im.width, "height": im.height, "duration": 0.0}

    ffmpeg = find_ffmpeg()
    proc = subprocess.run(
        [ffmpeg, "-i", file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    stderr = proc.stderr
    dur = 0.0
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
    if m_dur:
        h, m, s = int(m_dur.group(1)), int(m_dur.group(2)), float(m_dur.group(3))
        dur = h * 3600 + m * 60 + s
    w, h_px = 1080, 1920
    m_res = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", stderr)
    if m_res:
        w, h_px = int(m_res.group(1)), int(m_res.group(2))
    return {"width": w, "height": h_px, "duration": round(dur, 2)}


def create_thumbnail(file_path: str, thumb_path: str, media_type: str) -> None:
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)
    if media_type == "image":
        with Image.open(file_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((420, 740))
            im.save(thumb_path, format="JPEG", quality=86)
    else:
        ffmpeg = find_ffmpeg()
        subprocess.run(
            [
                ffmpeg, "-y", "-ss", "0.3", "-i", file_path,
                "-vframes", "1", "-vf", "scale=420:-2", thumb_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def _ease_out_cubic(t: float) -> float:
    t = _clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def _ease_out_expo(t: float) -> float:
    t = _clamp01(t)
    return 1.0 if t >= 1.0 else 1.0 - (2.0 ** (-10.0 * t))


def _ease_out_back(t: float) -> float:
    t = _clamp01(t)
    c1 = 1.15
    c3 = c1 + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + c1 * ((t - 1.0) ** 2)


def _wrap_japanese(text: str, font: ImageFont.FreeTypeFont, max_width: int, letter_spacing: int) -> List[str]:
    if not text:
        return []
    no_start = set("、。，．・：；？！）」』】〉》〕］｝")
    lines: List[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        if not raw_line:
            continue
        cur = ""
        cur_w = 0.0
        for ch in raw_line:
            adv = font.getlength(ch) + letter_spacing
            if cur and (cur_w + adv > max_width) and (ch not in no_start):
                lines.append(cur)
                cur = ch
                cur_w = adv
            else:
                cur += ch
                cur_w += adv
        if cur:
            lines.append(cur)
    return lines


def _measure_line(line: str, font: ImageFont.FreeTypeFont, letter_spacing: int) -> float:
    if not line:
        return 0.0
    total = sum(font.getlength(ch) for ch in line)
    total += max(0, len(line) - 1) * letter_spacing
    return total


def _lerp_rgb(c1, c2, t: float) -> Tuple[int, int, int]:
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))  # type: ignore


def _telop_px(telop: Dict[str, Any], size: int) -> Tuple[int, int, int]:
    """文字サイズに比例した (縁取り幅, 立体影の深さ, 光の半径) をピクセルで返す。"""
    return (
        max(2, int(round(size * telop["outline_ratio"]))),
        int(round(size * telop.get("extrude_ratio", 0))),
        int(round(size * telop.get("glow_ratio", 0))),
    )


def _telop_pad(telop: Dict[str, Any], base_size: int, est_h: int) -> int:
    sw, ext, glow = _telop_px(telop, base_size)
    dx, dy = telop.get("extrude_dir", [1, 1])
    return sw + ext * max(dx, dy, 1) + glow * 3 + int(abs(telop.get("skew", 0)) * est_h / 2) + 12


def _telop_glyph(xy, ch: str, rec: Dict[str, Any], telop: Dict[str, Any], y0: float, y1: float) -> Dict[str, Any]:
    sw, ext, glow = _telop_px(telop, rec["size"])
    return {
        "xy": xy, "ch": ch, "font": rec["font"], "sw": sw, "ext": ext, "glow": glow,
        "line_y": (int(y0), int(y1)),
    }


def _put_glyph(mask: Image.Image, draw: ImageDraw.ImageDraw, g: Dict[str, Any], stroke: int) -> None:
    """文字1つを mask に白で描く。

    通常は g["xy"] を左上として描く。縦書き用に、次の指定ができる:
      g["anchor"]="mm" : g["xy"] を文字の中心として描く
      g["rot"]=True    : 時計回りに90度回して描く（長音「ー」や括弧など）
    """
    x, y = g["xy"]
    stroke_fill = 255 if stroke > 0 else None
    if g.get("rot"):
        f = g["font"]
        cell = int(f.size * 1.7) + 2 * int(stroke) + 8
        tmp = Image.new("L", (cell, cell), 0)
        ImageDraw.Draw(tmp).text(
            (cell / 2.0, cell / 2.0), g["ch"], font=f, fill=255,
            stroke_width=int(stroke), stroke_fill=stroke_fill, anchor="mm",
        )
        tmp = tmp.rotate(-90, resample=Image.Resampling.BICUBIC)
        mask.paste(255, (int(round(x - cell / 2.0)), int(round(y - cell / 2.0))), tmp)
        return
    kw: Dict[str, Any] = {"anchor": "mm"} if g.get("anchor") else {}
    draw.text((x, y), g["ch"], font=g["font"], fill=255,
              stroke_width=int(stroke), stroke_fill=stroke_fill, **kw)


def _compose_telop(size: Tuple[int, int], glyphs: List[Dict[str, Any]], telop: Dict[str, Any]) -> Image.Image:
    """テロップ装飾（光 → 立体影 → 縁取り → グラデ塗り → 傾き）をかけた文字レイヤーを作る。"""
    w, h = size
    fill_m = Image.new("L", size, 0)
    outer_m = Image.new("L", size, 0)
    d_fill = ImageDraw.Draw(fill_m)
    d_outer = ImageDraw.Draw(outer_m)
    grad = Image.new("RGBA", size, (0, 0, 0, 0))
    d_grad = ImageDraw.Draw(grad)
    ext_masks: Dict[int, Image.Image] = {}
    lines_done = set()
    glow_r = 0
    c1, c2 = telop["fill"][0], telop["fill"][1]

    for g in glyphs:
        _put_glyph(fill_m, d_fill, g, 0)
        _put_glyph(outer_m, d_outer, g, g["sw"])
        glow_r = max(glow_r, g["glow"])
        if g["ext"] > 0:
            m = ext_masks.get(g["ext"])
            if m is None:
                m = Image.new("L", size, 0)
                ext_masks[g["ext"]] = m
            _put_glyph(m, ImageDraw.Draw(m), g, g["sw"])
        ly = g["line_y"]
        if ly not in lines_done:
            lines_done.add(ly)
            y0, y1 = ly
            span = max(1, y1 - y0)
            margin = int(span * 0.15) + 2
            for yy in range(max(0, y0 - margin), min(h, y1 + margin + 1)):
                t = min(1.0, max(0.0, (yy - y0) / span))
                d_grad.line((0, yy, w, yy), fill=_lerp_rgb(c1, c2, t) + (255,))

    out = Image.new("RGBA", size, (0, 0, 0, 0))

    if glow_r > 0:
        gain = float(telop.get("glow_gain", 2.2))
        gm = outer_m.filter(ImageFilter.GaussianBlur(glow_r)).point(lambda a: min(255, int(a * gain)))
        glow = Image.new("RGBA", size, tuple(telop["glow_color"]) + (255,))
        glow.putalpha(gm)
        out.alpha_composite(glow)

    dx, dy = telop.get("extrude_dir", [1, 1])
    for depth, m in ext_masks.items():
        ext_layer = Image.new("RGBA", size, tuple(telop["extrude_color"]) + (255,))
        ext_layer.putalpha(m)
        for d in range(depth, 0, -1):
            out.alpha_composite(ext_layer, (dx * d, dy * d))

    outline = Image.new("RGBA", size, tuple(telop["outline_color"]) + (255,))
    outline.putalpha(outer_m)
    out.alpha_composite(outline)

    grad.putalpha(fill_m)
    out.alpha_composite(grad)

    k = float(telop.get("skew", 0))
    if k:
        out = out.transform(size, Image.AFFINE, (1, k, -k * h / 2.0, 0, 1, 0), resample=Image.BICUBIC)
    return out


def _fallback_telop(palette: Dict[str, Any], stroke_w: int) -> Dict[str, Any]:
    """テロップ装飾が無いDNA用の、素直な文字（縁取りだけ）の設定。"""
    text_c = list(palette["text"][:3])
    return {
        "id": "plain", "label": "標準",
        "fill": [text_c, text_c],
        "outline_color": list(palette["stroke"][:3]),
        "outline_ratio": 0.0,
        "extrude_ratio": 0.0, "glow_ratio": 0.0, "skew": 0.0,
    }


def _char_shadow(img: Image.Image, opacity: float, blur: int, dx: int, dy: int) -> Image.Image:
    if opacity <= 0:
        return img
    w, h = img.size
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    alpha_ch = img.getchannel("A").point(lambda a: int(a * opacity))
    fill = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    fill.putalpha(alpha_ch)
    if blur > 0:
        fill = fill.filter(ImageFilter.GaussianBlur(max(1, blur // 2)))
    shadow.alpha_composite(fill, (dx, dy))
    shadow.alpha_composite(img)
    return shadow


def _build_vertical_text_block_sprite(
    headline: str,
    sublines: List[str],
    dna: Dict[str, Any],
    is_hook: bool,
    zone: str,
) -> Dict[str, Any]:
    """縦書きのテロップブロックを作る。列は右から左へ、文字は上から下へ並ぶ。"""
    font_path = dna["font_path"]
    font_weight = dna.get("font_weight")
    palette = dna["palette"]
    align = dna["align"]
    letter_spacing = int(dna["letter_spacing"])
    line_spacing = float(dna["line_spacing"])
    stroke_w = int(dna["stroke_width"])
    shadow_blur = int(dna["shadow_blur"])
    shadow_opacity = float(dna["shadow_opacity"])
    sdx, sdy = dna["shadow_offset"]
    decoration = dna["decoration"]
    telop = dna.get("telop")
    # 斜体は縦書きでは不自然なので外す
    telop = dict(telop, skew=0) if telop else _fallback_telop(palette, stroke_w)

    base_size = int(dna["hook_size"] if is_hook else dna["body_size"])
    max_col_h = TARGET_H - SAFE_TOP - SAFE_BOTTOM - 120
    max_block_w = TARGET_W - SAFE_LEFT - SAFE_RIGHT - 60
    cap_chars = 10 if is_hook else 12

    head_txt = to_vertical_text(headline)
    sub_txts = [t for t in (to_vertical_text(x) for x in sublines) if t][:3]

    def adv_of(sz: int) -> int:      # 1文字ぶんの縦の送り
        return int(sz * 1.04) + letter_spacing

    def colw_of(sz: int) -> int:     # 1列の幅
        return int(sz * 1.14)

    def gap_of(sz: int) -> int:      # 列と列の間
        return max(12, int(sz * (line_spacing - 1.0) + sz * 0.1))

    # 列が横幅に収まる大きさまで、少しずつ小さくする
    size = base_size
    while True:
        sub_size = max(30, int(size * 0.56))
        per_col = max(3, min(cap_chars, max_col_h // adv_of(size)))
        sub_per = max(3, min(cap_chars + 2, (max_col_h - int(size * 0.6)) // adv_of(sub_size)))
        cols: List[Dict[str, Any]] = [
            {"text": t, "size": size, "y_off": 0} for t in wrap_vertical(head_txt, per_col)
        ]
        sub_cols: List[str] = []
        for t in sub_txts:
            sub_cols.extend(wrap_vertical(t, sub_per))
        cols += [{"text": t, "size": sub_size, "y_off": int(size * 0.7)} for t in sub_cols[:4]]
        if not cols:
            cols = [{"text": "　", "size": size, "y_off": 0}]
        total_w = sum(colw_of(c["size"]) for c in cols) + sum(gap_of(c["size"]) for c in cols[:-1])
        if total_w <= max_block_w or size <= 40:
            break
        size -= 4

    for c in cols:
        c["font"] = load_font(font_path, c["size"], font_weight)

    pad_x = 34 if decoration in ("pill_bg", "frosted_card", "box_outline", "corner_brackets") else 24
    pad_y = 26 if decoration in ("pill_bg", "frosted_card", "box_outline", "corner_brackets") else 20
    extra_left = 18 if decoration == "left_accent_bar" else 0

    block_h = max(c["y_off"] + len(c["text"]) * adv_of(c["size"]) for c in cols) + 20
    shadow_pad = max(16, shadow_blur * 2 + max(abs(sdx), abs(sdy)) + stroke_w + 4)
    shadow_pad = max(shadow_pad, _telop_pad(telop, size, block_h + pad_y * 2))

    box_w = total_w + pad_x * 2 + extra_left + 20
    box_h = block_h + pad_y * 2
    sprite_w = box_w + shadow_pad * 2
    sprite_h = box_h + shadow_pad * 2

    if align == "left":
        block_x = SAFE_LEFT - shadow_pad
    elif align == "right":
        block_x = TARGET_W - SAFE_RIGHT - box_w - shadow_pad
    else:
        block_x = (TARGET_W - sprite_w) // 2

    if zone == "top":
        block_y = SAFE_TOP + 60 - shadow_pad
    elif zone == "center":
        block_y = (TARGET_H - sprite_h) // 2 - 40
    else:
        block_y = TARGET_H - SAFE_BOTTOM - box_h - 40 - shadow_pad
    block_y = max(0, min(block_y, TARGET_H - sprite_h))

    content_left = shadow_pad + pad_x + extra_left + 10
    top_y = shadow_pad + pad_y
    block_top, block_bottom = shadow_pad, shadow_pad + box_h   # グラデーションは全体で1つ

    glyphs: List[Dict[str, Any]] = []
    char_items: List[Dict[str, Any]] = []
    cursor = content_left + total_w
    for col in cols:
        sz = col["size"]
        cw_, adv, font = colw_of(sz), adv_of(sz), col["font"]
        cell_left = cursor - cw_
        cx_center = cell_left + cw_ / 2.0
        rec = {"font": font, "size": sz}
        for i, ch in enumerate(col["text"]):
            if ch in ("　", " "):
                continue
            cell_top = top_y + col["y_off"] + i * adv
            cy_center = cell_top + adv / 2.0
            kind = glyph_kind(ch)
            dx = dy = 0.0
            if kind == "punct":      # 句読点は右上へ
                dx, dy = sz * 0.50, -sz * 0.60
            elif kind == "small":    # 小書きのかなは少しだけ右上へ
                dx, dy = sz * 0.08, -sz * 0.08

            g = _telop_glyph((cx_center + dx, cy_center + dy), ch, rec, telop, block_top, block_bottom)
            g["anchor"], g["rot"] = "mm", kind == "rotate"
            glyphs.append(g)

            # 1文字ずつ登場させるアニメ用の画像
            c_pad = shadow_pad
            c_w, c_h = int(cw_) + c_pad * 2, int(adv) + c_pad * 2
            off = cell_top - block_top
            gl = _telop_glyph(
                (c_pad + cw_ / 2.0 + dx, c_pad + adv / 2.0 + dy), ch, rec, telop,
                c_pad - off, c_pad - off + (block_bottom - block_top),
            )
            gl["anchor"], gl["rot"] = "mm", kind == "rotate"
            c_img = _char_shadow(
                _compose_telop((c_w, c_h), [gl], telop), shadow_opacity, shadow_blur, sdx, sdy
            )
            char_items.append({
                "sprite": c_img,
                "x": int(cell_left) - c_pad,
                "y": int(cell_top) - c_pad,
                "right_x": int(cell_left + cw_),
                "top_y": int(cell_top),
                "h": int(adv),
                "cell": (int(cell_left), int(cell_top), int(cell_left + cw_), int(cell_top + adv)),
            })
        cursor -= cw_ + gap_of(sz)

    text_layer = _compose_telop((sprite_w, sprite_h), glyphs, telop)
    full_sprite = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 0))
    if shadow_opacity > 0:
        alpha_mask = text_layer.getchannel("A").point(lambda a: int(a * shadow_opacity))
        sh_img = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 255))
        sh_img.putalpha(alpha_mask)
        if shadow_blur > 0:
            sh_img = sh_img.filter(ImageFilter.GaussianBlur(shadow_blur))
        full_sprite.alpha_composite(sh_img, (sdx, sdy))
    full_sprite.alpha_composite(text_layer)

    return {
        "full_sprite": full_sprite,
        "char_items": char_items,
        "pos": (block_x, block_y),
        "box_rect": (shadow_pad, shadow_pad, shadow_pad + box_w, shadow_pad + box_h),
        "sprite_size": (sprite_w, sprite_h),
        "decoration": decoration,
        "palette": palette,
        "vertical": True,
    }


def _build_text_block_sprite(
    headline: str,
    sublines: List[str],
    dna: Dict[str, Any],
    is_hook: bool,
    zone: str,
) -> Dict[str, Any]:
    if dna.get("writing_mode") == "vertical":
        return _build_vertical_text_block_sprite(headline, sublines, dna, is_hook, zone)

    max_content_w = TARGET_W - SAFE_LEFT - SAFE_RIGHT - 48
    font_path = dna["font_path"]
    palette = dna["palette"]
    align = dna["align"]
    letter_spacing = int(dna["letter_spacing"])
    line_spacing = float(dna["line_spacing"])
    stroke_w = int(dna["stroke_width"])
    shadow_blur = int(dna["shadow_blur"])
    shadow_opacity = float(dna["shadow_opacity"])
    sdx, sdy = dna["shadow_offset"]
    decoration = dna["decoration"]

    base_size = int(dna["hook_size"] if is_hook else dna["body_size"])
    sub_size = max(32, int(base_size * 0.56))

    head_lines: List[str] = []
    font_weight = dna.get("font_weight")
    head_font = load_font(font_path, base_size, font_weight)
    for size_try in range(base_size, 36, -4):
        head_font = load_font(font_path, size_try, font_weight)
        head_lines = _wrap_japanese(headline, head_font, max_content_w, letter_spacing)
        if len(head_lines) <= 3:
            base_size = size_try
            break

    sub_font = load_font(font_path, sub_size, font_weight)
    wrapped_subs: List[str] = []
    for sl in sublines:
        wrapped_subs.extend(_wrap_japanese(sl, sub_font, max_content_w, max(0, letter_spacing - 1)))
    wrapped_subs = wrapped_subs[:4]

    line_records: List[Dict[str, Any]] = []
    for ln in head_lines:
        w = _measure_line(ln, head_font, letter_spacing)
        line_records.append({
            "text": ln,
            "font": head_font,
            "size": base_size,
            "w": w,
            "h": int(base_size * 1.12),
            "color": tuple(palette["text"]),
            "spacing": letter_spacing,
        })
    for ln in wrapped_subs:
        w = _measure_line(ln, sub_font, max(0, letter_spacing - 1))
        line_records.append({
            "text": ln,
            "font": sub_font,
            "size": sub_size,
            "w": w,
            "h": int(sub_size * 1.15),
            "color": tuple(palette["accent"]) if is_hook else tuple(palette["text"]),
            "spacing": max(0, letter_spacing - 1),
        })

    if not line_records:
        line_records.append({
            "text": " ",
            "font": head_font,
            "size": base_size,
            "w": 10,
            "h": base_size,
            "color": tuple(palette["text"]),
            "spacing": 0,
        })

    content_w = int(max(r["w"] for r in line_records)) + 20
    total_h = 0
    for idx, r in enumerate(line_records):
        gap = int(r["h"] * (line_spacing - 1.0)) if idx < len(line_records) - 1 else 0
        if idx == len(head_lines) - 1 and wrapped_subs:
            gap += 14
        r["y_rel"] = total_h
        total_h += r["h"] + gap

    pad_x = 34 if decoration in ("pill_bg", "frosted_card", "box_outline", "corner_brackets") else 24
    pad_y = 26 if decoration in ("pill_bg", "frosted_card", "box_outline", "corner_brackets") else 20
    extra_left = 18 if decoration == "left_accent_bar" else 0
    shadow_pad = max(16, shadow_blur * 2 + max(abs(sdx), abs(sdy)) + stroke_w + 4)
    telop = dna.get("telop")
    if telop:
        shadow_pad = max(shadow_pad, _telop_pad(telop, base_size, total_h + pad_y * 2))

    box_w = content_w + pad_x * 2 + extra_left
    box_h = total_h + pad_y * 2
    sprite_w = box_w + shadow_pad * 2
    sprite_h = box_h + shadow_pad * 2

    if align == "left":
        block_x = SAFE_LEFT - shadow_pad
    elif align == "right":
        block_x = TARGET_W - SAFE_RIGHT - box_w - shadow_pad
    else:
        block_x = (TARGET_W - sprite_w) // 2

    if zone == "top":
        block_y = SAFE_TOP + 60 - shadow_pad
    elif zone == "center":
        block_y = (TARGET_H - sprite_h) // 2 - 40
    else:
        block_y = TARGET_H - SAFE_BOTTOM - box_h - 40 - shadow_pad

    text_layer = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 0))
    draw_t = ImageDraw.Draw(text_layer)

    char_items: List[Dict[str, Any]] = []
    telop_glyphs: List[Dict[str, Any]] = []
    stroke_col = tuple(palette["stroke"]) + (255,)

    for rec in line_records:
        line_w = rec["w"]
        if align == "center":
            start_x = shadow_pad + pad_x + extra_left + (content_w - line_w) / 2.0
        elif align == "right":
            start_x = shadow_pad + pad_x + extra_left + (content_w - line_w)
        else:
            start_x = shadow_pad + pad_x + extra_left

        cy = shadow_pad + pad_y + rec["y_rel"]
        cx = start_x
        fill_col = rec["color"] + (255,)

        for ch in rec["text"]:
            cw = rec["font"].getlength(ch)
            if telop:
                telop_glyphs.append(_telop_glyph((cx, cy), ch, rec, telop, cy, cy + rec["h"]))
            else:
                draw_t.text(
                    (cx, cy), ch, font=rec["font"], fill=fill_col,
                    stroke_width=stroke_w, stroke_fill=stroke_col if stroke_w > 0 else None,
                )
            c_pad = shadow_pad
            c_w = max(8, int(math.ceil(cw)) + c_pad * 2)
            c_h = int(rec["h"]) + c_pad * 2
            c_img = Image.new("RGBA", (c_w, c_h), (0, 0, 0, 0))
            c_draw = ImageDraw.Draw(c_img)
            if telop:
                c_img = _compose_telop(
                    (c_w, c_h),
                    [_telop_glyph((c_pad, c_pad), ch, rec, telop, c_pad, c_pad + rec["h"])],
                    telop,
                )
            else:
                c_draw.text(
                    (c_pad, c_pad), ch, font=rec["font"], fill=fill_col,
                    stroke_width=stroke_w, stroke_fill=stroke_col if stroke_w > 0 else None,
                )
            if shadow_opacity > 0:
                c_shadow = Image.new("RGBA", (c_w, c_h), (0, 0, 0, 0))
                alpha_ch = c_img.getchannel("A").point(lambda a: int(a * shadow_opacity))
                sh_fill = Image.new("RGBA", (c_w, c_h), (0, 0, 0, 255))
                sh_fill.putalpha(alpha_ch)
                if shadow_blur > 0:
                    sh_fill = sh_fill.filter(ImageFilter.GaussianBlur(max(1, shadow_blur // 2)))
                c_shadow.alpha_composite(sh_fill, (sdx, sdy))
                c_shadow.alpha_composite(c_img)
                c_img = c_shadow

            char_items.append({
                "sprite": c_img,
                "x": int(cx) - c_pad,
                "y": int(cy) - c_pad,
                "right_x": int(cx + cw),
                "top_y": int(cy),
                "h": int(rec["h"]),
            })
            cx += cw + rec["spacing"]

    if telop:
        text_layer = _compose_telop((sprite_w, sprite_h), telop_glyphs, telop)

    full_sprite = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 0))
    if shadow_opacity > 0:
        alpha_mask = text_layer.getchannel("A").point(lambda a: int(a * shadow_opacity))
        sh_img = Image.new("RGBA", (sprite_w, sprite_h), (0, 0, 0, 255))
        sh_img.putalpha(alpha_mask)
        if shadow_blur > 0:
            sh_img = sh_img.filter(ImageFilter.GaussianBlur(shadow_blur))
        full_sprite.alpha_composite(sh_img, (sdx, sdy))
    full_sprite.alpha_composite(text_layer)

    return {
        "full_sprite": full_sprite,
        "char_items": char_items,
        "pos": (block_x, block_y),
        "box_rect": (shadow_pad, shadow_pad, shadow_pad + box_w, shadow_pad + box_h),
        "sprite_size": (sprite_w, sprite_h),
        "decoration": decoration,
        "palette": palette,
    }


def _draw_decoration_layer(
    sprite_size: Tuple[int, int],
    box_rect: Tuple[int, int, int, int],
    decoration: str,
    palette: Dict[str, Any],
    progress: float,
) -> Image.Image:
    w, h = sprite_size
    x0, y0, x1, y1 = box_rect
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    accent = tuple(palette["accent"]) + (245,)
    badge_bg = tuple(palette["badge_bg"])
    p = _ease_out_cubic(progress)

    if decoration == "pill_bg":
        cur_x1 = int(x0 + (x1 - x0) * p)
        if cur_x1 > x0 + 20:
            draw.rounded_rectangle((x0, y0, cur_x1, y1), radius=24, fill=badge_bg)
            draw.rounded_rectangle((x0, y0, cur_x1, y1), radius=24, outline=accent, width=2)
    elif decoration == "frosted_card":
        alpha = int(badge_bg[3] * p)
        fill_c = (badge_bg[0], badge_bg[1], badge_bg[2], alpha)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=16, fill=fill_c)
        draw.line((x0 + 16, y0 + 2, x0 + 16 + int((x1 - x0 - 32) * p), y0 + 2), fill=accent, width=4)
    elif decoration == "left_accent_bar":
        bar_h = int((y1 - y0) * p)
        draw.rounded_rectangle((x0 + 2, y0, x0 + 11, y0 + bar_h), radius=4, fill=accent)
    elif decoration == "underline_sweep":
        uy = y1 - 4
        draw.line((x0 + 12, uy, x0 + 12 + int((x1 - x0 - 24) * p), uy), fill=accent, width=5)
    elif decoration == "box_outline":
        cur_x1 = int(x0 + (x1 - x0) * p)
        draw.rectangle((x0, y0, cur_x1, y1), outline=accent, width=3)
    elif decoration == "corner_brackets":
        arm = int(28 * p)
        lw = 4
        draw.line((x0, y0, x0 + arm, y0), fill=accent, width=lw)
        draw.line((x0, y0, x0, y0 + arm), fill=accent, width=lw)
        draw.line((x1 - arm, y1, x1, y1), fill=accent, width=lw)
        draw.line((x1, y1 - arm, x1, y1), fill=accent, width=lw)
    elif decoration == "v_rule_pair":
        # 縦書き向け: 左右に縦の細線が上から伸びる
        cur_y = int(y0 + (y1 - y0) * p)
        draw.line((x0 + 6, y0, x0 + 6, cur_y), fill=accent, width=3)
        draw.line((x1 - 6, y0, x1 - 6, cur_y), fill=accent, width=3)
    elif decoration == "v_side_rule":
        # 縦書き向け: 右側に1本の縦線、上端に小さな丸（書の落款のような飾り）
        cur_y = int(y0 + (y1 - y0) * p)
        draw.line((x1 - 8, y0 + 12, x1 - 8, cur_y), fill=accent, width=3)
        if p > 0.15:
            draw.ellipse((x1 - 14, y0 + 2, x1 - 2, y0 + 14), fill=accent)
    elif decoration == "double_line":
        span = int(((x1 - x0) * 0.5) * p)
        mid = (x0 + x1) // 2
        draw.line((mid - span, y0, mid + span, y0), fill=accent, width=3)
        draw.line((mid - span, y1, mid + span, y1), fill=accent, width=3)

    return layer


def _build_scrim_canvas(dna: Dict[str, Any]) -> Image.Image:
    sc = dna["palette"]["scrim"]
    strength = float(dna["scrim_strength"])
    grad = Image.new("RGBA", (1, TARGET_H), (0, 0, 0, 0))
    px = grad.load()
    for y in range(TARGET_H):
        ny = y / TARGET_H
        a = 0.14 * strength
        if ny < 0.30:
            a += (0.30 - ny) / 0.30 * (0.45 * strength)
        if ny > 0.45:
            a += ((ny - 0.45) / 0.55) ** 1.3 * (0.75 * strength)
        alpha = max(0, min(215, int(a * 255)))
        px[0, y] = (sc[0], sc[1], sc[2], alpha)
    return grad.resize((TARGET_W, TARGET_H), Image.Resampling.NEAREST)


def _apply_alpha(img: Image.Image, alpha_factor: float) -> Image.Image:
    if alpha_factor >= 0.999:
        return img
    if alpha_factor <= 0.001:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    out = img.copy()
    a = out.getchannel("A").point(lambda v: int(v * alpha_factor))
    out.putalpha(a)
    return out


def _render_element_to_frame(
    frame: Image.Image,
    elem: Dict[str, Any],
    t_local: float,
    dur: float,
    anim_in: str,
    anim_dur: float,
    slide_dir: str,
) -> None:
    if t_local < 0 or t_local > dur:
        return

    out_dur = min(0.28, dur * 0.25)
    p_in = _clamp01(t_local / max(0.2, anim_dur))
    p_out = _clamp01((dur - t_local) / max(0.1, out_dur))

    bx, by = elem["pos"]
    sw, sh = elem["sprite_size"]
    full_sprite: Image.Image = elem["full_sprite"]
    deco_type = elem["decoration"]

    if deco_type != "none":
        deco_prog = p_in if anim_in != "clip_expand" else _clamp01(p_in / 0.55)
        deco_layer = _draw_decoration_layer(
            elem["sprite_size"], elem["box_rect"], deco_type, elem["palette"], deco_prog
        )
        if p_out < 1.0:
            deco_layer = _apply_alpha(deco_layer, p_out)
        frame.alpha_composite(deco_layer, (bx, by))

    if anim_in in ("char_reveal", "typing"):
        chars = elem["char_items"]
        n = len(chars)
        if n == 0:
            return
        reveal_span = max(0.25, anim_dur * 1.15)
        char_t = _clamp01(t_local / reveal_span)

        if anim_in == "typing":
            visible_count = int(math.ceil(char_t * n))
            for idx in range(min(n, visible_count)):
                ci = chars[idx]
                sp = _apply_alpha(ci["sprite"], p_out)
                frame.alpha_composite(sp, (bx + ci["x"], by + ci["y"]))
            if t_local < reveal_span + 0.45 and int(t_local * 6) % 2 == 0 and visible_count > 0:
                last_c = chars[min(n - 1, visible_count - 1)]
                draw = ImageDraw.Draw(frame)
                col = tuple(elem["palette"]["accent"]) + (int(240 * p_out),)
                if elem.get("vertical"):
                    # 縦書き: 打ったばかりの文字の下に、横棒のカーソル
                    cx0, _cy0, cx1, cy1 = last_c["cell"]
                    draw.rectangle((bx + cx0 + 8, by + cy1 + 2, bx + cx1 - 8, by + cy1 + 7), fill=col)
                else:
                    cur_x = bx + last_c["right_x"] + 4
                    cur_y0 = by + last_c["top_y"] + 4
                    cur_y1 = cur_y0 + last_c["h"] - 8
                    draw.rectangle((cur_x, cur_y0, cur_x + 5, cur_y1), fill=col)
        else:
            stagger = 0.55 / max(1, n)
            for idx, ci in enumerate(chars):
                cp = _clamp01((char_t - idx * stagger) / 0.45)
                if cp <= 0:
                    continue
                ce = _ease_out_cubic(cp)
                dy = int((1.0 - ce) * 18)
                sp = _apply_alpha(ci["sprite"], ce * p_out)
                frame.alpha_composite(sp, (bx + ci["x"], by + ci["y"] + dy))
        return

    sprite_to_draw = full_sprite
    draw_x, draw_y = bx, by
    alpha = p_out

    if anim_in == "fade_in":
        e = _ease_out_cubic(p_in)
        alpha *= e
        scale = 0.96 + 0.04 * e
        if scale < 0.999:
            nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
            sprite_to_draw = full_sprite.resize((nw, nh), Image.Resampling.BILINEAR)
            draw_x += (sw - nw) // 2
            draw_y += (sh - nh) // 2

    elif anim_in == "slide_in":
        e = _ease_out_expo(p_in)
        alpha *= _clamp01(p_in / 0.55)
        dist = 72
        off = int(dist * (1.0 - e))
        if slide_dir == "up":
            draw_y += off
        elif slide_dir == "down":
            draw_y -= off
        elif slide_dir == "left":
            draw_x += off
        else:
            draw_x -= off

    elif anim_in == "zoom_in":
        e = _ease_out_cubic(p_in)
        alpha *= _clamp01(p_in / 0.5)
        scale = 0.74 + 0.26 * e
        nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
        sprite_to_draw = full_sprite.resize((nw, nh), Image.Resampling.BILINEAR)
        draw_x += (sw - nw) // 2
        draw_y += (sh - nh) // 2

    elif anim_in == "popup":
        e = _ease_out_back(p_in)
        alpha *= _clamp01(p_in / 0.4)
        scale = max(0.1, 0.80 + 0.20 * e)
        nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
        sprite_to_draw = full_sprite.resize((nw, nh), Image.Resampling.BILINEAR)
        draw_x += (sw - nw) // 2
        draw_y += (sh - nh) // 2

    elif anim_in == "blur_in":
        e = _ease_out_cubic(p_in)
        alpha *= e
        blur_r = int(round(14 * (1.0 - e)))
        if blur_r > 0:
            sprite_to_draw = full_sprite.filter(ImageFilter.GaussianBlur(blur_r))

    elif anim_in == "mask_wipe" and elem.get("vertical"):
        # 縦書き: 上から下へ文字が現れる（読む向きに合わせる）
        e = _ease_out_expo(p_in)
        vis_h = max(1, int(sh * e))
        cropped = full_sprite.crop((0, 0, sw, vis_h))
        if alpha < 0.999:
            cropped = _apply_alpha(cropped, alpha)
        frame.alpha_composite(cropped, (bx, by))
        if 0.03 < p_in < 0.95:
            draw = ImageDraw.Draw(frame)
            x0, y0, x1, y1 = elem["box_rect"]
            bar_y = by + vis_h
            col = tuple(elem["palette"]["accent"]) + (230,)
            draw.rectangle((bx + x0, bar_y - 3, bx + x1, bar_y + 2), fill=col)
        return

    elif anim_in == "mask_wipe":
        e = _ease_out_expo(p_in)
        vis_w = max(1, int(sw * e))
        cropped = full_sprite.crop((0, 0, vis_w, sh))
        if alpha < 0.999:
            cropped = _apply_alpha(cropped, alpha)
        frame.alpha_composite(cropped, (bx, by))
        if 0.03 < p_in < 0.95:
            draw = ImageDraw.Draw(frame)
            x0, y0, x1, y1 = elem["box_rect"]
            bar_x = bx + vis_w
            col = tuple(elem["palette"]["accent"]) + (230,)
            draw.rectangle((bar_x - 3, by + y0, bar_x + 2, by + y1), fill=col)
        return

    elif anim_in == "split_reveal" and elem.get("vertical"):
        # 縦書き: 左右に分けた半分が、上下からずれて合わさる
        e = _ease_out_expo(p_in)
        alpha *= _clamp01(p_in / 0.5)
        mid_x = sw // 2
        off = int(38 * (1.0 - e))
        left_half = _apply_alpha(full_sprite.crop((0, 0, mid_x, sh)), alpha)
        right_half = _apply_alpha(full_sprite.crop((mid_x, 0, sw, sh)), alpha)
        frame.alpha_composite(left_half, (bx, by - off))
        frame.alpha_composite(right_half, (bx + mid_x, by + off))
        return

    elif anim_in == "split_reveal":
        e = _ease_out_expo(p_in)
        alpha *= _clamp01(p_in / 0.5)
        mid_y = sh // 2
        off = int(38 * (1.0 - e))
        top_half = _apply_alpha(full_sprite.crop((0, 0, sw, mid_y)), alpha)
        bot_half = _apply_alpha(full_sprite.crop((0, mid_y, sw, sh)), alpha)
        frame.alpha_composite(top_half, (bx - off, by))
        frame.alpha_composite(bot_half, (bx + off, by + mid_y))
        return

    elif anim_in == "clip_expand" and elem.get("vertical"):
        # 縦書き: 中央から左右へ開く
        text_p = _clamp01((p_in - 0.25) / 0.75)
        e = _ease_out_cubic(text_p)
        if e <= 0.01:
            return
        vis_w = max(1, int(sw * e))
        x_left = (sw - vis_w) // 2
        cropped = _apply_alpha(full_sprite.crop((x_left, 0, x_left + vis_w, sh)), alpha * e)
        frame.alpha_composite(cropped, (bx + x_left, by))
        return

    elif anim_in == "clip_expand":
        text_p = _clamp01((p_in - 0.25) / 0.75)
        e = _ease_out_cubic(text_p)
        if e <= 0.01:
            return
        vis_h = max(1, int(sh * e))
        y_top = (sh - vis_h) // 2
        cropped = _apply_alpha(full_sprite.crop((0, y_top, sw, y_top + vis_h)), alpha * e)
        frame.alpha_composite(cropped, (bx, by + y_top))
        return

    sprite_to_draw = _apply_alpha(sprite_to_draw, alpha)
    frame.alpha_composite(sprite_to_draw, (draw_x, draw_y))


def _camera_zoompan_filter(motion: str, frames: int) -> str:
    frames = max(15, frames)
    if motion == "zoom_in_punch":
        z_expr = f"1.0+0.18*pow(on/{frames},0.6)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "zoom_in_slow":
        z_expr = f"1.0+0.11*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out_reveal":
        z_expr = f"1.14-0.14*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":
        z_expr = "1.12"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right":
        z_expr = "1.12"
        x_expr = f"(iw-iw/zoom)*(on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        return (
            f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H},setsar=1,"
            f"loop=loop={frames - 1}:size=1:start=0,fps={FPS},format=yuv420p"
        )

    return (
        f"scale=1620:2880:force_original_aspect_ratio=increase,"
        f"crop=1620:2880,setsar=1,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={TARGET_W}x{TARGET_H}:fps={FPS},"
        f"format=yuv420p"
    )


def render_video_from_dna(
    dna: Dict[str, Any],
    assets: List[Dict[str, Any]],
    output_mp4_path: str,
    thumb_jpg_path: str,
) -> Tuple[float, float]:
    if not assets:
        raise ValueError("使用する画像・動画素材が1つも選択されていません。")

    Path(output_mp4_path).parent.mkdir(parents=True, exist_ok=True)
    Path(thumb_jpg_path).parent.mkdir(parents=True, exist_ok=True)

    narrative = dna["narrative"]
    scenes = narrative["scenes"]
    trans_dur = float(narrative["transition_duration"])
    total_dur = float(narrative["total_duration"])
    hook_dur = float(narrative["hook_duration"])
    total_frames = max(30, int(round(total_dur * FPS)))

    ffmpeg = find_ffmpeg()

    cmd: List[str] = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats"]
    filter_parts: List[str] = []
    seg_labels: List[str] = []

    for i, sc in enumerate(scenes):
        asset = assets[i % len(assets)]
        seg_dur = float(sc["duration"])
        seg_frames = max(15, int(round(seg_dur * FPS)))
        cam = dna["hook_camera"] if i == 0 else dna["body_cameras"][(i - 1) % len(dna["body_cameras"])]

        if asset["media_type"] == "image":
            cmd.extend(["-i", asset["file_path"]])
            flt = _camera_zoompan_filter(cam, seg_frames)
            filter_parts.append(f"[{i}:v]{flt}[s{i}]")
        else:
            cmd.extend(["-stream_loop", "-1", "-i", asset["file_path"]])
            filter_parts.append(
                f"[{i}:v]trim=start=0:duration={seg_dur:.3f},setpts=PTS-STARTPTS,"
                f"fps={FPS},scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_W}:{TARGET_H},setsar=1,format=yuv420p[s{i}]"
            )
        seg_labels.append(f"[s{i}]")

    overlay_input_idx = len(scenes)
    cmd.extend([
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{TARGET_W}x{TARGET_H}", "-r", str(FPS), "-i", "pipe:0",
    ])

    if len(seg_labels) == 1:
        bg_label = seg_labels[0]
    else:
        cur_label = seg_labels[0]
        cum_dur = float(scenes[0]["duration"])
        trans_name = dna["transition"]
        for i in range(1, len(seg_labels)):
            offset = max(0.1, cum_dur - trans_dur)
            out_lbl = f"[bg{i}]"
            filter_parts.append(
                f"{cur_label}{seg_labels[i]}xfade=transition={trans_name}:duration={trans_dur:.3f}:offset={offset:.3f}{out_lbl}"
            )
            cur_label = out_lbl
            cum_dur = cum_dur + float(scenes[i]["duration"]) - trans_dur
        bg_label = cur_label

    filter_parts.append(f"{bg_label}[{overlay_input_idx}:v]overlay=0:0:shortest=1[vout]")
    filter_complex = ";".join(filter_parts)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output_mp4_path,
    ])

    scrim_canvas = _build_scrim_canvas(dna)
    scene_renders: List[Dict[str, Any]] = []
    cur_t = 0.0
    for i, sc in enumerate(scenes):
        is_hook = sc["role"] == "hook"
        dur = float(sc["duration"])
        t_start = cur_t if i == 0 else cur_t - trans_dur * 0.4
        t_end = cur_t + dur - (trans_dur * 0.5 if i < len(scenes) - 1 else 0.0)
        zone = dna["hook_zone"] if is_hook else dna["body_zone"]
        elem = _build_text_block_sprite(
            sc["headline"], sc.get("sublines", []), dna, is_hook=is_hook, zone=zone
        )
        scene_renders.append({
            "t_start": t_start,
            "t_end": t_end,
            "elem": elem,
            "anim_in": dna["hook_animation"] if is_hook else dna["body_animation"],
        })
        cur_t += dur - (trans_dur if i < len(scenes) - 1 else 0.0)

    # ffmpeg の出力はパイプに溜めず、ファイルへ逃がす。
    # パイプのまま読まずに放置すると、容量がいっぱいになった時点で ffmpeg が止まり、
    # 動画生成が永遠に終わらなくなる（特にWindowsはパイプ容量が小さい）ため。
    err_file = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_file)

    assert proc.stdin is not None
    try:
        for f_idx in range(total_frames):
            t = f_idx / float(FPS)
            frame = scrim_canvas.copy()
            for sr in scene_renders:
                if sr["t_start"] <= t <= sr["t_end"]:
                    _render_element_to_frame(
                        frame=frame, elem=sr["elem"],
                        t_local=t - sr["t_start"], dur=sr["t_end"] - sr["t_start"],
                        anim_in=sr["anim_in"], anim_dur=float(dna["anim_duration"]),
                        slide_dir=dna["slide_direction"],
                    )
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    except Exception:
        proc.kill()
        err_file.close()
        raise

    proc.wait()
    err_file.seek(0)
    err_text = err_file.read().decode("utf-8", errors="ignore")
    err_file.close()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg 動画生成エラー:\n{err_text[-1200:]}")

    thumb_t = min(0.85, total_dur * 0.4)
    subprocess.run(
        [
            ffmpeg, "-y", "-ss", f"{thumb_t:.2f}", "-i", output_mp4_path,
            "-vframes", "1", "-vf", "scale=420:-2", thumb_jpg_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    return total_dur, hook_dur