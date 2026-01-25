"""Tests for Human Review Evidence Tracker (Story 7.7 AC4)."""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock

from app.services.compliance.human_review_evidence_tracker import (
    HumanReviewEvidenceTracker,
)


@pytest.fixture
def evidence_tracker():
    """Create HumanReviewEvidenceTracker instance."""
    return HumanReviewEvidenceTracker()


@pytest.fixture
def mock_task():
    """Mock Task object with compliance_evidence."""
    task = Mock()
    task.id = "task-123"
    task.compliance_evidence = None
    return task


@pytest.fixture
def production_data():
    """Sample production metadata."""
    return {
        "script_author": "Alice (Human Editor)",
        "script_review_time": "2026-01-25T10:00:00Z",
        "script_revisions": 3,
        "story_rationale": "Showcasing Pikachu foraging behavior in forest ecosystem",
        "asset_approvals": 22,
        "composite_choices": ["Pikachu + Forest", "Pikachu + Berry Bush"],
        "regeneration_log": ["Rejected blurry asset #3", "Regenerated environment #7"],
        "trim_decisions": ["Clip 5: trimmed 2s", "Clip 12: adjusted timing"],
        "sfx_choices": ["Forest ambience", "Berry eating sounds"],
        "final_qa_timestamp": "2026-01-25T14:30:00Z",
        "human_approver": "Bob (QA Lead)",
        "total_review_time": 45,
        "project_start": "2026-01-24T09:00:00Z",
        "generation_end": "2026-01-25T12:00:00Z",
        "review_end": "2026-01-25T14:30:00Z",
        "human_hours": 2.5,
        "qa_reviewer": "Bob (QA Lead)",
    }


class TestEvidencePackageBuilding:
    """Test building evidence packages from production data."""

    def test_build_complete_evidence_package(
        self, evidence_tracker, mock_task, production_data
    ):
        """Test building complete evidence package."""
        evidence = evidence_tracker.build_evidence_package(mock_task, production_data)

        # Validate structure
        assert "creative_decisions" in evidence
        assert "review_artifacts" in evidence
        assert "production_timeline" in evidence

        # Validate creative decisions
        assert evidence["creative_decisions"]["story_development"]["human_author"] == "Alice (Human Editor)"
        assert evidence["creative_decisions"]["story_development"]["revision_count"] == 3
        assert evidence["creative_decisions"]["visual_direction"]["asset_approval_count"] == 22

        # Validate review artifacts
        assert "qa_checklist" in evidence["review_artifacts"]
        assert evidence["review_artifacts"]["approval_signature"] == "Bob (QA Lead)"
        assert evidence["review_artifacts"]["review_duration_minutes"] == 45

        # Validate production timeline
        assert evidence["production_timeline"]["total_human_hours"] == 2.5

    def test_build_evidence_with_minimal_data(self, evidence_tracker, mock_task):
        """Test building evidence with minimal production data."""
        minimal_data = {}

        evidence = evidence_tracker.build_evidence_package(mock_task, minimal_data)

        # Should use defaults
        assert evidence["creative_decisions"]["story_development"]["human_author"] == "Unknown"
        assert evidence["creative_decisions"]["story_development"]["revision_count"] == 0
        assert evidence["review_artifacts"]["approval_signature"] == "System"
        assert evidence["production_timeline"]["total_human_hours"] == 1.0

    def test_evidence_size_limit_enforcement(self, evidence_tracker, mock_task):
        """Test that evidence packages are limited to 100KB."""
        # Create huge production data with massive regeneration log
        huge_data = {
            "rejected_generations": ["Rejected asset #" + str(i) for i in range(10000)]
        }

        evidence = evidence_tracker.build_evidence_package(mock_task, huge_data)

        # Should be truncated
        evidence_json = json.dumps(evidence)
        assert len(evidence_json) <= 100000  # 100KB limit


class TestQAChecklist:
    """Test QA checklist generation."""

    def test_generate_qa_checklist(self, evidence_tracker, mock_task, production_data):
        """Test generating standardized QA checklist."""
        checklist = evidence_tracker.generate_qa_checklist(mock_task, production_data)

        # Verify all required checks present
        assert "content_accuracy" in checklist
        assert "visual_quality" in checklist
        assert "audio_sync" in checklist
        assert "educational_value" in checklist
        assert "brand_safety" in checklist
        assert "metadata_quality" in checklist
        assert "ai_disclosure" in checklist
        assert "compliance_check" in checklist

        # Verify reviewer metadata
        assert checklist["reviewer_name"] == "Bob (QA Lead)"
        assert checklist["review_passed"] is True
        assert "review_timestamp" in checklist


class TestEvidenceValidation:
    """Test evidence presence validation."""

    def test_validate_evidence_present_complete(
        self, evidence_tracker, mock_task, production_data
    ):
        """Test validation with complete evidence."""
        # Build and attach evidence to task
        evidence = evidence_tracker.build_evidence_package(mock_task, production_data)
        mock_task.compliance_evidence = evidence

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is True

    def test_validate_evidence_missing(self, evidence_tracker, mock_task):
        """Test validation fails when evidence missing."""
        mock_task.compliance_evidence = None

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is False

    def test_validate_evidence_incomplete(self, evidence_tracker, mock_task):
        """Test validation fails with incomplete evidence."""
        incomplete_evidence = {
            "creative_decisions": {},
            # Missing review_artifacts and production_timeline
        }
        mock_task.compliance_evidence = incomplete_evidence

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is False

    def test_validate_evidence_missing_qa_checklist(self, evidence_tracker, mock_task):
        """Test validation fails when QA checklist missing."""
        evidence = {
            "creative_decisions": {},
            "review_artifacts": {},  # No qa_checklist
            "production_timeline": {},
        }
        mock_task.compliance_evidence = evidence

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is False

    def test_validate_evidence_json_string(self, evidence_tracker, mock_task, production_data):
        """Test validation with JSON string evidence."""
        evidence = evidence_tracker.build_evidence_package(mock_task, production_data)
        mock_task.compliance_evidence = json.dumps(evidence)

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_validate_evidence_malformed_json(self, evidence_tracker, mock_task):
        """Test validation with malformed JSON."""
        mock_task.compliance_evidence = "{invalid json"

        result = evidence_tracker.validate_evidence_present(mock_task)

        assert result is False

    def test_build_evidence_without_task_id(self, evidence_tracker, production_data):
        """Test building evidence for task without ID."""
        task_without_id = Mock()
        task_without_id.id = None

        # Should not crash
        evidence = evidence_tracker.build_evidence_package(
            task_without_id, production_data
        )

        assert "creative_decisions" in evidence
