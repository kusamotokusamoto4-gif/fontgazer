#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Fonts (google/fonts リポジトリ) から、再配布・商用利用が可能なライセンス
(OFL / Apache 2.0 / Ubuntu Font License) のフォントだけを集めるスクリプト。

- 標準ライブラリのみ使用（pip install 不要）
- 既にダウンロード済みのファイルはスキップ（再実行しても続きから）
- fonts/catalog.json と fonts/catalog.csv にフォント名・配布元・ライセンス等を記録
- preview.html を生成して、日本語テロップの見た目を一覧で確認できる

使い方:
  python fetch_fonts.py                 日本語対応フォントを収集
  python fetch_fonts.py --latin 100     加えて欧文のみ人気上位100ファミリーも収集
  python fetch_fonts.py --preview-only  プレビューHTMLだけ作り直す

GitHubの無認証APIは回数制限があります。足りない場合は環境変数 GITHUB_TOKEN を設定してください。
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(ROOT, "fonts")
CATALOG_JSON = os.path.join(FONT_DIR, "catalog.json")
CATALOG_CSV = os.path.join(FONT_DIR, "catalog.csv")
PREVIEW_HTML = os.path.join(ROOT, "preview.html")

API_ROOT_TREE = "https://api.github.com/repos/google/fonts/git/trees/main"
META_URL = "https://fonts.google.com/metadata/fonts"
RAW_BASE = "https://raw.githubusercontent.com/google/fonts/main/"
SOURCE_BASE = "https://github.com/google/fonts/tree/main/"

# 採用するライセンス。いずれも商用利用・動画への使用・SNS投稿に制限なし。
ALLOWED = {
    "ofl": "SIL Open Font License 1.1",
    "apache": "Apache License 2.0",
    "ufl": "Ubuntu Font License 1.0",
}

FONT_EXT = (".ttf", ".otf")


def http_get(url, retries=3):
    headers = {"User-Agent": "telop-font-library/1.0"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + token
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429) and "api.github.com" in url:
                print("  ! GitHub APIの回数制限に達した可能性があります。"
                      "GITHUB_TOKEN を設定するか、しばらく待って再実行してください。")
                raise
            if e.code == 404:
                raise
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


def get_json(url):
    return json.loads(http_get(url).decode("utf-8"))


def norm(family):
    """Google Fonts のフォルダ名規則: 小文字・英数字のみ。"""
    return re.sub(r"[^a-z0-9]", "", family.lower())


def cmap_codepoints(path):
    """フォントファイルの cmap から、収録されている文字コード一覧を取り出す（標準ライブラリのみ）。"""
    import struct
    cps = set()
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            off = 0
            if head[:4] == b"ttcf":
                f.seek(12)
                off = struct.unpack(">I", f.read(4))[0]
            f.seek(off + 4)
            n = struct.unpack(">H", f.read(2))[0]
            f.seek(off + 12)
            cmap_off = cmap_len = None
            for _ in range(n):
                rec = f.read(16)
                if rec[:4] == b"cmap":
                    cmap_off, cmap_len = struct.unpack(">II", rec[8:16])
                    break
            if cmap_off is None:
                return cps
            f.seek(cmap_off)
            d = f.read(cmap_len)
        num = struct.unpack(">H", d[2:4])[0]
        for i in range(num):
            _, _, so = struct.unpack(">HHI", d[4 + 8 * i: 12 + 8 * i])
            fmt = struct.unpack(">H", d[so:so + 2])[0]
            if fmt == 4:
                segx2 = struct.unpack(">H", d[so + 6:so + 8])[0]
                seg = segx2 // 2
                ends = struct.unpack(">%dH" % seg, d[so + 14: so + 14 + segx2])
                starts = struct.unpack(">%dH" % seg, d[so + 16 + segx2: so + 16 + 2 * segx2])
                for s, e in zip(starts, ends):
                    if s != 0xFFFF:
                        cps.update(range(s, e + 1))
            elif fmt == 12:
                ng = struct.unpack(">I", d[so + 12:so + 16])[0]
                for g in range(ng):
                    s, e, _ = struct.unpack(">III", d[so + 16 + 12 * g: so + 28 + 12 * g])
                    cps.update(range(s, min(e, 0x2FFFF) + 1))
    except Exception:  # noqa: BLE001
        pass
    return cps


def coverage(folder, files):
    """ひらがな・カタカナ・漢字がどれだけ入っているかを調べる。"""
    best = (0, 0, 0)
    for fn in files:
        cps = cmap_codepoints(os.path.join(folder, fn))
        hira = sum(1 for c in cps if 0x3041 <= c <= 0x3096)
        kata = sum(1 for c in cps if 0x30A1 <= c <= 0x30FA)
        kanji = sum(1 for c in cps if 0x4E00 <= c <= 0x9FFF or 0x3400 <= c <= 0x4DBF)
        if kanji + hira > best[0] + best[1]:
            best = (kanji, hira, kata)
    kanji, hira, kata = best
    level = "full" if kanji >= 2000 else ("partial" if kanji > 0 else "none")
    if kanji + hira + kata == 0:
        level = "unknown"  # 読み取れなかった場合は除外しない
    return {"kanji": kanji, "hiragana": hira, "katakana": kata, "kanji_level": level}


def analyze_missing(cat, force=False):
    changed = 0
    for fid, e in cat.items():
        if not force and "kanji_level" in e:
            continue
        folder = os.path.join(FONT_DIR, fid)
        if os.path.isdir(folder) and e.get("files"):
            e.update(coverage(folder, e["files"]))
            changed += 1
    if changed:
        print("漢字の収録数を調べました: %d ファミリー" % changed)
    return changed + drop_kana_only(cat)


def drop_kana_only(cat):
    """漢字がほとんど入っていない日本語フォント（かな専用など）を一覧から外す。ファイルは消さない。"""
    drop = [k for k, e in cat.items()
            if e.get("japanese") and e.get("origin") != "manual"
            and e.get("kanji_level") in ("partial", "none")]
    for k in drop:
        print("  - 漢字が足りないため一覧から除外: %s" % cat[k]["family"])
        del cat[k]
    return len(drop)


def load_catalog():
    if os.path.exists(CATALOG_JSON):
        with open(CATALOG_JSON, encoding="utf-8") as f:
            return {e["id"]: e for e in json.load(f)}
    return {}


def save_catalog(cat):
    os.makedirs(FONT_DIR, exist_ok=True)
    items = sorted(cat.values(), key=lambda e: (not e["japanese"], e["family"].lower()))
    with open(CATALOG_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    with open(CATALOG_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "family", "japanese", "kanji_level", "kanji_count", "category",
                    "license", "source", "files", "fetched"])
        for e in items:
            w.writerow([e["id"], e["family"], "yes" if e["japanese"] else "no",
                        e.get("kanji_level", ""), e.get("kanji", ""), e["category"],
                        e["license"], e["source"], " | ".join(e["files"]), e["fetched"]])


def build_index():
    """google/fonts の ofl / apache / ufl 配下のファイル一覧を取得。"""
    print("[1/4] フォント配布リポジトリの一覧を取得中...")
    root = get_json(API_ROOT_TREE)
    shas = {e["path"]: e["sha"] for e in root["tree"] if e["path"] in ALLOWED}
    index = {}
    for lic, sha in shas.items():
        data = get_json("https://api.github.com/repos/google/fonts/git/trees/%s?recursive=1" % sha)
        if data.get("truncated"):
            print("  ! %s の一覧が途中で切れています（一部のフォントが見つからない可能性）" % lic)
        for e in data["tree"]:
            if e["type"] != "blob":
                continue
            parts = e["path"].split("/", 1)
            if len(parts) == 2:
                index.setdefault(parts[0], (lic, []))[1].append(parts[1])
    return index


def load_families():
    print("[2/4] Google Fonts のメタデータを取得中...")
    raw = http_get(META_URL).decode("utf-8")
    raw = raw[raw.index("{"):]  # 先頭の )]}' を除去
    return json.loads(raw)["familyMetadataList"]


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = http_get(url)
    with open(dest, "wb") as f:
        f.write(data)
    return True


def fetch_family(fam, lic, files, is_jp, cat):
    fid = norm(fam["family"])
    top = [f for f in files if "/" not in f and f.lower().endswith(FONT_EXT)]
    if not top:  # 静的フォントが static/ にしかない場合
        top = [f for f in files if f.lower().endswith(FONT_EXT)]
    if not top:
        return False
    extras = [f for f in files if "/" not in f and
              (re.match(r"(OFL|LICENSE|UFL)", f, re.I) and f.lower().endswith(".txt") or f == "METADATA.pb")]
    folder = os.path.join(FONT_DIR, fid)
    saved = []
    for f in top + extras:
        url = RAW_BASE + lic + "/" + fid + "/" + urllib.parse.quote(f)
        dest = os.path.join(folder, os.path.basename(f))
        try:
            download(url, dest)
            if f in top:
                saved.append(os.path.basename(f))
        except Exception as e:  # noqa: BLE001
            print("    ! 失敗: %s (%s)" % (f, e))
    if not saved:
        return False
    cat[fid] = {
        "id": fid,
        "family": fam["family"],
        "japanese": is_jp,
        "category": fam.get("category", ""),
        "license": ALLOWED[lic],
        "source": SOURCE_BASE + lic + "/" + fid,
        "files": sorted(saved),
        "fetched": datetime.date.today().isoformat(),
    }
    cat[fid].update(coverage(folder, saved))
    if is_jp and cat[fid]["kanji_level"] in ("partial", "none"):
        print("    ! 漢字がほとんど入っていないため除外します: %s" % fam["family"])
        del cat[fid]
        return False
    return True


def build_preview(cat):
    items = sorted(cat.values(), key=lambda e: (not e["japanese"], e["family"].lower()))
    html = PREVIEW_TEMPLATE.replace("__DATA__", json.dumps(items, ensure_ascii=False))
    with open(PREVIEW_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("プレビューを作成しました: preview.html（%d ファミリー）" % len(items))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--latin", type=int, default=0, metavar="N",
                    help="日本語非対応（欧文のみ）の人気上位Nファミリーも収集")
    ap.add_argument("--display", type=int, default=0, metavar="N",
                    help="欧文の装飾系(display)の人気上位Nファミリーも収集")
    ap.add_argument("--color", action="store_true",
                    help="色つき(カラー)フォントをすべて収集")
    ap.add_argument("--analyze", action="store_true",
                    help="取得済みフォントの漢字収録数を調べ直してプレビューを更新")
    ap.add_argument("--preview-only", action="store_true")
    args = ap.parse_args()

    cat = load_catalog()
    if args.preview_only or args.analyze:
        if analyze_missing(cat, force=args.analyze):
            save_catalog(cat)
        build_preview(cat)
        return

    index = build_index()
    fams = load_families()

    jp = [f for f in fams if "japanese" in f.get("subsets", [])]
    jp.sort(key=lambda f: f["family"].lower())
    others = [f for f in fams if "japanese" not in f.get("subsets", [])]
    others.sort(key=lambda f: f.get("popularity", 10 ** 6))
    latin = []
    if args.latin > 0:
        latin += others[: args.latin]
    if args.display > 0:  # 縁取り・影・装飾入りが多い display カテゴリ
        latin += [f for f in others if f.get("category") == "display"][: args.display]
    if args.color:  # 色つき(カラー)フォント
        latin += [f for f in others if f.get("colorCapabilities")]
    seen = set()
    latin = [f for f in latin if not (f["family"] in seen or seen.add(f["family"]))]

    print("[3/4] ダウンロード開始: 日本語対応 %d 件 / 欧文のみ %d 件（候補）" % (len(jp), len(latin)))
    ok = skipped = 0
    for group, is_jp in ((jp, True), (latin, False)):
        for fam in group:
            fid = norm(fam["family"])
            if fid not in index:
                skipped += 1
                print("  - 対象外（OFL/Apache/UFL以外、または未収録）: %s" % fam["family"])
                continue
            lic, files = index[fid]
            print("  + %s  [%s]" % (fam["family"], ALLOWED[lic]))
            if fetch_family(fam, lic, files, is_jp, cat):
                ok += 1
                save_catalog(cat)  # 途中で止まっても記録が残る
            else:
                skipped += 1

    print("[4/4] 記録とプレビューを作成中...")
    analyze_missing(cat)
    save_catalog(cat)
    build_preview(cat)

    total = 0
    for dp, _, fs in os.walk(FONT_DIR):
        for fn in fs:
            total += os.path.getsize(os.path.join(dp, fn))
    print("\n完了: 取得 %d 件 / スキップ %d 件 / fonts フォルダ合計 %.0f MB" % (ok, skipped, total / 1048576))


PREVIEW_TEMPLATE = r"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>テロップ用フォント プレビュー</title>
<style>
  :root { --bg:#111; --fg:#f5f5f5; --card:#1c1c1c; --line:#333; --sub:#9a9a9a; }
  body.light { --bg:#f4f4f4; --fg:#111; --card:#fff; --line:#ddd; --sub:#666; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font-family:system-ui,"Yu Gothic UI",sans-serif; }
  header { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line);
           padding:12px 16px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
  header input[type=text] { padding:8px 10px; border-radius:6px; border:1px solid var(--line);
           background:var(--card); color:var(--fg); font-size:16px; }
  #text { flex:1 1 320px; }
  label { font-size:13px; color:var(--sub); display:flex; align-items:center; gap:6px; }
  select, button { padding:7px 10px; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--fg); }
  main { display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:12px; padding:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; cursor:pointer; }
  .card:hover { border-color:var(--sub); }
  .name { font-size:13px; font-weight:600; font-family:system-ui,sans-serif; }
  .meta { font-size:11px; color:var(--sub); margin-top:2px; font-family:system-ui,sans-serif; }
  .sample { margin-top:10px; line-height:1.5; word-break:break-all; min-height:1.6em; color:#fff;
            padding:10px 14px; border-radius:8px; overflow:hidden;
            background:linear-gradient(135deg,#5b6b7b,#9aa8b5); }
  .tag { display:inline-block; font-size:10px; padding:1px 6px; border-radius:99px; border:1px solid var(--sub); margin-right:4px; }
  #count { font-size:13px; color:var(--sub); }</style>
</head>
<body>
<header>
  <input type="text" id="text" value="今夜、はじまる。 Opening 2026">
  <input type="text" id="q" placeholder="フォント名で検索">
  <label>サイズ <input type="range" id="size" min="16" max="96" value="40"></label>
  <label>太さ <input type="range" id="weight" min="100" max="900" step="100" value="400"></label>
  <select id="filter">
    <option value="all">すべて</option>
    <option value="jp">日本語対応のみ</option>
    <option value="latin">欧文のみ</option>
  </select>
  <select id="style"></select>
  <button id="theme">背景切替</button>
  <span id="count"></span>
</header>
<main id="grid"></main>
<script>
const DATA = __DATA__;
const css = [];
DATA.forEach(f => f.files.forEach((file, i) => {
  const fam = "f_" + f.id + "_" + i;
  css.push('@font-face{font-family:"' + fam + '";src:url("fonts/' + f.id + '/' + encodeURIComponent(file) +
           '");font-weight:100 900;font-display:swap;}');
}));
const st = document.createElement("style"); st.textContent = css.join("\n"); document.head.appendChild(st);

const grid = document.getElementById("grid");
const $ = id => document.getElementById(id);

function render() {
  const q = $("q").value.trim().toLowerCase();
  const flt = $("filter").value;
  const pass = f => flt === "all" || (flt === "jp" && f.japanese) || (flt === "latin" && !f.japanese);
  const list = DATA.filter(f => pass(f) && (!q || f.family.toLowerCase().includes(q)));
  grid.innerHTML = "";
  list.forEach(f => {
    const el = document.createElement("div"); el.className = "card";
    const fam = "f_" + f.id + "_0";
    el.innerHTML =
      '<div class="name"></div><div class="meta"></div><div class="sample"></div>';
    el.querySelector(".name").textContent = f.family;
    el.querySelector(".meta").innerHTML =
      '<span class="tag">' + (f.japanese ? "日本語対応" : "欧文のみ") + '</span>' + f.license + ' / ' + f.files.length + ' ファイル';
    const s = el.querySelector(".sample");
    const span = document.createElement("span");
    span.textContent = $("text").value;
    span.style.cssText = STYLES[$("style").value] || "";
    span.style.display = "inline-block";
    s.appendChild(span);
    s.style.fontFamily = '"' + fam + '", sans-serif';
    s.style.fontSize = $("size").value + "px";
    s.style.fontWeight = $("weight").value;
    el.title = "クリックでフォント名をコピー";
    el.onclick = () => navigator.clipboard && navigator.clipboard.writeText(f.family);
    grid.appendChild(el);
  });
  $("count").textContent = list.length + " 件";
}
// 装飾の見本（フォントではなく、文字に重ねる縁取り・光・影・グラデ）
const STYLES = {
  "装飾なし（白文字）": "",
  "青い光＋白縁": "color:#1f3dff;-webkit-text-stroke:.14em #fff;paint-order:stroke fill;text-shadow:0 0 .25em #2a6bff,0 0 .5em #2a6bff;",
  "黄色の立体影（斜体）": "color:#fff200;transform:skewX(-10deg);text-shadow:.04em .04em 0 #c9a400,.08em .08em 0 #c9a400,.12em .12em 0 #8a6d00,.16em .16em 0 #8a6d00;",
  "赤い光＋黄白グラデ": "background:linear-gradient(#fff,#ffe100);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 .1em #ff1a1a) drop-shadow(0 0 .2em #ff1a1a);",
  "斜体＋黒縁": "color:#fff;transform:skewX(-12deg);-webkit-text-stroke:.14em #000;paint-order:stroke fill;",
  "橙グラデ＋白縁＋黄光": "color:#ff8a00;-webkit-text-stroke:.12em #fff;paint-order:stroke fill;filter:drop-shadow(0 0 .15em #ffe94d);",
  "黒い影（白文字）": "color:#fff;text-shadow:.05em .05em .1em #000,0 0 .15em #000;",
  "黄文字＋黒縁（太字テロップ）": "color:#ffd400;-webkit-text-stroke:.14em #000;paint-order:stroke fill;",
  "白文字＋オレンジ帯": "color:#fff;background:#ff7a00;padding:.05em .3em;",
  "白文字＋ピンク紫帯": "color:#fff;background:linear-gradient(90deg,#e86bd6,#9b6bff);padding:.05em .3em;"
};
Object.keys(STYLES).forEach(k => { const o = document.createElement("option"); o.value = o.textContent = k; $("style").appendChild(o); });
["text","q","size","weight","filter","style"].forEach(id => $(id).addEventListener("input", render));
$("theme").onclick = () => document.body.classList.toggle("light");
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断しました。再実行すると続きから取得します。")
        sys.exit(1)
