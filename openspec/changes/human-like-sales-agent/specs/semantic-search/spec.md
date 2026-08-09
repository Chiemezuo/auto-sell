## Purpose

The system shall use pgvector embeddings to match customer queries to catalog products by semantic intent, supplementing the existing keyword-based full-text search to handle vague, conceptual, or non-exact-match queries.

## ADDED Requirements

### Requirement: Product Embeddings Generation
The system SHALL generate and store vector embeddings for each product on creation and update.

#### Scenario: New product is created
- **WHEN** a new product is saved with a name and description
- **THEN** the system SHALL generate a vector embedding from the concatenated name and description and store it on the product record

#### Scenario: Product description is updated
- **WHEN** a product's name or description is modified
- **THEN** the system SHALL regenerate the embedding for the updated text

#### Scenario: Product is deleted
- **WHEN** a product is deleted
- **THEN** the embedding SHALL be removed along with the product record

### Requirement: Semantic Query Matching
The system SHALL convert inbound customer messages to embeddings and find semantically similar products.

#### Scenario: Customer sends a conceptual query
- **WHEN** a customer sends a message like "something with a great camera under 100k"
- **THEN** the system SHALL generate an embedding of the query, perform cosine similarity search against the tenant's product embeddings, and return the top N most semantically similar products

#### Scenario: Customer sends an exact product name
- **WHEN** a customer sends a message with an exact product name (e.g., "Samsung A54")
- **THEN** the system SHALL still include semantic search results alongside FTS results, as FTS may also match

### Requirement: Hybrid Search Merging
The system SHALL merge results from semantic search and full-text search into a single ranked result set.

#### Scenario: Both searches return results
- **WHEN** both FTS and semantic search return product matches for a query
- **THEN** the system SHALL merge the results, deduplicate by product ID, and present the combined set to the LLM, preserving the top-ranked results from each method

#### Scenario: Only one search method returns results
- **WHEN** FTS finds no matches but semantic search finds products, or vice versa
- **THEN** the system SHALL return results from whichever method produced matches

#### Scenario: No search method returns results
- **WHEN** neither FTS nor semantic search returns product matches
- **THEN** the system SHALL return an empty product set and the LLM SHALL inform the customer that no matching products were found

### Requirement: Tenant-Scoped Search
The system SHALL scope all semantic searches to the requesting tenant's product catalog.

#### Scenario: Tenant A queries for a product
- **WHEN** Tenant A's customer searches for a product
- **THEN** the system SHALL only consider embeddings from Tenant A's products, not any other tenant's catalog

### Requirement: Search Result Limit
The system SHALL limit search results to a configurable maximum to manage LLM context window usage.

#### Scenario: Many products match a query
- **WHEN** more than 10 products match a query across both search methods
- **THEN** the system SHALL return only the top 10 results to the LLM, prioritizing results that appear in both FTS and semantic results
