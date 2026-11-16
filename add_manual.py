#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Fonts 以外の配布サイトのフォントを、確認済みのものだけ取り込むスクリプト。

流れ:
  1. queue.json に「確認済みフォント」の情報を書く（Claudeが調査して作成）
       verdict が "ok"（利用条件を確認済み）のものだけが対象。
       ok でも license_summary と license_url が空だと取り込まない。
  2. download_url があれば自動ダウンロード。なければ、配布ページでダウンロードした
     zip / ttf / otf を inbox フォルダに入れる。
  3. START.BAT の 6 を実行 → fonts/ に展開、catalog.json に記録、preview.html を更新。
"""
import datetime
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile

import fetch_fonts as ff

ROOT = ff.ROOT
INBOX = os.path.join(ROOT, "inbox")
DONE = os.path.join(INBOX, "done")
QUEUE = os.path.join(ROOT, "queue.json")
DOC_EXT = (".txt", ".md", ".pdf", ".html")
DOC_HINT = re.compile(r"(license|licence|readme|ofl|read|規約|利用|ライセンス|はじめ)", re.I)


def key(s):
    return re.sub(r"[\s_\-\.\(\)（）　]+", "", s).lower()


def safe_id(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_") or "font"


def zip_name(info):
    """UTF-8フラグがないzip内の日本語名(cp932)を直す。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp932")
    except Exception:  # noqa: BLE001
        return info.filename


def extract(path, dest):
    """フォントファイルと規約文書を dest に取り出し、フォントのファイル名一覧を返す。"""
    saved = []
    os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = zip_name(info)
                base = os.path.basename(name.replace("\\", "/"))
                low = base.lower()
                is_font = low.endswith(ff.FONT_EXT)
                is_doc = low.endswith(DOC_EXT) and DOC_HINT.search(base)
                if not (is_font or is_doc):
                    continue
                with open(os.path.join(dest, base), "wb") as f:
                    f.write(z.read(info))
                if is_font:
                    saved.append(base)
    elif path.lower().endswith(ff.FONT_EXT):
        base = os.path.basename(path)
        shutil.copy(path, os.path.join(dest, base))
        saved.append(base)
    return sorted(set(saved))


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "telop-font-library/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    suffix = ".zip" if data[:2] == b"PK" else os.path.splitext(url.split("?")[0])[1] or ".bin"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return tmp


def valid_ok(e):
    return (e.get("verdict") == "ok" and str(e.get("license_summary", "")).strip()
            and str(e.get("license_url", "")).strip())


def main():
    os.makedirs(INBOX, exist_ok=True)
    if not os.path.exists(QUEUE):
        with open(QUEUE, "w", encoding="utf-8") as f:
            f.write("[]\n")
        print("queue.json を作りました。Claudeが調べた結果をここに入れてください。")
        return
    with open(QUEUE, encoding="utf-8") as f:
        queue = json.load(f)

    cat = ff.load_catalog()
    pending = []
    for e in queue:
        name = e.get("name", "")
        fid = safe_id(e.get("id") or name)
        if fid in cat:
            continue
        if not valid_ok(e):
            print("  - 取り込まない: %s（verdict=%s。確認済み(ok)かつ規約情報つきのみ対象）"
                  % (name, e.get("verdict", "unknown")))
            continue
        pending.append((e, fid))

    inbox_files = [f for f in os.listdir(INBOX)
                   if os.path.isfile(os.path.join(INBOX, f))
                   and f.lower().endswith((".zip",) + ff.FONT_EXT)]
    used = set()
    matched = {}
    # 1) ファイル名で対応づけ
    for e, fid in pending:
        if e.get("download_url"):
            continue
        for fn in inbox_files:
            if fn in used:
                continue
            k = key(fn)
            if key(e["name"]) in k or key(fid) in k:
                matched[fid] = os.path.join(INBOX, fn)
                used.add(fn)
                break
    # 2) 残りが1つずつなら対応づけ
    rest = [(e, fid) for e, fid in pending if not e.get("download_url") and fid not in matched]
    left = [fn for fn in inbox_files if fn not in used]
    if len(rest) == 1 and len(left) == 1:
        matched[rest[0][1]] = os.path.join(INBOX, left[0])
        used.add(left[0])

    added = 0
    for e, fid in pending:
        name = e["name"]
        src = matched.get(fid)
        tmp = None
        if not src and e.get("download_url"):
            try:
                print("  ダウンロード中: %s" % name)
                src = tmp = download(e["download_url"])
            except Exception as ex:  # noqa: BLE001
                print("  ! ダウンロード失敗: %s (%s)" % (name, ex))
        if not src:
            print("  ! %s のファイルがありません。配布ページ: %s\n"
                  "    ダウンロードした zip/ttf/otf を inbox フォルダに入れて、もう一度実行してください。"
                  % (name, e.get("source_url", "(URLなし)")))
            continue
        dest = os.path.join(ff.FONT_DIR, fid)
        saved = extract(src, dest)
        if not saved:
            shutil.rmtree(dest, ignore_errors=True)
            print("  ! %s: フォントファイル(ttf/otf)が見つかりません" % name)
            continue
        cat[fid] = {
            "id": fid,
            "family": name,
            "japanese": bool(e.get("japanese", True)),
            "category": e.get("category", ""),
            "license": e["license_summary"],
            "source": e.get("source_url", ""),
            "files": saved,
            "fetched": datetime.date.today().isoformat(),
            "origin": "manual",
            "license_url": e["license_url"],
            "license_checked": e.get("checked", ""),
        }
        added += 1
        print("  + 追加: %s（%d ファイル）" % (name, len(saved)))
        if tmp:
            os.remove(tmp)
        elif src.startswith(INBOX):
            os.makedirs(DONE, exist_ok=True)
            shutil.move(src, os.path.join(DONE, os.path.basename(src)))

    for fn in inbox_files:
        if fn not in used:
            print("  ? 対応するqueueがないファイル: %s（そのまま残しています）" % fn)

    if added:
        ff.save_catalog(cat)
        ff.build_preview(cat)
    print("\n完了: %d 件追加" % added)


if __name__ == "__main__":
    main()
