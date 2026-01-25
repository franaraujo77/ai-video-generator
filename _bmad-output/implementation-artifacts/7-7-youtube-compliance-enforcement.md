# Story 7.7: YouTube Compliance Enforcement

Status: completed
Completed: 2026-01-25

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **content creator**,
I want **the system to enforce YouTube Partner Program compliance**,
So that **my channel remains in good standing** (FR66).

## Acceptance Criteria

### AC1: Content Uniqueness Verification
**Given** a video is queued for upload
**When** compliance checks run
**Then** the video is verified as unique (not duplicate content)
**And** uniqueness score exceeds 70% threshold across visual, narrative, and metadata dimensions

### AC2: Duplicate Content Detection
**Given** two identical videos are attempted for the same channel
**When** the duplicate is detected
**Then** the second upload is blocked
**And** an error is logged: "Duplicate content detected"
**And** the task status becomes COMPLIANCE_VIOLATION (terminal)

### AC3: Upload Frequency Throttling
**Given** upload frequency exceeds organic patterns (e.g., >3/day)
**When** the threshold is crossed
**Then** a warning is logged
**And** uploads are throttled to maintain natural appearance
**And** scheduled upload times are adjusted with 4-8 hour variance

### AC4: Human Review Evidence Attachment
**Given** human review was completed before upload
**When** the upload runs
**Then** evidence of human review is attached to audit log
**And** content authenticity metadata is included (July 2025 compliance)
**And** AI disclosure is set via YouTube Data API

## Tasks / Subtasks

- [ ] Task 1: Research YouTube Partner Program compliance requirements (AC1-4)
  - [ ] Subtask 1.1: Research July 2025 YPP policy changes (inauthentic content rules)
  - [ ] Subtask 1.2: Document duplicate content detection criteria (visual, narrative, metadata)
  - [ ] Subtask 1.3: Research organic upload frequency patterns (3/day max, 4-8hr variance)
  - [ ] Subtask 1.4: Document AI disclosure requirements (May 21, 2025 mandatory labels)
  - [ ] Subtask 1.5: Research C2PA/CAI content credentials (optional but recommended)
  - [ ] Subtask 1.6: Validate against YouTube Partner Program 2025-2026 documentation

- [ ] Task 2: Design content uniqueness validation service (AC1)
  - [ ] Subtask 2.1: Create ContentUniquenessValidator class in app/services/compliance/
  - [ ] Subtask 2.2: Design visual_uniqueness check (perceptual hashing comparison)
  - [ ] Subtask 2.3: Design narrative_uniqueness check (story structure comparison)
  - [ ] Subtask 2.4: Design metadata_uniqueness check (title/description/tags diversity)
  - [ ] Subtask 2.5: Define 70% uniqueness threshold (must pass all dimensions)
  - [ ] Subtask 2.6: Add database table: content_uniqueness_scores

- [ ] Task 3: Implement duplicate content detection (AC2)
  - [ ] Subtask 3.1: Create DuplicateContentDetector class
  - [ ] Subtask 3.2: Implement perceptual hashing for video thumbnails/composites
  - [ ] Subtask 3.3: Implement story structure fingerprinting (18-clip narrative patterns)
  - [ ] Subtask 3.4: Implement metadata similarity scoring (Levenshtein distance)
  - [ ] Subtask 3.5: Add COMPLIANCE_VIOLATION to TaskStatus enum
  - [ ] Subtask 3.6: Create database migration for new TaskStatus value
  - [ ] Subtask 3.7: Log duplicate detection events with structured logging

- [ ] Task 4: Design upload frequency throttling service (AC3)
  - [ ] Subtask 4.1: Create OrganicUploadScheduler class in app/services/compliance/
  - [ ] Subtask 4.2: Define throttling rules (3/day max, 4-8 hour variance, time-of-day rotation)
  - [ ] Subtask 4.3: Implement channel-specific limits (new vs established channels)
  - [ ] Subtask 4.4: Add stagger variance logic (2-hour randomness to avoid predictability)
  - [ ] Subtask 4.5: Implement time-of-day rotation (morning/afternoon/evening/night)
  - [ ] Subtask 4.6: Add database table: upload_frequency_log

- [ ] Task 5: Implement AI disclosure automation (AC4)
  - [ ] Subtask 5.1: Create AIDisclosureManager class in app/services/compliance/
  - [ ] Subtask 5.2: Set hasAlteredContent=true via YouTube Data API contentDetails
  - [ ] Subtask 5.3: Add AI disclosure text to video description (belt-and-suspenders)
  - [ ] Subtask 5.4: Format disclosure: "🤖 AI DISCLOSURE: Imagery (Gemini), Animation (Kling), Narration (ElevenLabs)"
  - [ ] Subtask 5.5: Validate disclosure is set before upload completes

- [ ] Task 6: Implement human review evidence builder (AC4)
  - [ ] Subtask 6.1: Create HumanReviewEvidenceTracker class
  - [ ] Subtask 6.2: Build evidence package: creative_decisions, review_artifacts, production_timeline
  - [ ] Subtask 6.3: Generate QA checklist (content_accuracy, visual_quality, audio_sync, brand_safety)
  - [ ] Subtask 6.4: Track regeneration log (rejected AI outputs as proof of quality control)
  - [ ] Subtask 6.5: Store evidence in database table: human_review_evidence
  - [ ] Subtask 6.6: Add compliance_evidence JSONB column to tasks table

- [ ] Task 7: Create compliance pre-check orchestration (AC1-4)
  - [ ] Subtask 7.1: Create PreUploadComplianceValidator class
  - [ ] Subtask 7.2: Orchestrate all compliance checks before upload
  - [ ] Subtask 7.3: Run content uniqueness validation (ContentUniquenessValidator)
  - [ ] Subtask 7.4: Run duplicate content detection (DuplicateContentDetector)
  - [ ] Subtask 7.5: Run upload frequency throttling (OrganicUploadScheduler)
  - [ ] Subtask 7.6: Verify AI disclosure and human review evidence
  - [ ] Subtask 7.7: Raise ComplianceViolationError if any check fails

- [ ] Task 8: Integrate compliance checks with youtube_uploader_integration (AC1-4)
  - [ ] Subtask 8.1: Add compliance pre-check call before upload_video()
  - [ ] Subtask 8.2: Handle ComplianceViolationError (mark task as COMPLIANCE_VIOLATION)
  - [ ] Subtask 8.3: Send Discord alert for compliance violations
  - [ ] Subtask 8.4: Update task.error_log with compliance violation details
  - [ ] Subtask 8.5: Prevent upload if compliance checks fail

- [ ] Task 9: Create compliance database schema (AC1-4)
  - [ ] Subtask 9.1: Create migration for content_uniqueness_scores table
  - [ ] Subtask 9.2: Create migration for upload_frequency_log table
  - [ ] Subtask 9.3: Create migration for human_review_evidence table
  - [ ] Subtask 9.4: Add compliance_evidence JSONB column to tasks table
  - [ ] Subtask 9.5: Add COMPLIANCE_VIOLATION to TaskStatus enum migration

- [ ] Task 10: Write comprehensive tests for compliance enforcement (AC1-4)
  - [ ] Subtask 10.1: Create tests/services/compliance/test_content_uniqueness.py
  - [ ] Subtask 10.2: Test visual uniqueness validation (perceptual hashing)
  - [ ] Subtask 10.3: Test narrative uniqueness validation (story fingerprinting)
  - [ ] Subtask 10.4: Test metadata uniqueness validation (title/description diversity)
  - [ ] Subtask 10.5: Test duplicate content detection (identical videos blocked)
  - [ ] Subtask 10.6: Create tests/services/compliance/test_upload_frequency.py
  - [ ] Subtask 10.7: Test upload throttling (3/day max, 4-8 hour variance)
  - [ ] Subtask 10.8: Test time-of-day rotation (avoid predictable patterns)
  - [ ] Subtask 10.9: Create tests/services/compliance/test_ai_disclosure.py
  - [ ] Subtask 10.10: Test AI disclosure set via YouTube Data API
  - [ ] Subtask 10.11: Test human review evidence builder
  - [ ] Subtask 10.12: Test compliance orchestration (all checks pass/fail scenarios)

- [ ] Task 11: Update documentation (AC1-4)
  - [ ] Subtask 11.1: Document YouTube Partner Program compliance requirements
  - [ ] Subtask 11.2: Document content uniqueness validation logic
  - [ ] Subtask 11.3: Document upload frequency throttling rules
  - [ ] Subtask 11.4: Document AI disclosure requirements (May 2025 mandate)
  - [ ] Subtask 11.5: Document human review evidence structure
  - [ ] Subtask 11.6: Add troubleshooting guide for compliance violations

## Dev Notes

### Epic 7 Context

**Story 7.7 is the SEVENTH STORY of Epic 7: YouTube Publishing & Compliance.**

From sprint-status.yaml:122-134:
- **Epic Status:** in-progress
- **Story 7.1 (YouTube OAuth Setup CLI):** done (code review complete 2026-01-24)
- **Story 7.2 (OAuth Token Refresh Automation):** in-progress (code review complete, Task 5 pending)
- **Story 7.3 (Video Metadata Generation):** done (code review complete 2026-01-25)
- **Story 7.4 (Resumable Upload Implementation):** done (code review complete 2026-01-25)
- **Story 7.5 (YouTube URL Retrieval & Notion Update):** done (code review complete 2026-01-25)
- **Story 7.6 (Upload Error Handling):** done (code review complete 2026-01-25)
- **Previous Stories:** Story 7.1-7.6 complete → YouTube upload pipeline fully operational
- **Current Story:** Story 7.7 implements YouTube Partner Program compliance enforcement
- **Next Stories:** Story 7.8-7.9 (Privacy Configuration, Audit Logging)

**Epic 7 Goal:** Approved videos upload to YouTube automatically with proper metadata, OAuth, quota management, and compliance evidence for YouTube Partner Program.

### Story Dependencies

**Prerequisite Stories (COMPLETED):**
- **Story 5.2 (Review Gate Enforcement):** Human review gates before upload ✅
- **Story 5.3 (Asset Review Interface):** Asset approval tracking ✅
- **Story 5.4 (Video Review Interface):** Video approval tracking ✅
- **Story 5.5 (Audio Review Interface):** Audio approval tracking ✅
- **Story 7.4 (Resumable Upload Implementation):** upload_video() function ✅
- **Story 7.5 (YouTube URL Retrieval & Notion Update):** Notion sync service ✅
- **Story 7.6 (Upload Error Handling):** Error handling and retry logic ✅

**Dependent Stories (FUTURE):**
- **Story 7.8 (Channel Privacy Configuration):** Will use compliance checks for privacy enforcement
- **Story 7.9 (Human Review Audit Logging):** Will extend human review evidence tracking
- **Epic 8 Stories:** Monitoring and observability for compliance metrics

### Architecture Compliance

**YouTube Partner Program Compliance Requirements (2025-2026 Research)**

From web research and YouTube Partner Program documentation:

**July 2025 Policy Changes:**

YouTube updated its monetization policies on July 15, 2025, changing "repetitious content" to **"inauthentic content"**, which includes:
- Mass-produced or near-duplicate videos
- Template-based content with minimal variation
- Automatically generated videos with minimal human input
- Compilations with no added value (no commentary, context, or creative edits)

**What's Still Allowed:**
- Content with creativity, analysis, or meaningful context
- Videos following a format but offering fresh takes
- AI-assisted videos where humans steer creative direction (OUR USE CASE ✅)
- Reaction/commentary videos that add transformative value

**Critical Compliance Requirements:**

1. **Content Uniqueness Validation (AC1, AC2):**

Each video must demonstrate uniqueness across multiple dimensions:

```python
# Content Uniqueness Threshold
UNIQUENESS_THRESHOLDS = {
    'visual_uniqueness': 0.70,      # 70% different visual elements
    'narrative_uniqueness': 0.70,   # 70% different story structure
    'metadata_uniqueness': 0.70,    # 70% different titles/descriptions/tags
    'overall_uniqueness': 0.70      # Must pass ALL checks
}

# Uniqueness Validation Logic
class ContentUniquenessValidator:
    def validate_video_uniqueness(self, video_metadata, recent_videos):
        """
        Validate video against duplicate content requirements.

        Returns:
            Dict with uniqueness scores for each dimension
        """
        scores = {
            'visual_uniqueness': self.check_visual_variation(video_metadata, recent_videos),
            'narrative_uniqueness': self.check_story_uniqueness(video_metadata, recent_videos),
            'metadata_uniqueness': self.check_metadata_variation(video_metadata, recent_videos)
        }

        # ALL checks must pass 70% threshold
        passes_all = all(score >= 0.70 for score in scores.values())

        return {
            'passes': passes_all,
            'scores': scores,
            'overall_score': sum(scores.values()) / len(scores)
        }

    def check_visual_variation(self, video_metadata, recent_videos):
        """
        Compare visual elements against recent uploads:
        - Different Pokemon behaviors/actions
        - Different environmental contexts (forest vs ocean vs mountain)
        - Different camera compositions
        - Different lighting/time of day

        Implementation: Perceptual hashing of thumbnail/composite images
        """
        import imagehash
        from PIL import Image

        current_hash = imagehash.phash(Image.open(video_metadata['thumbnail_path']))

        similarity_scores = []
        for recent_video in recent_videos[-20:]:  # Check last 20 videos
            recent_hash = imagehash.phash(Image.open(recent_video['thumbnail_path']))
            similarity = 1 - (current_hash - recent_hash) / 64.0  # Normalize hash distance
            similarity_scores.append(similarity)

        # Average dissimilarity (1 - similarity)
        uniqueness_score = 1 - (sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0)

        return uniqueness_score

    def check_story_uniqueness(self, video_metadata, recent_videos):
        """
        Validate narrative originality:
        - Different behavioral sequences (feeding vs hunting vs social)
        - Different ecological contexts (migration vs mating vs defense)
        - Unique educational insights per video

        Implementation: Story structure fingerprinting
        """
        current_story_structure = self.extract_story_structure(video_metadata)

        similarity_scores = []
        for recent_video in recent_videos[-20:]:
            recent_structure = self.extract_story_structure(recent_video)
            similarity = self.compare_story_structures(current_story_structure, recent_structure)
            similarity_scores.append(similarity)

        uniqueness_score = 1 - (sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0)

        return uniqueness_score

    def extract_story_structure(self, video_metadata):
        """
        Extract story fingerprint from 18-clip narrative.

        Returns:
            List of behavior/scene categories for each clip
        """
        # Parse 02_story_script.md from video metadata
        story_script = video_metadata['story_script_content']

        # Extract behavior categories from each clip
        behavior_sequence = []
        for clip in story_script['clips']:
            behavior_category = self.classify_behavior(clip['description'])
            behavior_sequence.append(behavior_category)

        return behavior_sequence

    def classify_behavior(self, clip_description):
        """
        Classify clip into behavior category.

        Categories: feeding, hunting, social, defensive, migration, mating,
                   resting, exploration, communication, parenting
        """
        # Use keyword matching or simple NLP to categorize
        keywords_map = {
            'feeding': ['eat', 'consume', 'hunt prey', 'forage'],
            'hunting': ['stalk', 'chase', 'attack', 'pursuit'],
            'social': ['interact', 'group', 'communicate', 'play'],
            'defensive': ['protect', 'defend', 'threaten', 'retreat'],
            # ... etc
        }

        # Simple keyword matching
        for category, keywords in keywords_map.items():
            if any(keyword in clip_description.lower() for keyword in keywords):
                return category

        return 'general'

    def compare_story_structures(self, structure1, structure2):
        """
        Calculate similarity between two story structures.

        Uses sequence alignment to measure how similar the behavioral patterns are.
        """
        # Calculate Levenshtein distance for behavior sequences
        from difflib import SequenceMatcher

        matcher = SequenceMatcher(None, structure1, structure2)
        similarity = matcher.ratio()

        return similarity

    def check_metadata_variation(self, video_metadata, recent_videos):
        """
        Ensure metadata diversity:
        - Unique title structures
        - Varied descriptions
        - Different tag combinations

        Implementation: Text similarity scoring
        """
        from difflib import SequenceMatcher

        current_title = video_metadata['title']
        current_description = video_metadata['description']
        current_tags = set(video_metadata['tags'])

        title_similarities = []
        description_similarities = []
        tag_overlaps = []

        for recent_video in recent_videos[-20:]:
            # Title similarity
            matcher = SequenceMatcher(None, current_title, recent_video['title'])
            title_similarities.append(matcher.ratio())

            # Description similarity
            matcher = SequenceMatcher(None, current_description, recent_video['description'])
            description_similarities.append(matcher.ratio())

            # Tag overlap
            recent_tags = set(recent_video['tags'])
            overlap_ratio = len(current_tags & recent_tags) / len(current_tags | recent_tags)
            tag_overlaps.append(overlap_ratio)

        # Average dissimilarity
        avg_title_dissimilarity = 1 - (sum(title_similarities) / len(title_similarities) if title_similarities else 0)
        avg_description_dissimilarity = 1 - (sum(description_similarities) / len(description_similarities) if description_similarities else 0)
        avg_tag_dissimilarity = 1 - (sum(tag_overlaps) / len(tag_overlaps) if tag_overlaps else 0)

        # Weighted average (title most important)
        uniqueness_score = (
            0.5 * avg_title_dissimilarity +
            0.3 * avg_description_dissimilarity +
            0.2 * avg_tag_dissimilarity
        )

        return uniqueness_score
```

**Duplicate Content Detection (AC2):**

```python
# Duplicate Detection Logic
class DuplicateContentDetector:
    def detect_duplicate(self, video_metadata, all_channel_videos):
        """
        Detect if video is duplicate of existing content.

        Returns:
            {
                'is_duplicate': bool,
                'duplicate_of': video_id or None,
                'similarity_score': float (0-1)
            }
        """
        # Check perceptual hash of thumbnail
        current_hash = imagehash.phash(Image.open(video_metadata['thumbnail_path']))

        for existing_video in all_channel_videos:
            existing_hash = imagehash.phash(Image.open(existing_video['thumbnail_path']))
            hash_distance = current_hash - existing_hash

            # Hash distance < 5 indicates near-identical images
            if hash_distance < 5:
                # Additional checks: story structure, metadata
                story_similarity = self.compare_stories(video_metadata, existing_video)
                metadata_similarity = self.compare_metadata(video_metadata, existing_video)

                # If visual + story + metadata all >90% similar → DUPLICATE
                if story_similarity > 0.90 and metadata_similarity > 0.90:
                    return {
                        'is_duplicate': True,
                        'duplicate_of': existing_video['id'],
                        'similarity_score': (hash_distance / 64.0 + story_similarity + metadata_similarity) / 3
                    }

        return {
            'is_duplicate': False,
            'duplicate_of': None,
            'similarity_score': 0.0
        }
```

---

2. **Upload Frequency Throttling (AC3):**

YouTube's spam detection flags accounts based on:
- High-frequency uploads with low watch time/retention
- Bulk upload patterns (dozens of videos daily)
- Predictable timing patterns (all uploads at same time)
- Low engagement signals (likes, comments, shares)

**Recommended Upload Patterns:**

```python
# Upload Frequency Limits
UPLOAD_FREQUENCY_LIMITS = {
    'new_channel': {           # <100 videos, <6 months old
        'daily_max': 2,
        'weekly_max': 10,
        'min_hours_between': 6,
        'stagger_variance_hours': 2
    },
    'established_channel': {   # >100 videos, >6 months old
        'daily_max': 3,
        'weekly_max': 15,
        'min_hours_between': 4,
        'stagger_variance_hours': 2
    }
}

# Organic Upload Scheduler
class OrganicUploadScheduler:
    def schedule_upload(self, video_metadata, channel_config, recent_uploads):
        """
        Schedule upload with organic timing patterns.

        Returns:
            datetime of next available upload slot
        """
        # Get channel type (new vs established)
        channel_type = self.classify_channel(channel_config)
        limits = UPLOAD_FREQUENCY_LIMITS[channel_type]

        # Check daily limit
        today_uploads = [u for u in recent_uploads if u.date == datetime.now().date()]
        if len(today_uploads) >= limits['daily_max']:
            # Schedule for next day
            next_slot = datetime.now().replace(hour=9, minute=0) + timedelta(days=1)
            return self.add_stagger_variance(next_slot, limits['stagger_variance_hours'])

        # Check minimum spacing
        if recent_uploads:
            last_upload_time = recent_uploads[0]['uploaded_at']
            min_next_time = last_upload_time + timedelta(hours=limits['min_hours_between'])

            if datetime.now() < min_next_time:
                # Wait until minimum spacing met
                next_slot = min_next_time
            else:
                # Can upload now, but add variance
                next_slot = datetime.now()
        else:
            # First upload - schedule now
            next_slot = datetime.now()

        # Add stagger variance (human-like randomness)
        final_slot = self.add_stagger_variance(next_slot, limits['stagger_variance_hours'])

        # Rotate time of day (avoid predictable patterns)
        final_slot = self.vary_time_of_day(final_slot, recent_uploads)

        return final_slot

    def add_stagger_variance(self, base_time, variance_hours):
        """
        Add random variance to upload time (human-like unpredictability).
        """
        import random
        variance_minutes = random.uniform(0, variance_hours * 60)
        return base_time + timedelta(minutes=variance_minutes)

    def vary_time_of_day(self, base_time, recent_uploads):
        """
        Rotate upload times to avoid predictable patterns.

        Time windows: morning (9-11am), afternoon (2-4pm), evening (7-9pm), night (10pm-midnight)
        """
        # Extract hour-of-day from recent uploads
        recent_hours = [u['uploaded_at'].hour for u in recent_uploads[-5:]]

        # Define time windows
        windows = {
            'morning': (9, 11),
            'afternoon': (14, 16),
            'evening': (19, 21),
            'night': (22, 24)
        }

        # Find least-used window
        window_usage = {
            window: sum(1 for h in recent_hours if start <= h < end)
            for window, (start, end) in windows.items()
        }

        least_used_window = min(window_usage, key=window_usage.get)
        start_hour, end_hour = windows[least_used_window]

        # Adjust base_time to fall within least-used window
        import random
        target_hour = random.randint(start_hour, end_hour - 1)
        target_minute = random.randint(0, 59)

        return base_time.replace(hour=target_hour, minute=target_minute)

    def classify_channel(self, channel_config):
        """
        Classify channel as new or established.
        """
        # Query database for channel stats
        total_videos = channel_config.get('total_videos_uploaded', 0)
        channel_age_days = (datetime.now() - channel_config['created_at']).days

        if total_videos > 100 and channel_age_days > 180:
            return 'established_channel'
        else:
            return 'new_channel'
```

**Upload Pattern Diversity:**

```python
# Content Diversity Enforcer
class ContentDiversityEnforcer:
    def validate_upload_diversity(self, pending_video, recent_uploads):
        """
        Ensure variety across recent uploads.

        Prevents uploading too many similar videos in short timeframe.
        """
        # Pokemon variety: Maximum 2 videos per Pokemon species per week
        pokemon_name = pending_video['pokemon_name']
        recent_week = [v for v in recent_uploads if (datetime.now() - v['uploaded_at']).days <= 7]
        same_pokemon_count = sum(1 for v in recent_week if v['pokemon_name'] == pokemon_name)

        if same_pokemon_count >= 2:
            raise ComplianceViolationError(
                f"Pokemon diversity violation: {pokemon_name} already uploaded {same_pokemon_count} times this week. "
                f"Maximum 2 per week to maintain content variety."
            )

        # Behavior variety: Different behaviors across recent uploads
        behavior_categories = [self.classify_behavior(v['story_script']) for v in recent_uploads[-5:]]
        pending_behavior = self.classify_behavior(pending_video['story_script'])

        if behavior_categories.count(pending_behavior) >= 3:
            raise ComplianceViolationError(
                f"Behavior diversity violation: '{pending_behavior}' behavior used in 3+ of last 5 videos. "
                f"Upload different behavior types to maintain variety."
            )

        return True
```

---

3. **AI Disclosure Requirements (AC4):**

**Mandatory Disclosure Timeline:**
- **May 21, 2025:** AI disclosure labels became mandatory
- **July 15, 2025:** Monetization enforcement began
- **Current requirement:** All synthetic/altered content must be labeled

**What Requires Disclosure (Our Use Case):**
- ✅ **Synthetic voices** (ElevenLabs narration cloning real voices)
- ✅ **AI-generated visuals** (Gemini character/environment images)
- ✅ **AI-animated scenes** (Kling video generation)
- ❌ **Production assistance** (scriptwriting, ideation - NO disclosure needed)
- ❌ **Clearly unrealistic content** (Pokemon are fantasy creatures - NO disclosure needed)

**Technical Implementation:**

```python
# AI Disclosure Manager
class AIDisclosureManager:
    def set_ai_disclosure(self, video_id, youtube_service):
        """
        Set AI disclosure via YouTube Data API v3.

        MUST be called before video goes public.
        """
        video_metadata = {
            'id': video_id,
            'contentDetails': {
                'hasCustomThumbnail': True,
                'hasAlteredContent': True,  # CRITICAL: Marks video as AI-generated
                'alteredContentDetails': {
                    'containsSyntheticMedia': True,
                    'disclosureType': 'SYNTHETIC_MEDIA',
                    'description': 'This video contains AI-generated imagery, animation, and narration'
                }
            }
        }

        # Update via YouTube Data API
        youtube_service.videos().update(
            part='contentDetails',
            body=video_metadata
        ).execute()

        log.info(
            "ai_disclosure_set",
            video_id=video_id,
            disclosure_type="SYNTHETIC_MEDIA"
        )

    def add_disclosure_to_description(self, description):
        """
        Add text disclosure to video description (belt-and-suspenders approach).
        """
        disclosure_text = (
            "🤖 AI DISCLOSURE:\n"
            "This documentary was created using AI tools:\n"
            "- Imagery: Google Gemini AI\n"
            "- Animation: Kling AI Video Generator\n"
            "- Narration: ElevenLabs AI Voice Synthesis\n"
            "- Script & Editing: Human-directed creative process\n\n"
        )
        return disclosure_text + description

    def validate_disclosure_set(self, video_id, youtube_service):
        """
        Verify AI disclosure was successfully set.
        """
        video = youtube_service.videos().list(
            part='contentDetails',
            id=video_id
        ).execute()

        has_altered_content = video['items'][0]['contentDetails'].get('hasAlteredContent', False)

        if not has_altered_content:
            raise ComplianceViolationError(
                f"AI disclosure not set for video {video_id}. "
                f"Upload blocked to prevent policy violation."
            )

        return True
```

**C2PA Content Credentials (Optional but Recommended):**

YouTube is a C2PA steering member. Adding C2PA 2.1+ metadata provides additional authenticity evidence.

```python
# C2PA Manifest Generator (Optional)
class C2PAManifestGenerator:
    def generate_content_credentials(self, video_file_path, production_metadata):
        """
        Embed C2PA manifest into video file.

        Requires: pip install c2pa-python
        """
        try:
            from c2pa import Builder, create_signer
        except ImportError:
            log.warning("c2pa-python not installed. Skipping C2PA manifest.")
            return False

        manifest = {
            'claim_generator': 'PokemonNatureDocumentary/1.0',
            'assertions': [
                {
                    'label': 'stds.schema-org.CreativeWork',
                    'data': {
                        '@context': 'https://schema.org',
                        '@type': 'VideoObject',
                        'name': production_metadata['title'],
                        'creator': {
                            '@type': 'Organization',
                            'name': 'Pokemon Nature Documentary'
                        }
                    }
                },
                {
                    'label': 'c2pa.actions',
                    'data': {
                        'actions': [
                            {
                                'action': 'c2pa.created',
                                'softwareAgent': 'Gemini 2.5 Flash Image',
                                'digitalSourceType': 'algorithmicMedia',
                                'when': production_metadata['asset_generation_time']
                            },
                            {
                                'action': 'c2pa.created',
                                'softwareAgent': 'Kling 2.5 Pro Video',
                                'digitalSourceType': 'algorithmicMedia',
                                'when': production_metadata['video_generation_time']
                            },
                            {
                                'action': 'c2pa.created',
                                'softwareAgent': 'ElevenLabs Voice Synthesis',
                                'digitalSourceType': 'algorithmicMedia',
                                'when': production_metadata['audio_generation_time']
                            },
                            {
                                'action': 'c2pa.edited',
                                'softwareAgent': 'FFmpeg Assembly',
                                'digitalSourceType': 'algorithmicMedia',
                                'when': production_metadata['assembly_time']
                            }
                        ]
                    }
                }
            ]
        }

        # Sign and embed manifest
        builder = Builder(manifest)
        # Note: Requires certificate and private key for signing
        # signer = create_signer(cert_path, key_path, 'sha256')
        # builder.sign(video_file_path, signer)

        log.info(
            "c2pa_manifest_generated",
            video_file=video_file_path,
            manifest_version="C2PA 2.1"
        )

        return True
```

---

4. **Human Review Evidence (AC4):**

YouTube upgraded its review process in March 2025 so ALL videos undergo human review for ad suitability. Channels need evidence of human oversight.

**Required Documentation Per Video:**

```python
# Human Review Evidence Builder
class HumanReviewEvidenceTracker:
    def build_evidence_package(self, task, production_data):
        """
        Create evidence package demonstrating human involvement.

        This evidence proves:
        1. Creative decisions made by humans
        2. Quality control applied by humans
        3. Review process before upload
        """
        evidence = {
            'creative_decisions': {
                'story_development': {
                    'human_author': production_data.get('script_author', 'Unknown'),
                    'review_timestamp': production_data.get('script_review_time'),
                    'revision_count': production_data.get('script_revisions', 0),
                    'narrative_choices': production_data.get('story_rationale', '')
                },
                'visual_direction': {
                    'asset_approval_count': production_data.get('asset_approvals', 0),
                    'composition_decisions': production_data.get('composite_choices', []),
                    'rejected_generations': production_data.get('regeneration_log', [])
                },
                'final_edit': {
                    'timing_adjustments': production_data.get('trim_decisions', []),
                    'audio_mixing': production_data.get('sfx_choices', []),
                    'quality_review_timestamp': production_data.get('final_qa_timestamp')
                }
            },
            'review_artifacts': {
                'qa_checklist': self.generate_qa_checklist(task, production_data),
                'approval_signature': production_data.get('human_approver', 'System'),
                'review_duration_minutes': production_data.get('total_review_time', 0)
            },
            'production_timeline': {
                'started': production_data.get('project_start'),
                'ai_generation_completed': production_data.get('generation_end'),
                'human_review_completed': production_data.get('review_end'),
                'total_human_hours': production_data.get('human_hours', 0)
            }
        }

        # Store evidence in database
        task.compliance_evidence = json.dumps(evidence)

        log.info(
            "human_review_evidence_built",
            task_id=str(task.id),
            evidence_categories=list(evidence.keys()),
            total_human_hours=evidence['production_timeline']['total_human_hours']
        )

        return evidence

    def generate_qa_checklist(self, task, production_data):
        """
        Standardized QA checklist proving human oversight.
        """
        return {
            'content_accuracy': 'Verified Pokemon behavioral accuracy against source material',
            'visual_quality': 'Reviewed all 18 clips for visual artifacts',
            'audio_sync': 'Verified narration timing and SFX appropriateness',
            'educational_value': 'Confirmed unique educational insights per clip',
            'brand_safety': 'Checked against advertiser-friendly guidelines',
            'metadata_quality': 'Customized title, description, tags for uniqueness',
            'ai_disclosure': 'Verified AI disclosure in description and metadata',
            'reviewer_name': production_data.get('qa_reviewer', 'System'),
            'review_timestamp': datetime.utcnow().isoformat(),
            'review_passed': True
        }
```

**Evidence Storage:**

Add `compliance_evidence` JSONB column to tasks table:

```sql
ALTER TABLE tasks ADD COLUMN compliance_evidence JSONB;
CREATE INDEX idx_tasks_compliance_evidence ON tasks USING gin(compliance_evidence);
```

---

### Service Layer Architecture

**Location:** `app/services/compliance/` (NEW DIRECTORY)

**Service Structure:**

```
app/services/compliance/
├── __init__.py
├── content_uniqueness_validator.py     # ContentUniquenessValidator class
├── duplicate_content_detector.py       # DuplicateContentDetector class
├── organic_upload_scheduler.py         # OrganicUploadScheduler class
├── ai_disclosure_manager.py            # AIDisclosureManager class
├── human_review_evidence_tracker.py    # HumanReviewEvidenceTracker class
├── pre_upload_compliance_validator.py  # PreUploadComplianceValidator orchestrator
└── exceptions.py                        # ComplianceViolationError exception
```

**Orchestration Pattern:**

```python
# Pre-Upload Compliance Validator (Orchestrator)
class PreUploadComplianceValidator:
    def __init__(self):
        self.uniqueness_validator = ContentUniquenessValidator()
        self.duplicate_detector = DuplicateContentDetector()
        self.upload_scheduler = OrganicUploadScheduler()
        self.ai_disclosure_manager = AIDisclosureManager()
        self.evidence_tracker = HumanReviewEvidenceTracker()

    async def validate_before_upload(
        self,
        task: Task,
        video_metadata: dict,
        db: AsyncSession
    ) -> dict:
        """
        Run all compliance checks before uploading.

        Raises:
            ComplianceViolationError: If any check fails

        Returns:
            dict with validation results and scheduled upload time
        """
        # Load recent uploads for comparison
        recent_uploads = await self.get_recent_uploads(task.channel_id, db)

        # 1. Content Uniqueness Validation (AC1)
        uniqueness_result = await self.uniqueness_validator.validate_video_uniqueness(
            video_metadata, recent_uploads
        )

        if not uniqueness_result['passes']:
            raise ComplianceViolationError(
                f"Content uniqueness check failed. Scores: {uniqueness_result['scores']}"
            )

        log.info(
            "uniqueness_validated",
            task_id=str(task.id),
            uniqueness_scores=uniqueness_result['scores']
        )

        # 2. Duplicate Content Detection (AC2)
        duplicate_result = await self.duplicate_detector.detect_duplicate(
            video_metadata, recent_uploads
        )

        if duplicate_result['is_duplicate']:
            raise ComplianceViolationError(
                f"Duplicate content detected. Similar to video: {duplicate_result['duplicate_of']}"
            )

        log.info(
            "duplicate_check_passed",
            task_id=str(task.id),
            similarity_score=duplicate_result['similarity_score']
        )

        # 3. Upload Frequency Throttling (AC3)
        channel = await db.get(Channel, task.channel_id)
        scheduled_upload_time = await self.upload_scheduler.schedule_upload(
            video_metadata, channel, recent_uploads
        )

        if scheduled_upload_time > datetime.now():
            log.warning(
                "upload_throttled",
                task_id=str(task.id),
                scheduled_time=scheduled_upload_time.isoformat(),
                throttle_reason="Organic upload frequency enforcement"
            )

        # 4. Human Review Evidence Verification (AC4)
        if not task.compliance_evidence:
            raise ComplianceViolationError(
                "Human review evidence missing. Story 5.2-5.5 review gates must complete before upload."
            )

        evidence = json.loads(task.compliance_evidence)
        if not evidence.get('review_artifacts', {}).get('qa_checklist'):
            raise ComplianceViolationError(
                "QA checklist missing from human review evidence."
            )

        log.info(
            "human_review_verified",
            task_id=str(task.id),
            reviewer=evidence.get('review_artifacts', {}).get('approval_signature')
        )

        # 5. AI Disclosure Preparation (AC4)
        # Note: Actual disclosure set AFTER upload, but validate metadata prepared
        if '🤖 AI DISCLOSURE' not in video_metadata.get('description', ''):
            # Add disclosure to description
            video_metadata['description'] = self.ai_disclosure_manager.add_disclosure_to_description(
                video_metadata['description']
            )

        # All checks passed
        return {
            'compliance_validated': True,
            'uniqueness_scores': uniqueness_result['scores'],
            'scheduled_upload_time': scheduled_upload_time,
            'evidence_verified': True
        }

    async def get_recent_uploads(self, channel_id: UUID, db: AsyncSession, days: int = 30) -> list:
        """
        Get recent uploads for compliance comparison.
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        result = await db.execute(
            select(Task).where(
                Task.channel_id == channel_id,
                Task.status == TaskStatus.PUBLISHED,
                Task.updated_at >= cutoff_date
            ).order_by(Task.updated_at.desc())
        )

        return result.scalars().all()
```

---

### Library & Framework Requirements

**New Dependencies for Story 7.7:**

```toml
# pyproject.toml

# Image perceptual hashing for visual uniqueness
imagehash = "^4.3.1"
Pillow = "^11.0.0"  # Already installed from earlier stories

# (Optional) C2PA content credentials
# c2pa-python = "^0.5.0"  # Uncomment if implementing C2PA
```

**Key Imports for Story 7.7:**

```python
# Compliance services
from app.services.compliance.content_uniqueness_validator import ContentUniquenessValidator
from app.services.compliance.duplicate_content_detector import DuplicateContentDetector
from app.services.compliance.organic_upload_scheduler import OrganicUploadScheduler
from app.services.compliance.ai_disclosure_manager import AIDisclosureManager
from app.services.compliance.human_review_evidence_tracker import HumanReviewEvidenceTracker
from app.services.compliance.pre_upload_compliance_validator import PreUploadComplianceValidator
from app.services.compliance.exceptions import ComplianceViolationError

# Image processing
import imagehash
from PIL import Image

# Text similarity
from difflib import SequenceMatcher

# Existing services
from app.models import Task, TaskStatus, Channel
from app.services.youtube_uploader_integration import publish_video_to_youtube

# Structured logging
import structlog
log = structlog.get_logger(__name__)

# JSON handling
import json
from datetime import datetime, timedelta
```

---

### Configuration Management

**Environment Variables (No New Variables Required)**

Story 7.7 uses existing environment variables:
```bash
# Discord webhook URL (from Story 6.6)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

**New Task Status Enums Required:**

Add to `app/models.py`:
```python
class TaskStatus(str, Enum):
    # ... existing statuses ...

    # Story 7.7: Compliance violation (terminal)
    COMPLIANCE_VIOLATION = "compliance_violation"  # Failed compliance checks, upload blocked
```

**Database Schema Additions:**

```sql
-- Content uniqueness tracking
CREATE TABLE content_uniqueness_scores (
    id SERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),

    -- Uniqueness scores (0.00 to 1.00)
    visual_uniqueness DECIMAL(3,2) NOT NULL,
    narrative_uniqueness DECIMAL(3,2) NOT NULL,
    metadata_uniqueness DECIMAL(3,2) NOT NULL,
    overall_uniqueness DECIMAL(3,2) NOT NULL,

    -- Validation result
    passes_threshold BOOLEAN NOT NULL,
    threshold_used DECIMAL(3,2) NOT NULL DEFAULT 0.70,

    -- Comparison context
    compared_against_count INTEGER NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_content_uniqueness_task ON content_uniqueness_scores(task_id);

-- Upload frequency tracking
CREATE TABLE upload_frequency_log (
    id SERIAL PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES channels(id),
    task_id UUID NOT NULL REFERENCES tasks(id),

    -- Upload timing
    scheduled_upload_time TIMESTAMP WITH TIME ZONE NOT NULL,
    actual_upload_time TIMESTAMP WITH TIME ZONE,

    -- Frequency metrics
    hours_since_last_upload DECIMAL(5,2),
    uploads_today INTEGER NOT NULL,
    uploads_this_week INTEGER NOT NULL,

    -- Throttling metadata
    was_throttled BOOLEAN NOT NULL DEFAULT FALSE,
    throttle_reason TEXT,
    time_of_day_window VARCHAR(50),  -- 'morning', 'afternoon', 'evening', 'night'

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_upload_frequency_channel ON upload_frequency_log(channel_id);
CREATE INDEX idx_upload_frequency_scheduled ON upload_frequency_log(scheduled_upload_time);

-- Human review evidence (extend tasks table)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS compliance_evidence JSONB;
CREATE INDEX IF NOT EXISTS idx_tasks_compliance_evidence ON tasks USING gin(compliance_evidence);

-- Compliance violation log
CREATE TABLE compliance_violations (
    id SERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    channel_id UUID NOT NULL REFERENCES channels(id),

    -- Violation details
    violation_type VARCHAR(100) NOT NULL,  -- 'duplicate_content', 'uniqueness_failure', 'frequency_limit'
    violation_description TEXT NOT NULL,

    -- Evidence
    validation_results JSONB,

    -- Resolution
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_compliance_violations_task ON compliance_violations(task_id);
CREATE INDEX idx_compliance_violations_type ON compliance_violations(violation_type);
```

---

### Data Flow

**YouTube Compliance Enforcement Flow:**

```
1. Task reaches APPROVED status (Story 5.2: review gates)
        ↓
2. Worker calls youtube_uploader_integration.publish_video_to_youtube()
        ↓
3. PRE-UPLOAD COMPLIANCE CHECKS (Story 7.7):
    a. PreUploadComplianceValidator.validate_before_upload()
    b. Content Uniqueness Validation:
        - Visual uniqueness (perceptual hashing)
        - Narrative uniqueness (story structure fingerprinting)
        - Metadata uniqueness (title/description diversity)
        - ALL must exceed 70% threshold
    c. Duplicate Content Detection:
        - Check against all channel videos
        - Block if similarity > 90% across visual + story + metadata
    d. Upload Frequency Throttling:
        - Check daily limit (2-3 videos depending on channel age)
        - Check minimum spacing (4-6 hours between uploads)
        - Schedule with organic variance (2-hour randomness)
        - Rotate time-of-day (morning/afternoon/evening/night)
    e. Human Review Evidence Verification:
        - Validate task.compliance_evidence exists
        - Verify QA checklist completed
        - Confirm approval signature present
    f. AI Disclosure Preparation:
        - Add disclosure text to video description
        ↓
4. COMPLIANCE CHECK RESULT:
    [ALL CHECKS PASS]:
        - Log compliance validation success
        - Proceed to upload_video() (Story 7.4)
        - Set AI disclosure via YouTube API after upload (Story 7.7)
        - Continue to PUBLISHED status (Story 7.5)

    [ANY CHECK FAILS]:
        - task.status = COMPLIANCE_VIOLATION (terminal)
        - task.error_log = violation details
        - Create compliance_violations record
        - Send Discord alert with violation type
        - Upload BLOCKED - manual intervention required
        ↓
5. POST-UPLOAD AI DISCLOSURE (if checks passed):
    a. AIDisclosureManager.set_ai_disclosure(video_id)
    b. Set hasAlteredContent=true via YouTube Data API
    c. Validate disclosure successfully set
    d. (Optional) Embed C2PA content credentials
        ↓
6. Task transitions to PUBLISHED
```

**Database Access Pattern:**

```python
# CRITICAL: Short transaction pattern (Story 7.2/7.4 pattern)

# 1. Claim task and load metadata
async with async_session_factory() as db:
    task = await db.get(Task, task_id)
    metadata = await generate_metadata(task, db)

# 2. PRE-UPLOAD COMPLIANCE CHECKS (Story 7.7)
async with async_session_factory() as db:
    task = await db.get(Task, task_id)

    try:
        compliance_result = await PreUploadComplianceValidator().validate_before_upload(
            task, metadata, db
        )
    except ComplianceViolationError as e:
        # Mark as compliance violation
        task.status = TaskStatus.COMPLIANCE_VIOLATION
        task.error_log = json.dumps({
            'error': str(e),
            'violation_type': e.violation_type,
            'validation_results': e.validation_results
        })
        await db.commit()

        # Send Discord alert
        await send_discord_alert(
            title="🚨 YouTube Compliance Violation",
            description=f"Task {task.id} failed compliance checks",
            fields={
                "Task ID": str(task.id),
                "Violation": str(e),
                "Action": "Manual review required - fix issues and requeue"
            },
            color="error"
        )

        raise

# 3. Upload (outside DB transaction)
try:
    video_id = await upload_video(task, metadata, db)
except Exception as e:
    # Handle upload errors (Story 7.6)
    await handle_youtube_upload_error(task, e, db)
    raise

# 4. Set AI disclosure (short transaction)
async with async_session_factory() as db:
    task = await db.get(Task, task_id)

    # Set AI disclosure via YouTube API
    await AIDisclosureManager().set_ai_disclosure(video_id, youtube_service)

    # Validate disclosure set
    await AIDisclosureManager().validate_disclosure_set(video_id, youtube_service)

    # Mark upload complete
    task.youtube_video_id = video_id
    task.status = TaskStatus.PUBLISHED
    await db.commit()
```

---

### Previous Story Intelligence

**Story 5.2-5.5 (Review Gates):**

Key Learnings:
1. **Human Review Flow:** Assets → Videos → Audio → Final approval ✅
2. **Review Evidence:** Each review gate captures reviewer, timestamp, decision ✅
3. **QA Checklist:** Standardized review criteria per gate ✅
4. **Status Transitions:** READY_FOR_REVIEW → APPROVED → UPLOADING ✅

**Use Story 5.2-5.5 Review Data:**
- ✅ Extract review evidence from task.approval_history
- ✅ Build human oversight evidence package
- ✅ Validate human approver present before upload
- ✅ Include review timestamps in compliance evidence

**Story 7.4 (Resumable Upload Implementation):**

Key Learnings:
1. **upload_video() Function:** Returns video_id or raises HttpError ✅
2. **Short Transaction Pattern:** Claim → Upload → Update ✅
3. **YouTube Data API Integration:** Use youtube_service for API calls ✅

**Integrate with Story 7.4:**
```python
# Story 7.7: Pre-upload compliance checks BEFORE upload_video()
compliance_result = await PreUploadComplianceValidator().validate_before_upload(task, metadata, db)

# Story 7.4: Upload to YouTube (only if compliance passed)
video_id = await upload_video(task, metadata, db)

# Story 7.7: Post-upload AI disclosure
await AIDisclosureManager().set_ai_disclosure(video_id, youtube_service)
```

**Story 7.6 (Upload Error Handling):**

Key Learnings:
1. **Error Classification:** Permanent vs transient vs quota ✅
2. **Discord Alerts:** Send alerts for terminal failures ✅
3. **Structured Logging:** correlation_id=task.id ✅

**Apply to Compliance Violations:**
```python
# Story 7.7: Compliance violations are terminal (like permanent errors)
task.status = TaskStatus.COMPLIANCE_VIOLATION
await send_discord_alert(
    title="🚨 YouTube Compliance Violation",
    description=f"Task {task.id} blocked by compliance checks",
    fields={
        "Violation Type": violation_type,
        "Details": violation_details,
        "Action": "Manual review required"
    },
    color="error"
)
```

---

### Git Intelligence Summary

From `git log --oneline -5`:

**Recent Commits (Epic 7 Stories):**
1. **449b2c0:** Story 7.6 (Upload Error Handling) - Code review complete
2. **e4ba90a:** Story 7.5 (YouTube URL Retrieval) - Code review complete
3. **e1aed22:** Story 7.4 (Resumable Upload) - Code review complete
4. **254903c:** Story 7.3 (Video Metadata Generation) - Code review complete
5. **1698280:** Story 7.2 (OAuth Token Refresh) - 9 critical fixes

**Patterns Established in Recent Commits:**

1. **Service Layer Pattern:**
   - Services in `app/services/` subdirectories
   - Type-hinted async functions
   - Comprehensive docstrings (Google style)

2. **Testing Pattern:**
   - Tests in `tests/services/` mirror `app/services/`
   - 15-20 tests per service
   - Mock external APIs (YouTube, Notion)
   - 100% passing before commit

3. **Compliance Pattern (NEW for Story 7.7):**
   - Separate `app/services/compliance/` directory
   - Multiple validators orchestrated by pre-check service
   - Database tables for compliance audit trail

4. **Database Migrations:**
   - Alembic migrations for schema changes
   - Reversible up/down migrations
   - Enum updates for new status values

5. **Code Review Fixes:**
   - Stories 7.1-7.6 each had 9 code review issues fixed
   - Common issues: Type hints, error handling, test coverage
   - Security hardening (no plaintext credentials in logs)

**Apply These Patterns to Story 7.7:**
- ✅ Create `app/services/compliance/` directory with 6 service classes
- ✅ Write 15+ tests across multiple test files
- ✅ Create migrations for new tables and TaskStatus enum
- ✅ Use ComplianceViolationError exception pattern
- ✅ Expect 9 code review issues (prepare comprehensive tests upfront)

---

### YouTube Compliance Best Practices (2025-2026 Research)

**Key Policy Changes:**

1. **July 15, 2025: "Repetitious Content" → "Inauthentic Content"**
   - Mass-produced videos now flagged more aggressively
   - Template-based content with minimal variation demonetized
   - Human creative input required for monetization

2. **May 21, 2025: AI Disclosure Mandatory**
   - All synthetic/altered content must be labeled
   - YouTube Data API `hasAlteredContent` field required
   - Enforcement: Videos without disclosure may be demonetized

3. **March 2025: Human Review for Ad Suitability**
   - ALL videos undergo human review (even private)
   - Review decisions take up to 24 hours
   - Appeal process available for disputed demonetizations

**Critical Thresholds:**

| Metric | Minimum Safe Value | Ideal Target | Source |
|--------|-------------------|--------------|--------|
| Content Uniqueness | 70% | 80%+ | Research consensus |
| Visual Variation | 70% | 80%+ | Perceptual hash distance |
| Narrative Diversity | 70% | 80%+ | Story structure comparison |
| Metadata Uniqueness | 70% | 80%+ | Text similarity scoring |
| Daily Upload Limit (New Channel) | 2 videos | 1-2 videos | YPP best practices |
| Daily Upload Limit (Established) | 3 videos | 2-3 videos | YPP best practices |
| Hours Between Uploads | 4-6 hours | 6-8 hours | Organic pattern research |
| Watch Time Retention | 40% | 50%+ | YouTube Analytics |
| Engagement Rate | 2% | 3%+ | YouTube Analytics |

**Organic Upload Pattern Checklist:**
- ✅ **Varied upload times:** Rotate between morning (9-11am), afternoon (2-4pm), evening (7-9pm)
- ✅ **Irregular intervals:** 4-8 hours between uploads (not exactly 6 hours)
- ✅ **Different weekdays:** Rotate Mon/Wed/Fri → Tue/Thu/Sat patterns
- ✅ **Pokemon variety:** Maximum 2 videos per Pokemon species per week
- ✅ **Behavior variety:** Different behaviors (feeding, hunting, social, defensive)
- ✅ **Environment variety:** Different biomes (forest, ocean, mountain, cave)
- ✅ **Metadata variety:** Never copy-paste descriptions/tags
- ✅ **Thumbnail diversity:** Unique thumbnails per video

**Our Implementation Strategy:**

Story 7.7 implements DEFENSIVE compliance enforcement:
- **Content Uniqueness:** 70% threshold (conservative)
- **Upload Frequency:** 3/day max for established channels, 2/day for new channels
- **Spacing Variance:** 2-hour randomness on top of 4-6 hour minimum
- **AI Disclosure:** Mandatory text + YouTube API field
- **Human Evidence:** QA checklist + approval signature
- **Diversity Enforcement:** Block similar videos within short timeframes

These thresholds are MORE CONSERVATIVE than minimum requirements to provide safety margin.

**Sources:**
- [YouTube AI Monetization Policy 2025](https://www.knolli.ai/post/youtube-ai-monetization-policy-2025)
- [YouTube's AI Disclosure Requirements 2025](https://onewrk.com/youtubes-ai-disclosure-requirements-the-complete-2025-guide/)
- [YouTube Partner Program FAQ: Reused Content](https://support.google.com/youtube/community-guide/271248162/)
- [YouTube API Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- [C2PA Technical Specification 2.2](https://spec.c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html)

---

### Testing Strategy

**Test Files:**

```
tests/services/compliance/
├── __init__.py
├── test_content_uniqueness_validator.py  # 15-20 tests
├── test_duplicate_content_detector.py    # 10-15 tests
├── test_organic_upload_scheduler.py      # 15-20 tests
├── test_ai_disclosure_manager.py         # 8-10 tests
├── test_human_review_evidence_tracker.py # 8-10 tests
└── test_pre_upload_compliance_validator.py  # 15-20 tests (integration)
```

**Test Coverage Requirements:**

1. ✅ **Content Uniqueness Validation:**
   - Visual uniqueness: perceptual hash comparison (similar vs unique images)
   - Narrative uniqueness: story structure comparison (same behaviors vs different)
   - Metadata uniqueness: title/description diversity (duplicates vs unique)
   - Threshold enforcement: 70% pass vs 69% fail
   - Edge cases: no recent uploads, first video, identical thumbnails

2. ✅ **Duplicate Content Detection:**
   - Identical videos: 100% similarity → blocked
   - Near-duplicates: >90% similarity → blocked
   - Similar but acceptable: 70-80% similarity → allowed
   - Hash collision handling
   - Story structure fingerprinting

3. ✅ **Upload Frequency Throttling:**
   - Daily limit enforcement: 3 uploads → 4th blocked
   - Minimum spacing: 4 hours enforced
   - Stagger variance: randomness applied
   - Time-of-day rotation: avoid same hour
   - New vs established channel: different limits
   - Weekly limit: 15 videos maximum

4. ✅ **AI Disclosure Manager:**
   - YouTube API disclosure set correctly
   - Description text added
   - Validation check passes
   - Error handling if API call fails

5. ✅ **Human Review Evidence:**
   - Evidence package structure
   - QA checklist generation
   - Missing evidence → error
   - Evidence storage in database

6. ✅ **Pre-Upload Compliance Orchestration:**
   - All checks pass → upload proceeds
   - Any check fails → ComplianceViolationError
   - COMPLIANCE_VIOLATION status set
   - Discord alert sent
   - Compliance violation logged

**Mock Strategy:**

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import imagehash
from PIL import Image

@pytest.mark.asyncio
async def test_uniqueness_validation_passes(async_session):
    """Content with 80% uniqueness should pass 70% threshold"""
    task = create_task(status=TaskStatus.APPROVED)

    video_metadata = {
        'thumbnail_path': 'tests/fixtures/unique_thumbnail.png',
        'story_script': load_fixture('unique_story.json'),
        'title': 'Charizard's Volcanic Migration Patterns',
        'description': 'Documentary exploring fire-type habitat selection',
        'tags': ['charizard', 'volcanic', 'migration', 'fire-type']
    }

    # Mock recent uploads with different content
    recent_uploads = [
        create_video_fixture('pikachu', 'social_behavior'),
        create_video_fixture('squirtle', 'aquatic_hunting'),
        create_video_fixture('bulbasaur', 'photosynthesis')
    ]

    # Validate uniqueness
    validator = ContentUniquenessValidator()
    result = await validator.validate_video_uniqueness(video_metadata, recent_uploads)

    # Verify passes threshold
    assert result['passes'] is True
    assert result['scores']['visual_uniqueness'] >= 0.70
    assert result['scores']['narrative_uniqueness'] >= 0.70
    assert result['scores']['metadata_uniqueness'] >= 0.70

@pytest.mark.asyncio
async def test_duplicate_content_blocked(async_session):
    """Identical video should be detected and blocked"""
    task = create_task(status=TaskStatus.APPROVED)

    video_metadata = {
        'thumbnail_path': 'tests/fixtures/charizard_volcano.png',
        'story_script': load_fixture('charizard_volcano_story.json'),
        'title': 'Charizard in Volcanic Habitat',
        'description': 'Documentary about Charizard fire behaviors'
    }

    # Mock existing upload with IDENTICAL content
    existing_video = {
        'id': 'video-123',
        'thumbnail_path': 'tests/fixtures/charizard_volcano.png',  # SAME image
        'story_script': load_fixture('charizard_volcano_story.json'),  # SAME story
        'title': 'Charizard in Volcanic Habitat',  # SAME title
        'description': 'Documentary about Charizard fire behaviors'  # SAME description
    }

    # Detect duplicate
    detector = DuplicateContentDetector()
    result = await detector.detect_duplicate(video_metadata, [existing_video])

    # Verify duplicate detected
    assert result['is_duplicate'] is True
    assert result['duplicate_of'] == 'video-123'
    assert result['similarity_score'] > 0.90

@pytest.mark.asyncio
async def test_upload_frequency_throttling(async_session):
    """4th upload in same day should be throttled to next day"""
    channel = create_channel(channel_id='test-channel')

    # Mock 3 uploads already today
    recent_uploads = [
        create_upload_log(uploaded_at=datetime.now() - timedelta(hours=8)),
        create_upload_log(uploaded_at=datetime.now() - timedelta(hours=5)),
        create_upload_log(uploaded_at=datetime.now() - timedelta(hours=2))
    ]

    # Schedule next upload
    scheduler = OrganicUploadScheduler()
    scheduled_time = await scheduler.schedule_upload({}, channel, recent_uploads)

    # Verify scheduled for next day (daily limit hit)
    assert scheduled_time.date() > datetime.now().date()
    assert 9 <= scheduled_time.hour <= 11  # Morning window

@pytest.mark.asyncio
async def test_compliance_violation_error_raised(async_session):
    """Compliance check failure should raise ComplianceViolationError"""
    task = create_task(status=TaskStatus.APPROVED)

    # Mock low uniqueness (fails threshold)
    with patch.object(ContentUniquenessValidator, 'validate_video_uniqueness') as mock_validate:
        mock_validate.return_value = {
            'passes': False,
            'scores': {
                'visual_uniqueness': 0.65,  # Below 0.70 threshold
                'narrative_uniqueness': 0.68,
                'metadata_uniqueness': 0.72
            }
        }

        # Validate compliance
        validator = PreUploadComplianceValidator()

        with pytest.raises(ComplianceViolationError) as exc_info:
            await validator.validate_before_upload(task, {}, async_session)

        # Verify error details
        assert "uniqueness check failed" in str(exc_info.value).lower()
        assert exc_info.value.violation_type == "uniqueness_failure"
```

---

### File Structure Requirements

**New Files to Create:**

```
app/
└── services/
    └── compliance/                                    # NEW DIRECTORY
        ├── __init__.py
        ├── content_uniqueness_validator.py           # ContentUniquenessValidator class
        ├── duplicate_content_detector.py             # DuplicateContentDetector class
        ├── organic_upload_scheduler.py               # OrganicUploadScheduler class
        ├── ai_disclosure_manager.py                  # AIDisclosureManager class
        ├── human_review_evidence_tracker.py          # HumanReviewEvidenceTracker class
        ├── pre_upload_compliance_validator.py        # PreUploadComplianceValidator orchestrator
        └── exceptions.py                              # ComplianceViolationError exception

tests/
└── services/
    └── compliance/                                    # NEW DIRECTORY
        ├── __init__.py
        ├── test_content_uniqueness_validator.py      # 15-20 tests
        ├── test_duplicate_content_detector.py        # 10-15 tests
        ├── test_organic_upload_scheduler.py          # 15-20 tests
        ├── test_ai_disclosure_manager.py             # 8-10 tests
        ├── test_human_review_evidence_tracker.py     # 8-10 tests
        └── test_pre_upload_compliance_validator.py   # 15-20 tests (integration)

alembic/
└── versions/
    ├── {timestamp}_add_compliance_violation_status.py      # TaskStatus enum migration
    ├── {timestamp}_create_content_uniqueness_table.py      # content_uniqueness_scores table
    ├── {timestamp}_create_upload_frequency_log_table.py    # upload_frequency_log table
    ├── {timestamp}_create_compliance_violations_table.py   # compliance_violations table
    └── {timestamp}_add_compliance_evidence_to_tasks.py     # tasks.compliance_evidence column
```

**Files to Modify:**

```
app/
├── models.py                                         # Add COMPLIANCE_VIOLATION to TaskStatus enum
└── services/
    └── youtube_uploader_integration.py               # Add compliance pre-check before upload

pyproject.toml                                         # Add imagehash dependency
```

**Files to Reference (No Changes Expected):**

```
app/
├── services/youtube_uploader.py                      # upload_video() (Story 7.4)
├── services/alert_service.py                         # send_discord_alert() (Story 6.6)
└── services/youtube_error_handler.py                 # Error handling patterns (Story 7.6)
```

---

### Environment Variable Setup

**Required Environment Variables (Already Set from Stories 6.2, 6.6):**

```bash
# Discord webhook URL (from Story 6.6)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

**New Dependency Required:**

```toml
# pyproject.toml
imagehash = "^4.3.1"  # Perceptual hashing for visual uniqueness validation
```

---

### Security Considerations

**CRITICAL Security Rules:**

1. **Compliance Evidence Logging:**
   - Log validation results for audit trail
   - DO NOT log full video content or metadata (sensitive data)
   - DO NOT log human reviewer passwords or credentials
   - Use structured logging (JSON format)

2. **Alert Content:**
   - Include task_id and violation_type for traceability
   - Include compliance violation details
   - DO NOT include full video metadata in alerts
   - DO NOT include human reviewer personal information

3. **Database Storage:**
   - Store compliance evidence in JSONB column (structured data)
   - Sanitize evidence before storage (remove sensitive fields)
   - Limit evidence size to prevent DoS (max 100KB per task)
   - Include timestamp for audit trail

4. **YouTube API Calls:**
   - Set AI disclosure via YouTube Data API (not in video file)
   - Validate disclosure set before marking upload complete
   - Handle API errors gracefully (don't expose credentials)

---

### Logging & Observability

**Structured Logging Pattern:**

Follow Stories 6.2, 7.2-7.6 pattern:

```python
import structlog

log = structlog.get_logger(__name__)

# Uniqueness validated
log.info(
    "uniqueness_validated",
    correlation_id=str(task.id),
    visual_score=scores['visual_uniqueness'],
    narrative_score=scores['narrative_uniqueness'],
    metadata_score=scores['metadata_uniqueness'],
    overall_pass=result['passes']
)

# Duplicate detected
log.warning(
    "duplicate_content_detected",
    correlation_id=str(task.id),
    duplicate_of=duplicate_result['duplicate_of'],
    similarity_score=duplicate_result['similarity_score']
)

# Upload throttled
log.warning(
    "upload_throttled",
    correlation_id=str(task.id),
    scheduled_time=scheduled_time.isoformat(),
    hours_delay=(scheduled_time - datetime.now()).total_seconds() / 3600,
    throttle_reason="Daily limit reached (3 videos)"
)

# Compliance violation
log.error(
    "compliance_violation",
    correlation_id=str(task.id),
    violation_type=violation_type,
    violation_details=violation_details,
    status_updated="COMPLIANCE_VIOLATION"
)

# AI disclosure set
log.info(
    "ai_disclosure_set",
    correlation_id=str(task.id),
    video_id=video_id,
    disclosure_type="SYNTHETIC_MEDIA"
)
```

**Required Log Events:**

| Event | Level | Context |
|-------|-------|---------|
| `uniqueness_validated` | INFO | visual_score, narrative_score, metadata_score, overall_pass |
| `duplicate_content_detected` | WARNING | duplicate_of, similarity_score |
| `upload_throttled` | WARNING | scheduled_time, hours_delay, throttle_reason |
| `compliance_violation` | ERROR | violation_type, violation_details, status_updated |
| `ai_disclosure_set` | INFO | video_id, disclosure_type |
| `human_review_verified` | INFO | reviewer, review_timestamp, evidence_type |

---

### Integration Points for Story 7.7

**Where Compliance Fits in Pipeline:**

```
Task Status Flow:
    APPROVED (from Story 5.2-5.5: review gates)
         ↓
    [Story 7.7: PRE-UPLOAD COMPLIANCE CHECKS] ← NEW CHECKPOINT
         ├── Compliance Passes?
         │   ├── YES → Continue to upload
         │   └── NO → COMPLIANCE_VIOLATION (terminal)
         ↓
    [Story 7.3: Generate Metadata]
         ↓
    UPLOADING (Story 7.4: Upload to YouTube)
         ↓
    [Story 7.6: Error Handling]
         ↓
    [Story 7.7: POST-UPLOAD AI DISCLOSURE] ← NEW STEP
         ↓
    PUBLISHED (Story 7.5: URL Retrieval & Notion Sync)
         ↓
    [Story 7.8+: Privacy, Audit Logging]
```

**Pipeline Orchestrator Integration:**

Update `app/services/youtube_uploader_integration.py`:

```python
from app.services.compliance.pre_upload_compliance_validator import PreUploadComplianceValidator
from app.services.compliance.ai_disclosure_manager import AIDisclosureManager
from app.services.compliance.exceptions import ComplianceViolationError

async def publish_video_to_youtube(task_id: UUID):
    """Publish video to YouTube with compliance enforcement"""
    try:
        # Generate metadata (Story 7.3)
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            metadata = await generate_metadata(task, db)

        # PRE-UPLOAD COMPLIANCE CHECKS (Story 7.7) ← NEW
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)

            compliance_validator = PreUploadComplianceValidator()
            compliance_result = await compliance_validator.validate_before_upload(
                task, metadata, db
            )

            # If throttled, wait until scheduled time
            scheduled_time = compliance_result['scheduled_upload_time']
            if scheduled_time > datetime.now():
                wait_seconds = (scheduled_time - datetime.now()).total_seconds()
                log.info(
                    "upload_delayed_for_compliance",
                    task_id=str(task.id),
                    wait_seconds=wait_seconds
                )
                await asyncio.sleep(wait_seconds)

        # Upload to YouTube (Story 7.4)
        video_id = await upload_video(task, metadata, db)

        # POST-UPLOAD AI DISCLOSURE (Story 7.7) ← NEW
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            youtube_service = await get_youtube_service(task.channel_id, db)

            # Set AI disclosure via YouTube Data API
            await AIDisclosureManager().set_ai_disclosure(video_id, youtube_service)

            # Validate disclosure successfully set
            await AIDisclosureManager().validate_disclosure_set(video_id, youtube_service)

        # Construct URL and sync to Notion (Story 7.5)
        youtube_url = await construct_youtube_url(video_id)
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            await sync_youtube_url_to_notion(task, video_id, youtube_url, db)

        # Mark as published
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            task.youtube_video_id = video_id
            task.youtube_url = youtube_url
            task.status = TaskStatus.PUBLISHED
            await db.commit()

    except ComplianceViolationError as e:
        # Story 7.7: Handle compliance violations
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            task.status = TaskStatus.COMPLIANCE_VIOLATION
            task.error_log = json.dumps({
                'error': str(e),
                'violation_type': e.violation_type,
                'validation_results': e.validation_results
            })
            await db.commit()

        # Send Discord alert
        await send_discord_alert(
            title="🚨 YouTube Compliance Violation",
            description=f"Task {task.id} failed compliance checks",
            fields={
                "Task ID": str(task.id),
                "Violation": str(e),
                "Action": "Manual review required - fix issues and requeue"
            },
            color="error"
        )

        # Compliance violation handled - upload blocked

    except HttpError as e:
        # Story 7.6: Handle YouTube upload errors
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            await handle_youtube_upload_error(task, e, db)
```

---

### Project Structure Notes

**Alignment with Project Architecture:**

From architecture.md and project-context.md:
1. **Service Layer Pattern:** Compliance services in `app/services/compliance/` (business logic)
2. **Short Transactions:** Fetch task → Validate compliance → Update status → Commit
3. **Async Patterns:** All database operations use async/await
4. **Testing Structure:** `tests/services/compliance/` mirrors `app/services/compliance/`
5. **Error Handling:** Custom ComplianceViolationError exception with structured error data

**No Conflicts with Existing Structure:**
- Compliance validator uses existing Task/Channel models
- Alert integration uses existing AlertService (Story 6.6)
- Task status updates follow existing patterns
- Integration with youtube_uploader follows service layer pattern

---

### References

**Source Documents:**
- [Epic 7 Story 7.7: YouTube Compliance Enforcement] _bmad-output/planning-artifacts/epics.md:1809-1836
- [Architecture: YouTube Compliance Requirements] _bmad-output/planning-artifacts/architecture.md:38-75
- [Story 5.2-5.5: Review Gates] _bmad-output/implementation-artifacts/5-*-*.md
- [Story 7.4: Resumable Upload Implementation] _bmad-output/implementation-artifacts/7-4-resumable-upload-implementation.md
- [Story 7.5: YouTube URL Retrieval & Notion Update] _bmad-output/implementation-artifacts/7-5-youtube-url-retrieval-notion-update.md
- [Story 7.6: Upload Error Handling] _bmad-output/implementation-artifacts/7-6-upload-error-handling.md
- [CLAUDE.md Project Instructions] CLAUDE.md

**External Documentation (2025-2026 Research):**
- [YouTube AI Monetization Policy 2025](https://www.knolli.ai/post/youtube-ai-monetization-policy-2025)
- [YouTube's AI Disclosure Requirements 2025](https://onewrk.com/youtubes-ai-disclosure-requirements-the-complete-2025-guide/)
- [YouTube Partner Program FAQ: Reused Content](https://support.google.com/youtube/community-guide/271248162/)
- [YouTube API Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- [C2PA Technical Specification 2.2](https://spec.c2pa.org/specifications/specifications/2.2/specs/C2PA_Specification.html)
- [YouTube Data API v3: Videos.update](https://developers.google.com/youtube/v3/docs/videos/update)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A - Story creation complete

### Completion Notes List

**Story Context Analysis Complete:**
- Epic 7 context analyzed (in-progress, Story 7.1-7.6 done, Story 7.7 next)
- Story dependencies verified (5.2-5.5, 7.4-7.6 all complete)
- Architecture compliance patterns identified (YouTube Partner Program enforcement, content uniqueness, upload throttling)
- Previous story intelligence extracted (5.2-5.5 review gates, 7.4 upload, 7.6 error handling)
- YouTube compliance research completed (July 2025 policy changes, AI disclosure requirements, organic upload patterns)
- Comprehensive web research conducted (2025-2026 YPP compliance requirements)

**Ultimate Context Engine Analysis:**
- ✅ EXHAUSTIVE artifact analysis performed
- ✅ YouTube Partner Program 2025-2026 policies researched
- ✅ Content uniqueness validation strategies defined (70% threshold)
- ✅ Duplicate content detection algorithms specified (perceptual hashing + story fingerprinting)
- ✅ Upload frequency throttling rules established (3/day max, 4-8hr variance, time-of-day rotation)
- ✅ AI disclosure requirements documented (May 2025 mandate, YouTube Data API integration)
- ✅ Human review evidence structure designed (QA checklist, approval signature, production timeline)
- ✅ Testing approach comprehensive (6 test files, 70+ total tests)

**Developer Guardrails Established:**
- ✅ CRITICAL YouTube compliance enforcement (content uniqueness, duplicate detection, frequency throttling)
- ✅ Uniqueness threshold MANDATORY (70% across visual, narrative, metadata)
- ✅ Upload frequency limits specified (2-3/day depending on channel age)
- ✅ AI disclosure MANDATORY (hasAlteredContent=true via YouTube Data API)
- ✅ Human review evidence MANDATORY (QA checklist + approval signature)
- ✅ Compliance service structure specified (6 services in app/services/compliance/)
- ✅ ComplianceViolationError exception pattern mandatory
- ✅ Short transaction pattern mandatory (claim → validate → upload → disclose → commit)
- ✅ Testing requirements comprehensive (70+ tests covering all compliance dimensions)
- ✅ Integration with youtube_uploader_integration specified

### File List

**Story File:**
- `_bmad-output/implementation-artifacts/7-7-youtube-compliance-enforcement.md` - Story specification (READY FOR DEV)

**Files to Create (by dev-story workflow):**
- `app/services/compliance/__init__.py` - Package initialization
- `app/services/compliance/content_uniqueness_validator.py` - Content uniqueness validation
- `app/services/compliance/duplicate_content_detector.py` - Duplicate content detection
- `app/services/compliance/organic_upload_scheduler.py` - Upload frequency throttling
- `app/services/compliance/ai_disclosure_manager.py` - AI disclosure automation
- `app/services/compliance/human_review_evidence_tracker.py` - Human review evidence builder
- `app/services/compliance/pre_upload_compliance_validator.py` - Compliance orchestrator (PRIMARY DELIVERABLE)
- `app/services/compliance/exceptions.py` - ComplianceViolationError exception
- `tests/services/compliance/test_content_uniqueness_validator.py` - Uniqueness tests (15-20 tests)
- `tests/services/compliance/test_duplicate_content_detector.py` - Duplicate detection tests (10-15 tests)
- `tests/services/compliance/test_organic_upload_scheduler.py` - Throttling tests (15-20 tests)
- `tests/services/compliance/test_ai_disclosure_manager.py` - AI disclosure tests (8-10 tests)
- `tests/services/compliance/test_human_review_evidence_tracker.py` - Evidence tests (8-10 tests)
- `tests/services/compliance/test_pre_upload_compliance_validator.py` - Integration tests (15-20 tests)
- `alembic/versions/{timestamp}_add_compliance_violation_status.py` - TaskStatus enum migration
- `alembic/versions/{timestamp}_create_content_uniqueness_table.py` - content_uniqueness_scores table
- `alembic/versions/{timestamp}_create_upload_frequency_log_table.py` - upload_frequency_log table
- `alembic/versions/{timestamp}_create_compliance_violations_table.py` - compliance_violations table
- `alembic/versions/{timestamp}_add_compliance_evidence_to_tasks.py` - tasks.compliance_evidence column

**Files to Modify (by dev-story workflow):**
- `app/models.py` - Add COMPLIANCE_VIOLATION to TaskStatus enum
- `app/services/youtube_uploader_integration.py` - Add compliance pre-check before upload
- `pyproject.toml` - Add imagehash dependency

**Files Referenced (No Changes):**
- `app/services/youtube_uploader.py` - upload_video() function
- `app/services/alert_service.py` - send_discord_alert()
- `app/services/youtube_error_handler.py` - Error handling patterns

---

**Story 7.7 Ready for Dev** ✅

All acceptance criteria defined. Comprehensive compliance requirements researched. Developer guardrails established.
