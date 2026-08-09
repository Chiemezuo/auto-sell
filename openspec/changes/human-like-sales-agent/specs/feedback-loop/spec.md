## Purpose

The system shall allow business owners to rate bot responses (thumbs up/down) and edit bot messages, storing feedback with conversation context snapshots and prompt version tracking for future prompt improvement and model fine-tuning.

## ADDED Requirements

### Requirement: Bot Message Rating
The system SHALL allow owners to rate individual bot messages as good or bad.

#### Scenario: Owner rates a bot message as good
- **WHEN** an owner clicks thumbs-up on a bot message in the dashboard or conversation review
- **THEN** the system SHALL store a feedback record with type "good", linked to the bot message, conversation, and tenant, including a snapshot of the last 5 conversation messages and the prompt version that generated the response

#### Scenario: Owner rates a bot message as bad
- **WHEN** an owner clicks thumbs-down on a bot message in the dashboard
- **THEN** the system SHALL store a feedback record with type "bad", linked to the bot message, conversation, and tenant, including a context snapshot and prompt version

### Requirement: Owner-Edited Response Capture
The system SHALL capture owner-edited bot responses as corrected versions for learning.

#### Scenario: Owner edits and sends a bot draft
- **WHEN** an owner edits a bot draft before sending it to the customer
- **THEN** the system SHALL store both the original draft and the edited version in the feedback record with type "edited"

#### Scenario: Owner sends an edited message without draft mode
- **WHEN** an owner manually edits a previously-sent bot message via the dashboard (if supported)
- **THEN** the system SHALL store the original bot message and the owner's corrected version

### Requirement: Feedback Data Model
The system SHALL store feedback in a structured data model for future analysis.

#### Scenario: Feedback record created
- **WHEN** any feedback action (rate or edit) occurs
- **THEN** the system SHALL persist a record containing: feedback type, conversation reference, bot message reference, tenant reference, context snapshot (last 5 messages as JSON), prompt version identifier, optional owner note, optional edited response text, and creation timestamp

#### Scenario: Multiple feedback entries on same message
- **WHEN** an owner provides feedback on a message that already has a feedback record
- **THEN** the system SHALL update the existing record rather than creating a duplicate

### Requirement: Prompt Version Tracking
The system SHALL track which prompt version generated each bot response to enable correlation with feedback.

#### Scenario: Bot message includes prompt version
- **WHEN** the bot generates a response
- **THEN** the system SHALL store the active prompt version identifier on the Message record

#### Scenario: Feedback analysis groups by prompt version
- **WHEN** viewing feedback analytics grouped by prompt version
- **THEN** the system SHALL be able to correlate feedback ratings with specific prompt versions to identify which prompts perform better

### Requirement: Feedback Visibility
The system SHALL display feedback status in the conversation view.

#### Scenario: Owner sees feedback on a message
- **WHEN** viewing a conversation with previously-rated messages
- **THEN** the dashboard SHALL visually indicate which messages have been rated (thumbs-up or thumbs-down icon)
