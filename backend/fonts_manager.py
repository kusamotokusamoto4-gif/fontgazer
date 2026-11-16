import io
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from .database import FONTS_DIR, get_conn, now_iso
from .fontutil import load_font

WINDOWS_SYSTEM_FONTS = [
    ("YuGothB.ttc", "游ゴシック Bold (標準)", "gothic", "Microsoft Windows標準搭載フォント", 1),
    ("YuGothM.ttc", "游ゴシック Medium (標準)", "gothic", "Microsoft Windows標準搭載フォント", 1),
    ("meiryob.ttc", "メイリオ Bold (標準)", "modern", "Microsoft Windows標準搭載フォント", 1),
    ("meiryo.ttc", "メイリオ Regular (標準)", "modern", "Microsoft Windows標準搭載フォント", 1),
    ("BIZ-UDGothicB.ttc", "BIZ UDゴシック Bold (標準)", "minimal", "MORISAWA BIZ UD (Windows標準)", 1),
    ("BIZ-UDMinchoM.ttc", "BIZ UD明朝 Medium (標準)", "mincho", "MORISAWA BIZ UD (Windows標準)", 1),
    ("msmincho.ttc", "MS 明朝 (標準)", "mincho", "Microsoft Windows標準搭載フォント", 1),
    ("msgothic.ttc", "MS ゴシック (標準)", "gothic", "Microsoft Windows標準搭載フォント", 1),
    ("UDDigiKyokashoN-B.ttc", "UDデジタル教科書体 Bold (標準)", "rounded", "Windows標準搭載フォント", 1),
    ("HGRGE.TTC", "HG創英角ゴシックUB (標準)", "display", "Office/Windows付属フォント(利用規約確認推奨)", 0),
    ("HGRPP1.TTC", "HG創英角ポップ体 (標準)", "pop", "Office/Windows付属フォント(利用規約確認推奨)", 0),
    ("HGRSKP.TTF", "HG正楷書体-PRO (標準)", "brush", "Office/Windows付属フォント(利用規約確認推奨)", 0),
]

FONT_CATEGORIES = [
    {"id": "gothic", "label": "ゴシック（力強い・汎用）"},
    {"id": "mincho", "label": "明朝（高級感・上品）"},
    {"id": "modern", "label": "モダン・スタイリッシュ"},
    {"id": "minimal", "label": "ミニマル・すっきり"},
    {"id": "rounded", "label": "丸文字・やさしい"},
    {"id": "pop", "label": "ポップ・明るい"},
    {"id": "display", "label": "見出し・インパクト"},
    {"id": "brush", "label": "筆・和風・古民家"},
]


def _guess_category(filename: str) -> str:
    low = filename.lower()
    if any(k in low for k in ("mincho", "serif", "shippori", "klee", "明朝")):
        return "mincho"
    if any(k in low for k in ("maru", "round", "zenmaru", "kyokasho", "丸")):
        return "rounded"
    if any(k in low for k in ("pop", "rock", "dela", "reggae", "ポップ")):
        return "pop"
    if any(k in low for k in ("brush", "fude", "kaisho", "gyosho", "毛筆", "楷書")):
        return "brush"
    if any(k in low for k in ("biz", "noto", "ud")):
        return "minimal"
    return "gothic"


def sync_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        existing_paths = {
            r["file_path"]: r["id"]
            for r in conn.execute("SELECT id, file_path FROM fonts").fetchall()
        }

        for fpath in sorted(FONTS_DIR.iterdir()):
            if fpath.suffix.lower() in (".ttf", ".otf", ".ttc") and fpath.is_file():
                s_path = str(fpath.resolve())
                if s_path not in existing_paths:
                    fid = "f_" + uuid.uuid4().hex[:10]
                    conn.execute(
                        """
                        INSERT INTO fonts (
                            id, display_name, file_path, source, category, enabled,
                            license_type, commercial_ok, license_notes, created_at
                        ) VALUES (?, ?, ?, 'custom', ?, 1, 'カスタム追加（ライセンス要記入）', 1, '', ?)
                        """,
                        (fid, fpath.stem, s_path, _guess_category(fpath.name), now_iso()),
                    )

        win_fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        if win_fonts_dir.exists():
            for fname, disp, cat, lic_type, comm_ok in WINDOWS_SYSTEM_FONTS:
                candidate = win_fonts_dir / fname
                if candidate.exists():
                    s_path = str(candidate.resolve())
                    if s_path not in existing_paths:
                        fid = "sys_" + uuid.uuid5(uuid.NAMESPACE_DNS, fname).hex[:10]
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO fonts (
                                id, display_name, file_path, source, category, enabled,
                                license_type, commercial_ok, license_notes, created_at
                            ) VALUES (?, ?, ?, 'system', ?, 1, ?, ?, 'OS標準フォント。商用利用時はOSライセンス条件を確認してください。', ?)
                            """,
                            (fid, disp, s_path, cat, lic_type, comm_ok, now_iso()),
                        )

        rows = conn.execute("SELECT id, file_path FROM fonts").fetchall()
        for r in rows:
            if not Path(r["file_path"]).exists():
                conn.execute("DELETE FROM fonts WHERE id = ?", (r["id"],))


def list_fonts(only_enabled: bool = False) -> List[Dict[str, Any]]:
    sync_fonts()
    with get_conn() as conn:
        q = "SELECT * FROM fonts"
        if only_enabled:
            q += " WHERE enabled = 1"
        q += " ORDER BY source ASC, category ASC, display_name ASC"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_font(font_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fonts WHERE id = ?", (font_id,)).fetchone()
        return dict(row) if row else None


def upload_font(
    original_filename: str,
    file_bytes: bytes,
    category: str = "",
    license_type: str = "商用利用可",
    commercial_ok: bool = True,
    license_notes: str = "",
) -> Dict[str, Any]:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix.lower()
    if ext not in (".ttf", ".otf", ".ttc"):
        raise ValueError("対応フォント形式は .ttf / .otf / .ttc のみです。")

    safe_stem = "".join(c for c in Path(original_filename).stem if c.isalnum() or c in ("-", "_", " "))
    safe_stem = safe_stem.strip() or "custom_font"
    dest = FONTS_DIR / f"{safe_stem}_{uuid.uuid4().hex[:6]}{ext}"
    dest.write_bytes(file_bytes)

    try:
        ImageFont.truetype(str(dest), 32)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ValueError(f"フォントファイルを読み込めませんでした: {exc}") from exc

    fid = "f_" + uuid.uuid4().hex[:10]
    cat = category or _guess_category(original_filename)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO fonts (
                id, display_name, file_path, source, category, enabled,
                license_type, commercial_ok, license_notes, created_at
            ) VALUES (?, ?, ?, 'custom', ?, 1, ?, ?, ?, ?)
            """,
            (
                fid,
                Path(original_filename).stem,
                str(dest.resolve()),
                cat,
                license_type,
                1 if commercial_ok else 0,
                license_notes,
                now_iso(),
            ),
        )
    return get_font(fid)  # type: ignore


def update_font_meta(font_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {"enabled", "category", "license_type", "commercial_ok", "license_notes", "display_name"}
    fields = []
    values = []
    for k, v in updates.items():
        if k in allowed and v is not None:
            if k in ("enabled", "commercial_ok"):
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)
    if fields:
        values.append(font_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE fonts SET {', '.join(fields)} WHERE id = ?", values)
    return get_font(font_id)


def delete_font(font_id: str) -> None:
    font = get_font(font_id)
    if not font:
        return
    if font["source"] == "custom":
        try:
            Path(font["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
        with get_conn() as conn:
            conn.execute("DELETE FROM fonts WHERE id = ?", (font_id,))
    else:
        update_font_meta(font_id, {"enabled": False})


def render_font_preview_png(font_id: str, text: str = "海まで徒歩1分・580万円 / あいうえお 漢字") -> bytes:
    font_row = get_font(font_id)
    w, h = 680, 74
    img = Image.new("RGBA", (w, h), (22, 26, 35, 255))
    draw = ImageDraw.Draw(img)
    if font_row and Path(font_row["file_path"]).exists():
        try:
            font = load_font(font_row["file_path"], 30, 800)
            draw.text((16, 18), text, font=font, fill=(242, 245, 250, 255))
        except Exception:
            draw.text((16, 22), f"[Render Error] {font_row['display_name']}", fill=(248, 113, 113, 255))
    else:
        draw.text((16, 22), "Font not found", fill=(248, 113, 113, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()