import json
import threading
import traceback
import uuid
from typing import Any, Dict, List

from .database import OUTPUTS_DIR, THUMBS_DIR, get_conn, list_assets, now_iso
from .dna_generator import generate_batch_dnas
from .renderer import render_video_from_dna


def _run_batch_thread(batch_id: str, project: Dict[str, Any], count: int) -> None:
    try:
        all_assets = list_assets()
        selected_assets = [a for a in all_assets if a["selected"] == 1]
        if not selected_assets:
            raise ValueError("使用する画像・動画素材が選択されていません。")

        with get_conn() as conn:
            conn.execute(
                "UPDATE batches SET current_message = ? WHERE id = ?",
                (f"デザインDNAを{count}パターン設計中...", batch_id),
            )

        dnas = generate_batch_dnas(project=project, count=count, assets=selected_assets)

        for idx, dna in enumerate(dnas):
            with get_conn() as conn:
                conn.execute(
                    "UPDATE batches SET current_message = ? WHERE id = ?",
                    (f"動画をレンダリング中 ({idx + 1}/{len(dnas)}): {dna['font_name']} × {dna['hook_animation_label']}", batch_id),
                )

            vid_id = f"v_{uuid.uuid4().hex[:10]}"
            out_mp4 = OUTPUTS_DIR / f"{batch_id}_{idx + 1:02d}_{vid_id}.mp4"
            out_thumb = THUMBS_DIR / f"{vid_id}.jpg"

            try:
                total_dur, hook_dur = render_video_from_dna(
                    dna=dna,
                    assets=selected_assets,
                    output_mp4_path=str(out_mp4),
                    thumb_jpg_path=str(out_thumb),
                )
                status = "done"
                err_msg = ""
            except Exception as vid_exc:
                total_dur = float(dna["narrative"]["total_duration"])
                hook_dur = float(dna["narrative"]["hook_duration"])
                status = "error"
                err_msg = f"{vid_exc}\n{traceback.format_exc()[-500:]}"

            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO generated_videos (
                        id, batch_id, index_in_batch, status, file_path, thumb_path,
                        duration, hook_duration, dna_json, combo_hash,
                        is_favorite, is_disliked, error_message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                    """,
                    (
                        vid_id, batch_id, idx + 1, status, str(out_mp4), str(out_thumb),
                        total_dur, hook_dur, json.dumps(dna, ensure_ascii=False),
                        dna["combo_hash"], err_msg, now_iso(),
                    ),
                )
                conn.execute(
                    "UPDATE batches SET completed_count = ? WHERE id = ?",
                    (idx + 1, batch_id),
                )

        with get_conn() as conn:
            conn.execute(
                "UPDATE batches SET status = 'completed', current_message = ? WHERE id = ?",
                (f"{len(dnas)}パターンの生成が完了しました！", batch_id),
            )
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                "UPDATE batches SET status = 'error', error_message = ?, current_message = ? WHERE id = ?",
                (f"{exc}\n{traceback.format_exc()}", f"エラー: {exc}", batch_id),
            )


def start_batch_job(project: Dict[str, Any], count: int = 10) -> str:
    all_assets = list_assets()
    selected_assets = [a for a in all_assets if a["selected"] == 1]
    if not selected_assets:
        raise ValueError("素材が選択されていません。画像を1枚以上、または動画を1本以上アップロードして選択してください。")

    batch_id = f"b_{uuid.uuid4().hex[:10]}"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO batches (
                id, status, total_count, completed_count, current_message,
                error_message, project_json, styles_json, created_at
            ) VALUES (?, 'running', ?, 0, '生成ジョブを開始しています...', '', ?, ?, ?)
            """,
            (
                batch_id, count,
                json.dumps(project, ensure_ascii=False),
                json.dumps(project.get("styles", ["auto"]), ensure_ascii=False),
                now_iso(),
            ),
        )

    th = threading.Thread(
        target=_run_batch_thread, args=(batch_id, project, count), daemon=True
    )
    th.start()
    return batch_id


def get_batch_status(batch_id: str) -> Dict[str, Any]:
    with get_conn() as conn:
        brow = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if not brow:
            raise ValueError("指定されたバッチが見つかりません。")
        vrows = conn.execute(
            "SELECT * FROM generated_videos WHERE batch_id = ? ORDER BY index_in_batch ASC",
            (batch_id,),
        ).fetchall()

        videos: List[Dict[str, Any]] = []
        for vr in vrows:
            d = dict(vr)
            d["dna"] = json.loads(d["dna_json"])
            d["video_url"] = f"/api/videos/{d['id']}/stream"
            d["download_url"] = f"/api/videos/{d['id']}/download"
            d["thumb_url"] = f"/api/videos/{d['id']}/thumb"
            videos.append(d)

        res = dict(brow)
        res["styles"] = json.loads(res["styles_json"])
        res["project"] = json.loads(res["project_json"])
        res["videos"] = videos
        return res