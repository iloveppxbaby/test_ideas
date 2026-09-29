from __future__ import annotations

import pytest
from pydantic import ValidationError

from guazi_script_agent.schemas import ReferenceVideo, ValuePoint, ValuePointSet


def test_example_files_match_schema(example_request) -> None:
    assert example_request.reference.platform == "douyin"
    assert example_request.resolved_duration() == 24
    assert [point.id for point in example_request.value_points.value_points] == [
        "inspection-report",
        "test-drive",
    ]
    assert example_request.value_points.value_points[1].evidence is None


def test_duplicate_value_point_id_is_rejected() -> None:
    point = {
        "id": "same",
        "title": "卖点",
        "description": "说明",
        "audience": "首次购车的人",
        "tone": "直白",
    }
    with pytest.raises(ValidationError, match="必须唯一"):
        ValuePointSet.model_validate({"value_points": [point, point]})


def test_rhythm_gap_is_rejected() -> None:
    with pytest.raises(ValidationError, match="首尾相接"):
        ReferenceVideo.model_validate(
            {
                "title": "中性标题",
                "platform": "douyin",
                "duration_seconds": 10,
                "transcript": "这是一段足够长的中性转写，用来通过校验。",
                "rhythm_notes": [
                    {
                        "start_seconds": 0,
                        "end_seconds": 4,
                        "shot": "画面甲",
                        "purpose": "展开",
                    },
                    {
                        "start_seconds": 5,
                        "end_seconds": 10,
                        "shot": "画面乙",
                        "purpose": "结尾",
                    },
                ],
            }
        )


def test_short_forbidden_phrase_is_rejected() -> None:
    with pytest.raises(ValidationError, match="禁用表述"):
        ValuePoint.model_validate(
            {
                "id": "point",
                "title": "卖点",
                "description": "说明",
                "audience": "首次购车的人",
                "tone": "直白",
                "forbidden_phrases": ["价"],
            }
        )


def test_reference_needs_duration_or_url() -> None:
    with pytest.raises(ValidationError, match="duration_seconds"):
        ReferenceVideo.model_validate({"transcript": "一段中性转写。"})


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ValuePointSet.model_validate({"value_points": [], "extra": 1})
