"""汉字小岛 API。"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .db import (
    CONTENT_DB_PATH,
    STATS_DB_PATH,
    checkpoint_content_for_backup,
    checkpoint_for_backup,
    get_db,
    get_settings,
    now_iso,
    today_str,
    update_settings,
)
from . import achievements, curriculum, poems, recognition
from .families import list_families
from .models import (
    AchievementSeenIn,
    AttemptBatchIn,
    PoemReadIn,
    RecognitionAttemptIn,
    RecognitionItemPatchIn,
    RecognitionReportIn,
    RecognitionRunIn,
    SessionEndIn,
    SessionIn,
    SettingsIn,
)
from .polyphonic import list_common_polyphonic
from .readings import list_readings
from .srs import (
    apply_attempt,
    get_character,
    list_characters,
    list_lessons,
    reset_progress,
    stats_summary,
    today_queue,
    weak_characters,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "time": now_iso()}


@router.get("/bootstrap")
def bootstrap() -> dict[str, Any]:
    with get_db() as conn:
        settings = get_settings(conn)
        queue = today_queue(conn, int(settings["new_per_day"]))
        return {
            "settings": settings,
            "stats": stats_summary(conn),
            "books": curriculum.list_books(conn),
            "lessons": list_lessons(conn),
            "readings": list_readings(),
            "poems": poems.list_poems(conn),
            "poem_summary": poems.summary(conn),
            "families": list_families(),
            "queue": queue,
            "recognition": recognition.summary(conn),
            "achievements": achievements.summary(conn),
        }


@router.get("/today")
def today() -> dict[str, Any]:
    with get_db() as conn:
        settings = get_settings(conn)
        return {
            "settings": settings,
            "stats": stats_summary(conn),
            "queue": today_queue(conn, int(settings["new_per_day"])),
        }


@router.get("/characters")
def characters() -> dict[str, Any]:
    with get_db() as conn:
        return {"characters": list_characters(conn)}


@router.get("/characters/{char}")
def character(char: str) -> dict[str, Any]:
    with get_db() as conn:
        data = get_character(conn, char)
        if not data:
            raise HTTPException(status_code=404, detail="没有这个字")
        return data


@router.get("/lessons")
def lessons() -> dict[str, Any]:
    with get_db() as conn:
        return {"lessons": list_lessons(conn)}


@router.get("/books")
def books() -> dict[str, Any]:
    with get_db() as conn:
        return {"books": curriculum.list_books(conn)}


@router.get("/books/{book_id}")
def book_detail(book_id: str) -> dict[str, Any]:
    with get_db() as conn:
        book = curriculum.get_book(conn, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="没有这一册")
        return {"book": book}


@router.get("/lessons/{lesson_id}")
def lesson_detail(lesson_id: str) -> dict[str, Any]:
    with get_db() as conn:
        lesson = curriculum.get_lesson(conn, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="没有这一课")
        return {"lesson": lesson}


@router.get("/poems")
def poem_list() -> dict[str, Any]:
    with get_db() as conn:
        return {"poems": poems.list_poems(conn), "summary": poems.summary(conn)}


@router.get("/poems/{poem_id}")
def poem_detail(poem_id: str) -> dict[str, Any]:
    with get_db() as conn:
        poem = poems.get_poem(conn, poem_id)
        if poem is None:
            raise HTTPException(status_code=404, detail="没有这首诗")
        return {"poem": poem}


@router.post("/poems/{poem_id}/read")
def poem_read(poem_id: str, body: PoemReadIn) -> dict[str, Any]:
    with get_db() as conn:
        try:
            data = poems.mark_read(conn, poem_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        data["achievements"] = achievements.summary(conn)
        return data


@router.post("/sessions")
def start_session(body: SessionIn) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions(id, started_at, app_version) VALUES (?, ?, ?)",
            (session_id, now_iso(), body.app_version or "0.1.0"),
        )
        conn.commit()
    return {"id": session_id}


@router.patch("/sessions/{session_id}")
def end_session(session_id: str, body: SessionEndIn) -> dict[str, Any]:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE sessions SET ended_at = ?, completed = ? WHERE id = ?",
            (now_iso(), 1 if body.completed else 0, session_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="没有这个学习记录")
        return {"ok": True, "achievements": achievements.summary(conn)}


@router.post("/attempts")
def submit_attempts(body: AttemptBatchIn) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with get_db() as conn:
        session_id = body.session_id
        if session_id:
            exists = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not exists:
                session_id = None

        for item in body.attempts:
            row = conn.execute(
                "SELECT char, words_json FROM characters WHERE char = ?",
                (item.char,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=400, detail=f"字库里没有：{item.char}")

            words = []
            try:
                words = [str(w) for w in json.loads(row["words_json"])]
            except (json.JSONDecodeError, TypeError):
                pass

            # 正确答案尽量由服务端决定，避免前端把答案传错。
            if item.question_type in {"audio", "pinyin", "cloze"}:
                correct_answer = item.char
            elif item.question_type == "word":
                correct_answer = (
                    item.correct_answer
                    if item.correct_answer in words
                    else (words[0] if words else item.char)
                )
            else:
                correct_answer = item.correct_answer

            is_correct = int(item.selected.strip() == correct_answer.strip())
            conn.execute(
                """
                INSERT INTO attempts(
                  session_id, ts, local_date, char, question_type,
                  selected, correct_answer, is_correct, response_ms, reading_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    now_iso(),
                    today_str(),
                    item.char,
                    item.question_type,
                    item.selected,
                    correct_answer,
                    is_correct,
                    item.response_ms,
                    item.reading_key,
                ),
            )
            progress = apply_attempt(conn, item.char, bool(is_correct))
            results.append(
                {
                    "char": item.char,
                    "question_type": item.question_type,
                    "selected": item.selected,
                    "correct_answer": correct_answer,
                    "is_correct": bool(is_correct),
                    "response_ms": item.response_ms,
                    "progress": progress,
                }
            )
        conn.commit()
        stats = stats_summary(conn)
    return {"results": results, "stats": stats}


@router.get("/progress")
def progress() -> dict[str, Any]:
    with get_db() as conn:
        return {"characters": list_characters(conn), "stats": stats_summary(conn)}


@router.get("/stats/summary")
def summary() -> dict[str, Any]:
    with get_db() as conn:
        return {
            "stats": stats_summary(conn),
            "weak": weak_characters(conn),
            "settings": get_settings(conn),
            "recognition": recognition.summary(conn),
            "achievements": achievements.summary(conn),
        }


@router.get("/achievements")
def achievement_list() -> dict[str, Any]:
    with get_db() as conn:
        return achievements.summary(conn)


@router.post("/achievements/seen")
def achievement_seen(body: AchievementSeenIn) -> dict[str, Any]:
    with get_db() as conn:
        return achievements.mark_seen(conn, body.ids)


@router.get("/polyphonic")
def polyphonic() -> dict[str, Any]:
    """多音字：教材标注的读音 + 常见多音字补充（data/polyphonic.csv）。"""
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT c.char, c.pinyin, c.audio_key, c.meaning, c.words_json,
                   i.pinyin_override, i.audio_key_override, l.title AS lesson_title
            FROM curriculum_items i
            JOIN characters c ON c.char = i.char
            {curriculum.CURRICULUM_ITEM_JOIN}
            {curriculum.CURRICULUM_ITEM_ORDER}
            """
        ).fetchall()
        common = list_common_polyphonic()
        meanings: dict[str, str] = {}
        if common:
            placeholders = ",".join("?" for _ in common)
            for row in conn.execute(
                f"SELECT char, meaning FROM characters WHERE char IN ({placeholders})",
                [item["char"] for item in common],
            ):
                meanings[row["char"]] = row["meaning"]

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        pinyin = (row["pinyin_override"] or row["pinyin"] or "").strip()
        if not pinyin:
            continue
        entry = grouped.setdefault(
            row["char"],
            {
                "char": row["char"],
                "meaning": row["meaning"],
                "readings": {},
                "source": "textbook",
            },
        )
        reading = entry["readings"].setdefault(
            pinyin,
            {
                "pinyin": pinyin,
                "audio_key": row["audio_key_override"] or row["audio_key"],
                "contexts": [],
                "source": "textbook",
            },
        )
        lesson_title = (row["lesson_title"] or "").strip()
        if lesson_title and lesson_title not in reading["contexts"]:
            reading["contexts"].append(lesson_title)

    # 教材里本来就有两个以上读音的字（8 个），和「只有一个教材读音 + 常见补充」分开。
    textbook_multi = {
        char for char, entry in grouped.items() if len(entry["readings"]) >= 2
    }

    for item in common:
        char = item["char"]
        entry = grouped.get(char)
        if entry is None:
            entry = {
                "char": char,
                "meaning": meanings.get(char, ""),
                "readings": {},
                "source": "common",
            }
            grouped[char] = entry
        elif char not in textbook_multi:
            entry["source"] = "common"
        for reading in item["readings"]:
            existing = entry["readings"].get(reading["pinyin"])
            if existing:
                for context in reading["contexts"]:
                    if context not in existing["contexts"]:
                        existing["contexts"].append(context)
            else:
                entry["readings"][reading["pinyin"]] = {**reading, "source": "common"}

    items = []
    for entry in grouped.values():
        if len(entry["readings"]) < 2:
            continue
        items.append(
            {
                "char": entry["char"],
                "meaning": entry["meaning"],
                "source": "textbook" if entry["char"] in textbook_multi else "common",
                "readings": list(entry["readings"].values()),
            }
        )
    # 教材里出现的多音字排前面，常见补充排后面。
    items.sort(key=lambda item: (1 if item["source"] == "common" else 0, item["char"]))
    return {"items": items}


@router.get("/recognition/overview")
@router.get("/recognition/summary")
def recognition_overview() -> dict[str, Any]:
    with get_db() as conn:
        return recognition.summary(conn)


@router.post("/recognition/runs")
def recognition_start(body: RecognitionRunIn) -> dict[str, Any]:
    with get_db() as conn:
        try:
            return recognition.start_run(conn, body.scope, body.restart)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recognition/runs/{run_id}")
def recognition_run(run_id: str) -> dict[str, Any]:
    with get_db() as conn:
        data = recognition.get_run(conn, run_id)
        if data is None:
            raise HTTPException(status_code=404, detail="没有这一轮认字")
        return data


@router.get("/recognition/runs/{run_id}/items/{index}")
def recognition_run_item(run_id: str, index: int) -> dict[str, Any]:
    with get_db() as conn:
        try:
            return recognition.item_at(conn, run_id, index)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/recognition/runs/{run_id}/reports")
def recognition_report(run_id: str, body: RecognitionReportIn) -> dict[str, Any]:
    with get_db() as conn:
        try:
            return recognition.report(conn, run_id, body.char, body.report)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recognition/items")
def recognition_items(query: str = "", limit: int = 60) -> dict[str, Any]:
    with get_db() as conn:
        return recognition.list_items(conn, query, limit)


@router.patch("/recognition/items/{char}")
def recognition_update_item(char: str, body: RecognitionItemPatchIn) -> dict[str, Any]:
    with get_db() as conn:
        try:
            return recognition.set_report(conn, char, body.self_report)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/recognition/print")
def recognition_print() -> dict[str, Any]:
    with get_db() as conn:
        return recognition.print_sheet(conn)


@router.get("/recognition/today")
def recognition_today() -> dict[str, Any]:
    with get_db() as conn:
        return recognition.today(conn)


@router.post("/recognition/attempts")
def recognition_attempt(body: RecognitionAttemptIn) -> dict[str, Any]:
    with get_db() as conn:
        try:
            return recognition.attempt(
                conn, body.char, body.correct, body.response_ms
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/parent/weekly")
def parent_weekly() -> dict[str, Any]:
    """最近 7 天：每天答题、新字、学习时长，加一句建议。"""
    today = date.today()
    start = today - timedelta(days=6)
    days: list[dict[str, Any]] = []
    with get_db() as conn:
        for offset in range(6, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(is_correct), 0) AS c "
                "FROM attempts WHERE local_date = ?",
                (day,),
            ).fetchone()
            new_chars = int(
                conn.execute(
                    "SELECT COUNT(*) FROM char_progress WHERE substr(first_seen_at, 1, 10) = ?",
                    (day,),
                ).fetchone()[0]
            )
            days.append(
                {
                    "date": day,
                    "attempts": int(row["n"]),
                    "correct": int(row["c"]),
                    "new_chars": new_chars,
                }
            )

        session_rows = conn.execute(
            "SELECT started_at, ended_at FROM sessions "
            "WHERE ended_at IS NOT NULL AND started_at >= ?",
            (start.isoformat(),),
        ).fetchall()
        minutes = 0.0
        for row in session_rows:
            try:
                begin = datetime.fromisoformat(row["started_at"])
                end = datetime.fromisoformat(row["ended_at"])
            except (TypeError, ValueError):
                continue
            seconds = (end - begin).total_seconds()
            if 0 < seconds <= 3600:
                minutes += seconds / 60

    attempts = sum(day["attempts"] for day in days)
    correct = sum(day["correct"] for day in days)
    new_chars = sum(day["new_chars"] for day in days)
    active_days = sum(1 for day in days if day["attempts"] > 0)
    accuracy = round(correct / attempts * 100) if attempts else 0

    if not attempts:
        suggestion = "还没有答题记录。先从每天 3–5 个新字开始，10 分钟就够。"
    elif accuracy < 70:
        suggestion = "正确率偏低，可以把每天新字降到 3 个，多复习几天再往前学。"
    elif active_days >= 5:
        suggestion = "这周坚持得很好。继续保持每天 10 分钟，比一次学很多更有效。"
    else:
        suggestion = "这周学习天数还不多，固定一个时间段（比如晚饭后）会更容易坚持。"

    return {
        "days": days,
        "attempts": attempts,
        "correct": correct,
        "accuracy": accuracy,
        "new_chars": new_chars,
        "active_days": active_days,
        "minutes": round(minutes),
        "suggestion": suggestion,
    }



@router.get("/settings")
def read_settings() -> dict[str, Any]:
    with get_db() as conn:
        return get_settings(conn)


@router.post("/settings")
def write_settings(body: SettingsIn) -> dict[str, Any]:
    with get_db() as conn:
        return update_settings(conn, body.model_dump(exclude_none=True))


@router.post("/reset")
def reset() -> dict[str, Any]:
    with get_db() as conn:
        reset_progress(conn)
        return {"ok": True, "stats": stats_summary(conn)}


@router.get("/export/attempts.csv")
def export_attempts() -> Response:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, ts, local_date, char, question_type,
                   selected, correct_answer, is_correct, response_ms, reading_key
            FROM attempts ORDER BY id
            """
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "session_id",
            "ts",
            "local_date",
            "char",
            "question_type",
            "selected",
            "correct_answer",
            "is_correct",
            "response_ms",
            "reading_key",
        ]
    )
    for row in rows:
        writer.writerow([row[key] for key in row.keys()])
    content = "\ufeff" + buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="hanzi-attempts.csv"'},
    )


@router.get("/backup")
@router.get("/backup/stats")
def backup() -> FileResponse:
    checkpoint_for_backup()
    if not STATS_DB_PATH.exists():
        raise HTTPException(status_code=404, detail="统计数据库还没有生成")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return FileResponse(
        STATS_DB_PATH,
        media_type="application/vnd.sqlite3",
        filename=f"hanzi-stats-{stamp}.db",
    )


@router.get("/backup/content")
def backup_content() -> FileResponse:
    checkpoint_content_for_backup()
    if not CONTENT_DB_PATH.exists():
        raise HTTPException(status_code=404, detail="内容数据库还没有生成")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return FileResponse(
        CONTENT_DB_PATH,
        media_type="application/vnd.sqlite3",
        filename=f"hanzi-content-{stamp}.db",
    )
