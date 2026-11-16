from typing import Optional

from PIL import ImageFont


def load_font(path: str, size: int, weight: Optional[int] = None) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。可変フォント(Google Fontsの [wght].ttf など)なら太さを指定する。

    静的フォントや、太さの軸がないフォントでは weight は無視される。
    """
    font = ImageFont.truetype(path, size)
    if weight:
        try:
            axes = font.get_variation_axes()
            values = []
            has_weight = False
            for ax in axes:
                name = ax.get("name", b"")
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "ignore")
                lo, hi, default = ax["minimum"], ax["maximum"], ax["default"]
                if str(name).lower() in ("weight", "wght"):
                    values.append(max(lo, min(hi, weight)))
                    has_weight = True
                else:
                    values.append(default)
            if has_weight:
                font.set_variation_by_axes(values)
        except Exception:
            pass  # 静的フォントなど。そのまま使う
    return font
