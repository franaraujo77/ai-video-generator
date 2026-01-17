"""Project-wide constants and mappings.

This module contains status mapping tables for Notion <-> Task synchronization.
The Task model uses a 26-status enum internally that matches the pipeline stages.
"""

# 26-option Notion status → Task.status (26-status enum)
# Maps Notion database status values to internal TaskStatus enum values
NOTION_TO_INTERNAL_STATUS: dict[str, str] = {
    # Draft & Planning
    "Draft": "draft",
    "Ready for Planning": "draft",
    "Queued": "queued",
    # Processing states (map to pipeline stages)
    "Processing": "claimed",
    "Assets Generating": "generating_assets",
    "Assets Ready": "assets_ready",
    "Assets Approved": "assets_approved",  # Story 5.2: Review gate approval
    "Composites Creating": "generating_composites",
    "Composites Ready": "composites_ready",
    "Videos Generating": "generating_video",
    "Videos Ready": "video_ready",
    "Videos Approved": "video_approved",  # Story 5.2: Review gate approval
    "Audio Generating": "generating_audio",
    "Audio Ready": "audio_ready",
    "Audio Approved": "audio_approved",  # Story 5.2: Review gate approval
    "SFX Generating": "generating_sfx",
    "SFX Ready": "sfx_ready",
    "Assembling Video": "assembling",
    # Review states
    "Ready for Review": "final_review",
    "Under Review": "final_review",
    "Review Approved": "approved",
    "Review Rejected": "final_review",  # Map back to review for retry
    # Upload & completion
    "Uploading": "uploading",
    "Upload Complete": "published",
    # Error states
    "Asset Error": "asset_error",  # Story 5.2: Assets review rejection
    "Video Error": "video_error",  # Story 5.2: Video review rejection
    "Audio Error": "audio_error",  # Story 5.2: Audio review rejection
    "Upload Error": "upload_error",  # Story 5.2: Final review rejection
    "Error: Invalid Input": "draft",  # Go back to draft for correction
    "Error: API Failure": "asset_error",  # Generic API error
    "Error: Retriable": "asset_error",  # Retriable error
    "Error: Manual Review": "asset_error",  # Needs manual intervention
    "Archived": "published",
}

# Task.status → 26-option Notion status
# Maps internal TaskStatus enum values to Notion database status values
# Used for pushing status updates back to Notion
INTERNAL_TO_NOTION_STATUS: dict[str, str] = {
    # Initial states
    "draft": "Draft",
    "queued": "Queued",
    "claimed": "Processing",
    # Asset generation phase
    "generating_assets": "Assets Generating",
    "assets_ready": "Assets Ready",
    "assets_approved": "Assets Ready",  # Keep as Ready until next phase
    # Composite creation phase
    "generating_composites": "Composites Creating",
    "composites_ready": "Composites Ready",
    # Video generation phase
    "generating_video": "Videos Generating",
    "video_ready": "Videos Ready",
    "video_approved": "Videos Ready",  # Keep as Ready until next phase
    # Audio generation phase
    "generating_audio": "Audio Generating",
    "audio_ready": "Audio Ready",
    "audio_approved": "Audio Ready",  # Keep as Ready until next phase
    # Sound effects phase
    "generating_sfx": "SFX Generating",
    "sfx_ready": "SFX Ready",
    # Assembly phase
    "assembling": "Assembling Video",
    "assembly_ready": "Assembling Video",  # Keep in assembling until review
    # Review and approval phase
    "final_review": "Ready for Review",
    "approved": "Review Approved",
    # YouTube upload phase
    "uploading": "Uploading",
    "published": "Upload Complete",
    # Error states (Story 5.2: Review gate rejections)
    "asset_error": "Asset Error",
    "video_error": "Video Error",
    "audio_error": "Audio Error",
    "upload_error": "Upload Error",
}

# Valid Notion priority options
NOTION_PRIORITY_OPTIONS = ["Low", "Normal", "High"]

# Valid Task internal priority options (lowercase)
TASK_PRIORITY_OPTIONS = ["low", "normal", "high"]
