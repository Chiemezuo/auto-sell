## Purpose

The bot shall engage customers through structured conversation phases (Greeting, Discovery, Recommendation, Negotiation, Close), adapt its communication style per tenant personality configuration, classify inbound message sentiment, and select appropriate system prompts based on phase and sentiment context.

## ADDED Requirements

### Requirement: Conversation Phase Tracking
The system SHALL track each conversation's current phase and transition between phases based on conversation progress and customer signals.

#### Scenario: New customer sends a greeting
- **WHEN** a customer sends a greeting message ("hi", "hello", "good morning") to a new conversation
- **THEN** the system SHALL set the conversation phase to `greeting` and the bot SHALL respond with a welcome message that introduces the business and asks what the customer is looking for

#### Scenario: Customer sends vague product query
- **WHEN** a customer sends a message that does not clearly identify a product category or name (e.g., "something nice", "a good phone")
- **THEN** the system SHALL transition to `discovery` phase and the bot SHALL ask 1-2 qualifying questions about budget, preferences, or use case before recommending products

#### Scenario: Customer sends a specific product query
- **WHEN** a customer sends a message with clear product intent (e.g., "do you have iPhone 14")
- **THEN** the system SHALL transition to `recommendation` phase and the bot SHALL present matching products with key specs and prices

#### Scenario: Customer negotiates on price
- **WHEN** a customer makes a counter-offer or asks for a discount
- **THEN** the system SHALL transition to `negotiation` phase

#### Scenario: Customer agrees to buy
- **WHEN** a customer expresses intent to purchase ("I'll take it", "how do I pay", "send the link")
- **THEN** the system SHALL transition to `close` phase and the bot SHALL call the generate_payment_link tool

### Requirement: Per-Tenant Personality Configuration
The system SHALL allow each tenant to configure the bot's communication personality, including tone, formality level, and emoji usage.

#### Scenario: Tenant selects casual personality
- **WHEN** a tenant configures their bot personality as "casual"
- **THEN** the bot SHALL use informal language, contractions, and occasional emojis in customer conversations

#### Scenario: Tenant selects professional personality
- **WHEN** a tenant configures their bot personality as "professional"
- **THEN** the bot SHALL use formal language, avoid emojis, and maintain a business-like tone

#### Scenario: Tenant configures emoji usage level
- **WHEN** a tenant sets emoji usage to "none"
- **THEN** the bot SHALL not use any emojis in any customer messages

### Requirement: Sentiment-Aware Message Routing
The system SHALL classify the sentiment of each inbound customer message and adjust bot behavior accordingly.

#### Scenario: Customer expresses frustration
- **WHEN** a customer sends a message indicating frustration or anger ("this is too expensive", "you're not helping")
- **THEN** the system SHALL select a de-escalation prompt that prioritizes empathy, alternative suggestions, and escalation to owner if the customer remains unsatisfied

#### Scenario: Customer expresses excitement
- **WHEN** a customer sends a message indicating excitement ("I love it!", "perfect!")
- **THEN** the system SHALL accelerate toward the close phase by confirming the selection and offering the payment link

#### Scenario: Customer expresses hesitation
- **WHEN** a customer sends a message indicating hesitation ("let me think about it", "maybe later")
- **THEN** the bot SHALL address potential concerns by asking what is holding them back and offering additional information or alternatives

### Requirement: Greeting Phase Behavior
When a conversation begins, the bot SHALL orient the customer before presenting products.

#### Scenario: First message in a new conversation
- **WHEN** the first customer message arrives in a new conversation
- **THEN** the bot SHALL respond with a welcome that includes the business name, a brief overview of product categories available, and an open-ended question inviting the customer to describe what they need

#### Scenario: Returning customer after conversation ended
- **WHEN** a returning customer messages after their previous conversation was completed or abandoned
- **THEN** the bot SHALL acknowledge the return, reference the previous interaction if context is available, and ask how it can help

### Requirement: Discovery Phase Behavior
When customer intent is vague, the bot SHALL ask qualifying questions before recommending products.

#### Scenario: Customer says "I need something"
- **WHEN** a customer sends a message with no specific product indicators
- **THEN** the bot SHALL NOT immediately search the catalog but SHALL respond with 1-2 questions about what type of product, budget range, or purpose

#### Scenario: Discovery phase identifies intent
- **WHEN** the customer responds to discovery questions with clear preferences
- **THEN** the system SHALL transition to recommendation phase and present matching products

### Requirement: Multi-Message Sequence Dispatch
The bot SHALL be able to send messages as a sequence of short messages with natural delays, rather than a single long message.

#### Scenario: Product recommendation with multiple items
- **WHEN** the bot needs to present 3 product recommendations
- **THEN** the system SHALL dispatch them as separate short messages with configurable delays (1-3 seconds) between each message

#### Scenario: Long response split for WhatsApp readability
- **WHEN** a bot response exceeds 500 characters
- **THEN** the system SHALL split it into multiple messages dispatched sequentially

### Requirement: Graceful Non-Text Message Handling
The system SHALL respond to non-text WhatsApp messages with message-type-specific, friendly responses.

#### Scenario: Customer sends an image
- **WHEN** a customer sends an image message
- **THEN** the bot SHALL reply acknowledging the image was received, explaining it cannot view images yet, and inviting the customer to describe what they are looking for in text

#### Scenario: Customer sends a voice note
- **WHEN** a customer sends a voice message
- **THEN** the bot SHALL reply acknowledging the voice note was received, explaining it can only process text, and inviting the customer to type their question

### Requirement: Rate Limit Graceful Messaging
The system SHALL respond to rate-limited customers with friendly, human-like messages instead of abrupt directives.

#### Scenario: Customer exceeds rate limit
- **WHEN** a customer exceeds the per-minute message rate limit
- **THEN** the bot SHALL send a friendly message asking them to slow down, using warm language (e.g., "Whoa, you're faster than I can type! 😅 Give me a moment — what were you looking for?")
