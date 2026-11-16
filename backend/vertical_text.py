"""縦書きテロップの文字処理（レイアウトに依存しない部分）。

- 数字は漢数字へ（580万円 → 五八〇万円）。縦書きでは算用数字が不自然なため
- 列の分割は、行頭禁則（、。」などを列の先頭に置かない）と行末禁則（「（を列の末尾に置かない）を守る
- 長音（ー）や括弧、～ は90度回転、句読点や小さい「っゃゅょ」は右上へ寄せる
"""
import math
import re
from typing import List

_KANJI_DIGITS = str.maketrans("0123456789０１２３４５６７８９", "〇一二三四五六七八九〇一二三四五六七八九")

# 縦書きでは時計回りに90度回す文字（長音・ダッシュ・波ダッシュ・括弧類）
ROTATE_CHARS = set("ー―－—–-〜～…⋯（）()「」『』【】［］[]〈〉《》｛｝{}<>＜＞=＝→←")
# 縦書きでは右上へ寄せる文字（句読点）
SHIFT_PUNCT = set("、。，．,.")
# 縦書きでは少し右上へ寄せる文字（小書きのかな）
SMALL_KANA = set("ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ")

# 行頭禁則: 列の先頭に置いてはいけない文字
NO_LINE_START = set("、。，．,.）」』】〕〉》｝)]}ゃゅょっぁぃぅぇぉゎャュョッァィゥェォヮー!?！？・:：;；…‥")
# 行末禁則: 列の末尾に置いてはいけない文字
NO_LINE_END = set("（「『【〔〈《｛([{")


def to_vertical_text(text: str) -> str:
    """横書き用の文字列を、縦書き向けに整える。"""
    s = (text or "").replace("\r\n", "\n").replace("\n", "")
    s = re.sub(r"(?<=[0-9０-９]),(?=[0-9０-９]{3})", "", s)      # 1,980 → 1980
    s = re.sub(r"(?<=[0-9０-９])[.．](?=[0-9０-９])", "・", s)    # 3.5 → 三・五
    s = s.translate(_KANJI_DIGITS)
    s = re.sub(r"[ \t]+", "　", s.strip())                       # 空白は全角1つぶんの間に
    return s


def glyph_kind(ch: str) -> str:
    """'rotate'（回転）/ 'punct'（句読点）/ 'small'（小書きかな）/ 'normal'。"""
    if ch in ROTATE_CHARS:
        return "rotate"
    if ch in SHIFT_PUNCT:
        return "punct"
    if ch in SMALL_KANA:
        return "small"
    return "normal"


def wrap_vertical(text: str, per_col: int) -> List[str]:
    """per_col 文字を上限に、できるだけ均等な長さの列へ分ける（禁則処理つき）。"""
    text = text or ""
    n = len(text)
    if n == 0:
        return []
    per_col = max(2, int(per_col))
    if n <= per_col:
        return [text]
    n_cols = math.ceil(n / per_col)
    target = math.ceil(n / n_cols)
    cols: List[str] = []
    i = 0
    while i < n:
        j = min(n, i + target)
        pushed = 0
        while j < n and text[j] in NO_LINE_START and pushed < 2:
            j += 1
            pushed += 1
        while j - i > 1 and text[j - 1] in NO_LINE_END:
            j -= 1
        cols.append(text[i:j])
        i = j
    return cols
