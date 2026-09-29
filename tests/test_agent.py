from __future__ import annotations

import json
from pathlib import Path

import pytest

from guazi_script_agent.agent import generate_script
from guazi_script_agent.errors import AgentError
from guazi_script_agent.llm.mock import MockLLMClient
from guazi_script_agent.originality import normalize_copy
from guazi_script_agent.prompts import PROMPT_VERSION, render_prompts
from guazi_script_agent.render import render_json, render_markdown
from guazi_script_agent.schemas import ComplianceKind, VideoScript
from guazi_script_agent.structure import extract_structure

ROOT = Path(__file__).resolve().parents[1]


def _viewer_text(script: VideoScript) -> str:
    parts = [script.title, script.opening_hook, script.cta]
    for beat in script.beats:
        parts.extend((beat.voiceover, beat.visual, beat.subtitle))
    return "\n".join(parts)


def test_prompt_keeps_structure_and_drops_source_copy(example_request) -> None:
    structure = extract_structure(
        example_request.reference, example_request.resolved_duration()
    )
    system_prompt, user_prompt = render_prompts(example_request, structure)
    combined = system_prompt + user_prompt
    video = example_request.reference
    assert "禁止照搬" in system_prompt
    assert PROMPT_VERSION == "v1"
    assert '"prompt_version": "v1"' in user_prompt
    assert "inspection-report" in user_prompt
    assert "直白、克制、可信" in user_prompt
    assert "购车顾虑" in user_prompt
    assert video.transcript not in combined
    assert video.title not in combined
    assert video.why_viral not in combined
    for note in video.rhythm_notes:
        assert note.shot not in combined


def test_mock_script_covers_value_points_and_compliance(example_request) -> None:
    script = generate_script(example_request)
    assert script.provider == "mock"
    assert script.prompt_version == "v1"
    assert script.schema_version == "1.0"
    assert script.structure_borrowed.hook_type.value == "pain"
    assert script.structure_borrowed.timing_scaled is False
    assert script.opening_hook == script.beats[0].voiceover
    spoken = "\n".join(beat.voiceover for beat in script.beats)
    for point in example_request.value_points.value_points:
        assert point.id in {
            identifier for beat in script.beats for identifier in beat.value_point_ids
        }
        assert point.title in spoken
    assert "示例：详情页可打开该车检测报告" in spoken
    assert "待核实" in spoken
    viewer = _viewer_text(script)
    for point in example_request.value_points.value_points:
        for phrase in point.forbidden_phrases:
            assert phrase not in viewer
    kinds = [note.kind for note in script.compliance_notes]
    assert ComplianceKind.no_false_promise in kinds
    assert ComplianceKind.evidence_bound in kinds
    assert ComplianceKind.unverified_claim in kinds
    unverified = next(
        note
        for note in script.compliance_notes
        if note.kind == ComplianceKind.unverified_claim
    )
    assert unverified.related_value_point_ids == ["test-drive"]
    for beat in script.beats:
        assert len(beat.voiceover) <= (beat.end_seconds - beat.start_seconds) * 8 + 8


def test_duration_override_still_valid(example_request) -> None:
    request = example_request.model_copy(update={"target_duration_seconds": 12})
    script = generate_script(request)
    assert script.target_duration_seconds == 12
    assert script.structure_borrowed.timing_scaled is True
    assert script.beats[-1].end_seconds == 12
    assert script.beats[0].start_seconds == 0


def test_success_calls_model_once(example_request) -> None:
    class Counting:
        name = "mock"

        def __init__(self) -> None:
            self.inner = MockLLMClient()
            self.calls = 0

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            return self.inner.complete(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

    client = Counting()
    script = generate_script(example_request, llm=client)
    assert client.calls == 1
    assert script.provider == "mock"


def test_invalid_json_is_retried_once(example_request) -> None:
    class Flaky:
        name = "flaky"

        def __init__(self) -> None:
            self.inner = MockLLMClient()
            self.calls = 0

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "没有 json"
            return self.inner.complete(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

    client = Flaky()
    script = generate_script(example_request, llm=client)
    assert client.calls == 2
    assert script.title
    assert script.provider == "flaky"


def test_forbidden_phrase_from_model_is_removed(example_request) -> None:
    class Tamper:
        name = "tamper"

        def __init__(self) -> None:
            self.inner = MockLLMClient()

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            payload = json.loads(
                self.inner.complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
            )
            payload["beats"][1]["voiceover"] += "全网最低价"
            return json.dumps(payload, ensure_ascii=False)

    script = generate_script(example_request, llm=Tamper())
    assert "全网最低价" not in _viewer_text(script)
    assert any(
        note.kind == ComplianceKind.forbidden_phrase for note in script.compliance_notes
    )


def test_copied_transcript_is_rejected(example_request) -> None:
    gram = normalize_copy(example_request.reference.transcript)[:12]

    class Tamper:
        name = "tamper"

        def __init__(self) -> None:
            self.inner = MockLLMClient()

        def complete(self, *, system_prompt: str, user_prompt: str) -> str:
            payload = json.loads(
                self.inner.complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
            )
            payload["opening_hook"] = gram
            payload["beats"][0]["voiceover"] = gram
            return json.dumps(payload, ensure_ascii=False)

    with pytest.raises(AgentError, match="连续重复"):
        generate_script(example_request, llm=Tamper())


def test_checked_in_example_matches_generator(example_request) -> None:
    script = generate_script(example_request)
    assert (ROOT / "examples/sample_output.json").read_text(
        encoding="utf-8"
    ) == render_json(script)
    assert (ROOT / "examples/sample_script.md").read_text(
        encoding="utf-8"
    ) == render_markdown(script)
    assert "口播" in (ROOT / "examples/sample_script.md").read_text(encoding="utf-8")
    VideoScript.model_validate_json(
        (ROOT / "examples/sample_output.json").read_text(encoding="utf-8")
    )
