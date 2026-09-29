from __future__ import annotations

import pytest

from guazi_script_agent.schemas import BeatRole, HookType, ReferenceVideo
from guazi_script_agent.structure import extract_structure, infer_hook_type


def _video(**overrides: object) -> ReferenceVideo:
    payload: dict[str, object] = {
        "title": "一条中性标题",
        "platform": "douyin",
        "duration_seconds": 10,
        "transcript": "画面先停住，再切到下一条信息。",
        "rhythm_notes": [
            {
                "start_seconds": 0,
                "end_seconds": 5,
                "shot": "中性画面",
                "purpose": "展开",
            },
            {
                "start_seconds": 5,
                "end_seconds": 10,
                "shot": "中性结尾",
                "purpose": "结尾",
            },
        ],
    }
    payload.update(overrides)
    return ReferenceVideo.model_validate(payload)


def test_example_structure_borrows_timing_and_roles(example_request) -> None:
    structure = extract_structure(
        example_request.reference, example_request.resolved_duration()
    )
    assert structure.hook_type == HookType.pain
    assert structure.beat_count == 5
    assert structure.shot_density_per_10s == 2.08
    assert [beat.role for beat in structure.beats] == [
        BeatRole.hook,
        BeatRole.build,
        BeatRole.proof,
        BeatRole.turn,
        BeatRole.cta,
    ]
    assert [beat.start_seconds for beat in structure.beats] == [0, 3, 9, 16, 21]
    assert structure.beats[-1].end_seconds == 24


def test_duration_override_scales_beats(example_request) -> None:
    structure = extract_structure(example_request.reference, 12)
    assert [beat.start_seconds for beat in structure.beats] == [0, 1.5, 4.5, 8, 10.5]
    assert [beat.end_seconds for beat in structure.beats] == [1.5, 4.5, 8, 10.5, 12]


def test_missing_rhythm_is_synthesized() -> None:
    video = _video(duration_seconds=24, rhythm_notes=[])
    structure = extract_structure(video, 24)
    assert structure.beat_count == 5
    assert structure.beats[0].role == BeatRole.hook
    assert structure.beats[-1].role == BeatRole.cta
    assert structure.beats[0].start_seconds == 0
    assert structure.beats[-1].end_seconds == 24


@pytest.mark.parametrize(
    ("why_viral", "expected"),
    [
        ("这是痛点", HookType.pain),
        ("吃亏之后给了三个清单", HookType.pain),
        ("用故事做代入", HookType.story),
        ("做成三条清单", HookType.number),
        ("制造反差", HookType.contrast),
        ("抛出疑问", HookType.question),
        (None, HookType.question),
    ],
)
def test_hook_priority(why_viral: str | None, expected: HookType) -> None:
    video = _video(why_viral=why_viral)
    assert infer_hook_type(video) == expected
