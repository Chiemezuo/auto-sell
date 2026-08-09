## Purpose

The bot shall use human-like sales techniques during price negotiation, including social proof, scarcity signals, product bundling, price anchoring, cross-sell suggestions, and alternative product recommendations, instead of binary within-range price acceptance.

## ADDED Requirements

### Requirement: Social Proof in Product Descriptions
The bot SHALL incorporate social proof when presenting or defending a product's value, using actual sales data from the tenant.

#### Scenario: Product is a best-seller
- **WHEN** presenting a product that has the highest sale count for the tenant in the last 30 days
- **THEN** the bot SHALL mention that it is a popular or best-selling item in natural language (e.g., "this is actually our most popular phone this month")

#### Scenario: Product has no sales data
- **WHEN** presenting a product with no prior sales
- **THEN** the bot SHALL NOT fabricate social proof or mention popularity

### Requirement: Scarcity-Based Urgency
The bot SHALL use actual stock quantity data to create legitimate urgency when stock is low.

#### Scenario: Product has 3 or fewer units
- **WHEN** a product's stock_quantity is 3 or fewer and the customer is in negotiation or recommendation phase
- **THEN** the bot SHALL mention the limited stock as a natural part of the conversation (e.g., "only a few left")

#### Scenario: Product has ample stock
- **WHEN** a product's stock_quantity is more than 3
- **THEN** the bot SHALL NOT mention scarcity or imply urgency based on stock levels

### Requirement: Product Bundling
The bot SHALL offer bundle deals when a customer is purchasing a primary item that has complementary products.

#### Scenario: Customer buying a phone
- **WHEN** a customer agrees to purchase a phone and the tenant has accessories (cases, screen protectors, chargers) in the catalog
- **THEN** the bot SHALL suggest adding an accessory with a small discount on the combined price

#### Scenario: No complementary products exist
- **WHEN** a customer buys a product with no related items in the catalog
- **THEN** the bot SHALL NOT suggest a bundle

### Requirement: Price Anchoring
The bot SHALL use the asking_price as an anchor and negotiate downward to floor_price, making the customer feel they received a favorable deal.

#### Scenario: Customer makes offer above floor_price
- **WHEN** a customer offers a price that is above the product's floor_price
- **THEN** the bot SHALL not immediately accept but SHALL push back slightly before accepting, to create the perception of a negotiated deal

#### Scenario: Customer makes offer below floor_price
- **WHEN** a customer offers a price below the product's floor_price
- **THEN** the bot SHALL decline warmly, counter with a price above floor_price, and may mention product value or features to justify the price

### Requirement: Alternative Product Suggestions
When a product exceeds a customer's budget, the bot SHALL suggest similar but more affordable alternatives.

#### Scenario: Customer budget below targeted product
- **WHEN** a customer's stated budget is below the floor_price of the product they are interested in and negotiation fails
- **THEN** the bot SHALL search for products in the same category within the customer's budget and suggest them as alternatives

#### Scenario: No alternatives within budget
- **WHEN** no products in the same category are within the customer's budget
- **THEN** the bot SHALL inform the customer honestly and may suggest they check back later or offer to notify them of new stock

### Requirement: Cross-Sell and Upsell
The bot SHALL suggest higher-value or complementary products at appropriate moments in the conversation.

#### Scenario: Customer viewing a product with a premium variant
- **WHEN** a customer shows interest in a product and a higher-spec variant exists in the catalog
- **THEN** the bot SHALL mention the premium variant with its key advantages and price difference

#### Scenario: No up-sell opportunity
- **WHEN** no higher-tier or complementary products exist for the item the customer is viewing
- **THEN** the bot SHALL NOT fabricate or force an upsell

### Requirement: Floor Price Confidentiality
The bot SHALL never reveal the floor_price to the customer under any circumstances.

#### Scenario: Customer directly asks for the lowest price
- **WHEN** a customer asks "what's your lowest price" or "what's the best you can do"
- **THEN** the bot SHALL respond with a price above floor_price without disclosing the floor value

#### Scenario: Customer presses for the absolute minimum
- **WHEN** a customer repeatedly demands the lowest possible price
- **THEN** the bot SHALL hold firm at a price above floor_price or escalate to the owner if the customer becomes frustrated
