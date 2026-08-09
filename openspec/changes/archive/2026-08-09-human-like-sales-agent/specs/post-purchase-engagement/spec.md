## Purpose

The system shall send automated follow-up messages after a completed sale to check on delivery, request feedback, and re-engage customers for repeat business, plus re-engage customers who abandoned a conversation or payment within the WhatsApp 24-hour messaging window.

## ADDED Requirements

### Requirement: Post-Sale Follow-Up Scheduling
The system SHALL schedule automated follow-up messages at defined intervals after a sale is completed.

#### Scenario: Sale is completed
- **WHEN** a Sale record is created (payment confirmed)
- **THEN** the system SHALL schedule follow-up messages for Day 1, Day 5, Day 14, and Day 30 after the sale date

#### Scenario: Follow-up messages are sent on schedule
- **WHEN** the scheduled time for a follow-up message arrives
- **THEN** a Celery Beat task SHALL dispatch the appropriate templated message to the customer via WhatsApp

### Requirement: Delivery Check-In (Day 1)
The system SHALL send a delivery check-in message one day after the sale.

#### Scenario: Day 1 check-in sent
- **WHEN** 24 hours have passed since a sale was completed
- **THEN** the system SHALL send a WhatsApp message asking the customer if they received their product and if everything is satisfactory

### Requirement: Feedback Request (Day 5)
The system SHALL send a feedback request 5 days after the sale.

#### Scenario: Day 5 feedback request
- **WHEN** 5 days have passed since a sale was completed
- **THEN** the system SHALL send a WhatsApp message asking the customer for feedback on their purchase and experience

### Requirement: Re-Engagement (Day 14)
The system SHALL send a re-engagement message 14 days after the sale, suggesting complementary products.

#### Scenario: Day 14 re-engagement
- **WHEN** 14 days have passed since a sale was completed
- **THEN** the system SHALL send a WhatsApp message mentioning new stock or accessories related to the customer's previous purchase

### Requirement: Win-Back (Day 30)
The system SHALL send a win-back message 30 days after the sale.

#### Scenario: Day 30 win-back
- **WHEN** 30 days have passed since a sale was completed and the customer has not made another purchase
- **THEN** the system SHALL send a WhatsApp message inviting the customer to browse new products or offering assistance

### Requirement: Abandoned Cart Re-Engagement
The system SHALL send re-engagement messages to customers who received a payment link but did not complete payment, within the WhatsApp 24-hour customer service window.

#### Scenario: Customer receives payment link but does not pay within 2 hours
- **WHEN** a payment link remains pending for 2 hours
- **THEN** the system SHALL send a gentle re-engagement message asking if the customer needs help or has questions about the product

#### Scenario: Customer still does not pay after 6 hours
- **WHEN** a payment link remains pending for 6 hours
- **THEN** the system SHALL send a second re-engagement message offering assistance or suggesting alternatives

#### Scenario: Payment link expires or is paid
- **WHEN** a payment link is paid or expires
- **THEN** the system SHALL cancel any pending re-engagement messages for that link

### Requirement: WhatsApp Template Compliance
The system SHALL use WhatsApp message templates for messages sent outside the 24-hour customer service window.

#### Scenario: Follow-up message outside 24-hour window
- **WHEN** a follow-up message is scheduled more than 24 hours after the customer's last message
- **THEN** the system SHALL send the message using a pre-approved WhatsApp message template

#### Scenario: Re-engagement within 24-hour window
- **WHEN** a re-engagement message is sent within 24 hours of the customer's last message
- **THEN** the system MAY send it as a free-form message without a template

### Requirement: Tenant Follow-Up Configuration
The system SHALL allow tenants to enable or disable the follow-up sequence and configure message content.

#### Scenario: Tenant disables follow-ups
- **WHEN** a tenant disables the post-purchase follow-up feature
- **THEN** no follow-up messages SHALL be scheduled or sent for that tenant's sales

#### Scenario: Tenant customizes follow-up messages
- **WHEN** a tenant provides custom text for a follow-up message template
- **THEN** the system SHALL use the tenant's custom text instead of the platform default
