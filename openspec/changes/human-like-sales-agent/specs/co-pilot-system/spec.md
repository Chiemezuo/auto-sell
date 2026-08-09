## Purpose

The system shall provide a real-time web dashboard where business owners monitor conversations, intervene in bot-customer interactions by taking over or handing back control, approve or edit bot-drafted responses in co-pilot mode, and review full conversation histories.

## ADDED Requirements

### Requirement: Real-Time Conversation Streaming
The system SHALL stream active conversation messages to the owner dashboard via WebSocket in real time.

#### Scenario: New customer message arrives
- **WHEN** a customer sends a message to the business WhatsApp number
- **THEN** the dashboard SHALL display the message in the active conversations list within 2 seconds of receipt

#### Scenario: Bot sends a response
- **WHEN** the bot generates and sends a response to a customer
- **THEN** the dashboard SHALL display the bot's message in the conversation view within 2 seconds

#### Scenario: Multiple concurrent conversations
- **WHEN** multiple customers are messaging simultaneously
- **THEN** each owner connected via WebSocket SHALL receive updates for all conversations belonging to their tenant

### Requirement: Conversation History Review
The system SHALL allow owners to view the complete message history for any past or active conversation.

#### Scenario: Owner opens a conversation
- **WHEN** an owner selects a conversation from the dashboard
- **THEN** the system SHALL display all messages in chronological order, clearly labeled as customer or bot

#### Scenario: Owner reviews an escalated conversation
- **WHEN** an owner receives an escalation alert and opens the conversation
- **THEN** the system SHALL display the last 10 messages of the conversation for immediate context

### Requirement: Owner Take Over Conversation
The system SHALL allow an owner to take over a conversation, stopping the bot from responding and routing messages to the owner.

#### Scenario: Owner takes over an active conversation
- **WHEN** an owner clicks "Take Over" on an active conversation in the dashboard
- **THEN** the system SHALL transition the conversation state to `owner_handling`, stop the bot from generating responses for that conversation, and display a text input for the owner to reply directly

#### Scenario: Customer messages during owner handling
- **WHEN** a customer sends a message while the conversation is in `owner_handling` state
- **THEN** the system SHALL display the message on the owner's dashboard and SHALL NOT invoke the LLM or send an automated bot response

### Requirement: Owner Hand Back to Bot
The system SHALL allow an owner to return a conversation to bot control.

#### Scenario: Owner hands conversation back
- **WHEN** an owner clicks "Hand Back to Bot" on a conversation in `owner_handling` state
- **THEN** the system SHALL transition the conversation back to `active` state and the bot SHALL resume responding to subsequent customer messages

### Requirement: Co-Pilot Draft Review
In co-pilot mode, the bot SHALL generate a draft response and wait for owner approval before sending.

#### Scenario: Bot drafts a response in co-pilot mode
- **WHEN** a conversation is in co-pilot mode and a customer message arrives
- **THEN** the bot SHALL generate a draft response, transition the conversation to `co_pilot_drafting` state, and push the draft to the owner's dashboard for review

#### Scenario: Owner approves bot draft
- **WHEN** an owner clicks "Send" on a bot draft
- **THEN** the system SHALL send the draft as-is to the customer, transition the conversation back to `active`, and log the draft as approved

#### Scenario: Owner edits bot draft
- **WHEN** an owner edits a bot draft and clicks "Send"
- **THEN** the system SHALL send the edited version, store the original draft and edited version for feedback, and transition the conversation back to `active`

#### Scenario: Owner rejects bot draft
- **WHEN** an owner clicks "Skip" or "Reject" on a bot draft
- **THEN** the system SHALL discard the draft, transition the conversation to `owner_handling`, and present a text input for the owner to compose their own response

### Requirement: Co-Pilot Mode Configuration
The system SHALL support per-tenant and per-conversation co-pilot mode configuration.

#### Scenario: Tenant sets co-pilot as default
- **WHEN** a tenant configures their default mode as "co-pilot"
- **THEN** all new conversations SHALL start in co-pilot mode unless explicitly overridden

#### Scenario: Owner overrides co-pilot for a specific conversation
- **WHEN** an owner toggles co-pilot mode off for a specific conversation
- **THEN** that conversation SHALL operate in autonomous mode regardless of the tenant default

#### Scenario: Tenant sets autonomous as default
- **WHEN** a tenant configures their default mode as "autonomous"
- **THEN** all conversations SHALL start in autonomous mode, and the owner may enable co-pilot per conversation via the dashboard

### Requirement: Dashboard Accessibility
The system SHALL provide a web dashboard accessible to tenant owners through the existing `/tenant/` admin interface.

#### Scenario: Owner logs into dashboard
- **WHEN** an authenticated tenant owner navigates to the dashboard
- **THEN** the system SHALL display a WebSocket-connected dashboard showing their tenant's active conversations, key metrics (active chats, pending payments, today's sales), and conversation view

#### Scenario: Unauthenticated access attempt
- **WHEN** an unauthenticated user attempts to access the dashboard
- **THEN** the system SHALL redirect to the login page

### Requirement: New Conversation States
The system SHALL support additional conversation states for owner intervention flows.

#### Scenario: Conversation transitions to owner handling
- **WHEN** an owner takes over a conversation
- **THEN** the conversation state SHALL be `owner_handling` and the `process_message` task SHALL skip LLM processing for that conversation

#### Scenario: Conversation transitions to co-pilot drafting
- **WHEN** the bot generates a draft for owner approval
- **THEN** the conversation state SHALL be `co_pilot_drafting` and further customer messages SHALL be queued until the draft is resolved
