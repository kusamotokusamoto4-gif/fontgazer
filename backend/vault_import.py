"""フォント保管庫(fontgazer)のフォントを、このアプリのフォントライブラリに登録する。

使い方:
    IMPORT_FONTS.bat をダブルクリック（初回だけ fontgazer フォルダの場所を聞かれます）
    または  venv\\Scripts\\python.exe -m backend.vault_import "C:\\...\\fontgazer"

- fontgazer/fonts/catalog.json を読み、日本語対応（漢字がそろっているもの）だけ登録
- フォントファイルはコピーせず、fontgazer 側のファイルをそのまま参照
- 何度実行しても重複しない。「有効/無効」「カテゴリ」をアプリ上で変更していた場合は保持
- ライセンス名と配布元URLを、フォントの「ライセンスメモ」に記録
"""
import json
import sys
from pathlib import Path

from .database import DATA_DIR, get_conn, init_db, now_iso
from .fonts_manager import _guess_category, sync_fonts

# Google Fonts のカテゴリ → このアプリのカテゴリ
CATALOG_CATEGORY_MAP = {
    "sansserif": "gothic",
    "serif": "mincho",
    "display": "display",
    "handwriting": "pop",
    "monospace": "minimal",
}

WEIGHT_SCORES = (
    ("black", 95), ("heavy", 94), ("extrabold", 92), ("semibold", 80),
    ("bold", 90), ("medium", 70), ("regular", 60),
)


def _file_score(filename: str) -> int:
    low = filename.lower()
    if "italic" in low:
        return -1
    if "[" in filename and "wght" in low:
        return 100  # 可変フォント: 太さをアプリ側で選べる
    for key, score in WEIGHT_SCORES:
        if key in low:
            return score
    return 50


def _choose_file(files):
    return max(files, key=lambda f: (_file_score(f), -len(f)))


def _category(entry) -> str:
    guessed = _guess_category(entry["family"])
    if guessed != "gothic":
        return guessed
    key = str(entry.get("category", "")).lower().replace(" ", "").replace("-", "").replace("_", "")
    return CATALOG_CATEGORY_MAP.get(key, "gothic")


def import_vault(vault_dir: Path) -> None:
    catalog_path = vault_dir / "fonts" / "catalog.json"
    items = json.loads(catalog_path.read_text(encoding="utf-8"))

    init_db()
    added = updated = skipped = 0
    with get_conn() as conn:
        existing = {r["id"] for r in conn.execute("SELECT id FROM fonts").fetchall()}
        for e in items:
            if not e.get("japanese"):
                skipped += 1  # 欧文のみのフォントは、日本語テロップに使えない
                continue
            if e.get("kanji_level") in ("partial", "none"):
                skipped += 1
                continue
            folder = vault_dir / "fonts" / e["id"]
            files = [f for f in e.get("files", []) if (folder / f).exists()]
            if not files:
                skipped += 1
                continue

            path = str((folder / _choose_file(files)).resolve())
            fid = "v_" + e["id"][:60]
            notes = "保管庫: %s / 取得日 %s" % (e.get("source", ""), e.get("fetched", ""))
            if e.get("license_url"):
                notes += " / 規約: %s（確認日 %s）" % (e["license_url"], e.get("license_checked", ""))

            conn.execute(
                """
                INSERT INTO fonts (
                    id, display_name, file_path, source, category, enabled,
                    license_type, commercial_ok, license_notes, created_at
                ) VALUES (?, ?, ?, 'vault', ?, 1, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    file_path = excluded.file_path,
                    license_type = excluded.license_type,
                    license_notes = excluded.license_notes
                """,
                (fid, e["family"], path, _category(e), e.get("license", ""), notes, now_iso()),
            )
            if fid in existing:
                updated += 1
            else:
                added += 1

    sync_fonts()
    print("\n完了: 追加 %d 件 / 更新 %d 件 / 対象外 %d 件" % (added, updated, skipped))
    print("（対象外は、欧文のみ・漢字が少ない・ファイルなし のフォントです）")


def main() -> None:
    saved = DATA_DIR / "vault_path.txt"
    arg = sys.argv[1].strip().strip('"') if len(sys.argv) > 1 else ""
    if not arg and saved.exists():
        arg = saved.read_text(encoding="utf-8").strip()
    if not arg:
        arg = input("フォント保管庫(fontgazer)のフォルダのパスを入力してください: ").strip().strip('"')

    vault = Path(arg)
    if not (vault / "fonts" / "catalog.json").exists():
        print("fonts\\catalog.json が見つかりません: %s" % vault)
        print("fontgazer フォルダで START.BAT の 1 を実行して、フォントを集めてから、もう一度試してください。")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    saved.write_text(str(vault), encoding="utf-8")
    import_vault(vault)


if __name__ == "__main__":
    main()
