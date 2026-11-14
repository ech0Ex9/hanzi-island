"""API 请求模型。"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AttemptIn(BaseModel):
    char: str = Field(min_length=1, max_length=4)
    question_type: str = Field(min_length=1, max_length=20)
    selected: str = Field(min_length=1, max_length=20)
    correct_answer: str = Field(min_length=1, max_length=20)
    response_ms: int = Field(ge=0, le=120000)
    reading_key: Optional[str] = Field(default=None, max_length=10)


class AttemptBatchIn(BaseModel):
    session_id: Optional[str] = None
    attempts: List[AttemptIn] = Field(min_length=1, max_length=50)


class SessionIn(BaseModel):
    app_version: Optional[str] = "0.1.0"


class SessionEndIn(BaseModel):
    completed: bool = False


class AchievementSeenIn(BaseModel):
    ids: List[str] = Field(default_factory=list, max_length=50)


class PoemReadIn(BaseModel):
    mode: Literal["read"] = "read"


class RecognitionRunIn(BaseModel):
    scope: str = Field(default="all", min_length=1, max_length=40)
    restart: bool = False


class RecognitionReportIn(BaseModel):
    char: str = Field(min_length=1, max_length=4)
    report: Literal["known", "unknown"]


class RecognitionAttemptIn(BaseModel):
    char: str = Field(min_length=1, max_length=4)
    correct: bool
    response_ms: Optional[int] = Field(default=None, ge=0, le=120000)


class RecognitionItemPatchIn(BaseModel):
    self_report: Literal["known", "unknown"]


class SettingsIn(BaseModel):
    new_per_day: Optional[int] = Field(default=None, ge=1, le=10)
    sound: Optional[bool] = None
    auto_play_audio: Optional[bool] = None
    reduce_motion: Optional[bool] = None
    theme: Optional[str] = Field(default=None, max_length=20)
    pinyin_mode: Optional[str] = Field(default=None, max_length=20)
    achievements_enabled: Optional[bool] = None
