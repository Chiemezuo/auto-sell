## Purpose

The system shall support multiple LLM providers (DeepSeek, OpenAI, Anthropic) behind a common interface, with per-tenant provider selection and separate model routing for lightweight classification tasks versus full response generation.

## ADDED Requirements

### Requirement: Pluggable LLM Provider Interface
The system SHALL provide an abstract base interface that all LLM providers implement, with methods for chat completion and text classification.

#### Scenario: Provider implements the interface
- **WHEN** a new LLM provider is added to the system
- **THEN** it SHALL implement `chat(messages, tools, **kwargs)` returning a structured response with content and tool calls, and `classify(text, labels)` returning label probabilities

#### Scenario: System uses a provider through the interface
- **WHEN** the system calls an LLM operation
- **THEN** it SHALL interact only through the abstract interface, never through provider-specific APIs directly

### Requirement: Multi-Provider Support
The system SHALL support DeepSeek, OpenAI, and Anthropic as concrete LLM provider implementations.

#### Scenario: Tenant uses DeepSeek
- **WHEN** a tenant is configured to use the DeepSeek provider
- **THEN** all LLM calls for that tenant SHALL be routed through the DeepSeek API using the tenant's configured API key

#### Scenario: Tenant uses OpenAI
- **WHEN** a tenant is configured to use the OpenAI provider
- **THEN** all LLM calls for that tenant SHALL be routed through the OpenAI API using the tenant's configured API key

#### Scenario: System adds a new provider
- **WHEN** a new LLM provider implementation is added to the codebase
- **THEN** it SHALL be available for tenant selection without changes to the conversation processing logic

### Requirement: Per-Tenant Provider Configuration
The system SHALL allow each tenant to select their preferred LLM provider.

#### Scenario: Tenant selects a provider
- **WHEN** a tenant's LLM provider preference is set in their configuration
- **THEN** the system SHALL use that provider for all LLM calls for that tenant

#### Scenario: Tenant has no provider configured
- **WHEN** a tenant has no LLM provider configured
- **THEN** the system SHALL use the platform default provider configured at the Django settings level

### Requirement: Two-Tier Model Routing
The system SHALL route classification tasks (sentiment, intent detection) to a lightweight model and response generation tasks to a primary model.

#### Scenario: Inbound message classification
- **WHEN** a customer message arrives and needs sentiment/intent classification
- **THEN** the system SHALL use the lightweight classification model (e.g., DeepSeek lite or equivalent) configured for that tenant

#### Scenario: Response generation
- **WHEN** the system needs to generate a customer-facing response
- **THEN** the system SHALL use the primary generation model (e.g., deepseek-chat, gpt-4o) configured for that tenant

### Requirement: Provider Failure Handling
The system SHALL handle LLM provider failures with retry and fallback logic.

#### Scenario: Primary provider fails temporarily
- **WHEN** the LLM provider returns a transient error (rate limit, timeout)
- **THEN** the system SHALL retry up to 3 times with exponential backoff before returning an error

#### Scenario: Provider configured with fallback
- **WHEN** the primary provider fails after all retries and a fallback provider is configured
- **THEN** the system SHALL attempt the same call using the fallback provider before failing

#### Scenario: No fallback configured
- **WHEN** the primary provider fails after all retries and no fallback is configured
- **THEN** the system SHALL log the error and, for customer-facing calls, send an appropriate "technical difficulty" message to the customer
