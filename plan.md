# MASTER PLANNING PROMPT
# ChandlerOS — Production-Grade AI Portfolio Agent

You are acting as a Principal AI Architect and Staff AI Engineer.

I am NOT asking you to build this system.

I am NOT asking you to write implementation code.

I am NOT asking you to create files or start development.

Your ONLY task is to produce an extremely detailed technical blueprint for the system described below.

The blueprint will later be used as the master engineering specification from which the project will be implemented.

============================================================
PROJECT
============================================================

I want to build an AI agent embedded into my personal portfolio website.

The agent should be capable of answering essentially any reasonable question about my portfolio, work, projects, research, writing, technical experience, education, skills, and related information.

However, this is intentionally much more ambitious than a normal "portfolio chatbot."

The project itself is intended to demonstrate that I understand modern AI engineering end-to-end.

I want to use the project as the foundation for a comprehensive technical blog series explaining how production LLM systems are designed, evaluated, deployed, optimized, secured, and operated.

The final system should therefore demonstrate:

- Knowledge engineering
- Knowledge graphs
- Graph RAG
- Vector RAG
- Hybrid RAG
- Query understanding
- Context engineering
- Agentic workflows where justified
- LLM gateways
- Model routing
- Multi-provider inference
- Free-tier LLM infrastructure
- Rate limiting
- Abuse prevention
- Caching
- Semantic caching
- Token optimization
- Retries
- Timeouts
- Circuit breakers
- Graceful degradation
- Personality engineering
- Structured outputs
- Grounding
- Hallucination prevention
- Prompt injection defense
- Evaluation
- Golden datasets
- LLM-as-a-judge
- Regression testing
- Prompt versioning
- Model versioning
- Knowledge versioning
- Observability
- Distributed tracing
- Cost tracking
- CI/CD
- Production deployment
- Reliability engineering
- Incident handling

The target is to operate this system for approximately $0/month at normal personal-portfolio traffic using legitimate free tiers and open-source technologies.

Do not assume paid infrastructure.

============================================================
CORE PRODUCT
============================================================

The final product is a conversational AI assistant for my portfolio.

It should answer questions about:

- Who I am
- Education
- Work experience
- Companies
- Roles
- Projects
- Research
- Publications
- Books
- Blog posts
- Skills
- Technologies
- Programming languages
- AI/ML experience
- Agentic AI work
- Evaluation work
- Engineering philosophy
- Projects and their relationships
- Lessons learned
- Technical decisions
- Other information explicitly present in the portfolio knowledge base

Examples:

"What projects have you built using LLMs?"

"How does your ML book relate to your current AI work?"

"Which projects demonstrate agentic AI experience?"

"What technologies have you used across your projects?"

"What research have you done around evaluation?"

"Tell me about Harshith's experience with AI."

"Which projects use Python?"

"What connects project X and project Y?"

The system must strongly prefer factual correctness over making up an answer.

If information is not present in the trusted knowledge base, the agent should say that it does not have enough information rather than hallucinating.

============================================================
PERSONALITY
============================================================

The default personality is ChandlerOS.

The assistant should have a recognizable witty, dry, conversational, self-deprecating sitcom-inspired personality.

However, personality must NOT be implemented as:

"Just tell the LLM to talk like Chandler."

Instead, design personality as an independent controllable layer.

Separate:

WHAT THE AGENT KNOWS

from:

HOW THE AGENT SPEAKS.

The personality layer should work regardless of which underlying LLM provider/model is being used.

The architecture should allow different providers to produce substantially similar personality characteristics.

Define a personality policy containing dimensions such as:

- Humor
- Sarcasm
- Warmth
- Self-deprecation
- Formality
- Directness
- Conversationality
- Rhetorical-question frequency
- Sentence length
- Punchline frequency
- Emotional sensitivity

Personality must be context-dependent.

For example:

Technical question:
    high clarity
    moderate humor

Casual question:
    more humor

User frustration:
    lower sarcasm
    higher warmth

Serious topic:
    very low humor
    high empathy

The personality must never introduce unsupported facts.

============================================================
KNOWLEDGE ARCHITECTURE
============================================================

The canonical representation of my portfolio knowledge should be a Knowledge Graph.

The portfolio is highly structured and contains relationships between entities.

Do not treat the entire portfolio as unrelated text chunks.

Design an explicit graph model.

Potential entities:

- Person
- Organization
- Company
- Role
- Education
- Degree
- Project
- Publication
- Book
- Blog
- Research Topic
- Skill
- Technology
- Programming Language
- Framework
- Dataset
- Model
- Achievement
- Certification
- Event
- Concept

Potential relationships:

- WORKED_AT
- AUTHORED
- BUILT
- USES
- DEMONSTRATES
- STUDIED
- RESEARCHES
- PUBLISHED
- TEACHES
- RELATED_TO
- IMPLEMENTED_WITH
- DEPENDS_ON
- INSPIRED_BY
- PART_OF
- CONTRIBUTED_TO
- LEARNED_FROM

Every important relationship should ideally have provenance.

Example conceptually:

Project A
    --USES-->
Python

Evidence:
    portfolio_project_a.md
    section 3

The plan must explain:

- Graph schema
- Entity schema
- Relationship schema
- Evidence/provenance model
- Entity resolution
- Versioning
- Conflict handling
- Confidence
- Graph validation

============================================================
GRAPH RAG
============================================================

Graph RAG should be the primary mechanism for structured portfolio questions.

Design the complete Graph RAG pipeline:

USER QUERY
    ↓
Query understanding
    ↓
Entity identification
    ↓
Entity resolution
    ↓
Graph traversal
    ↓
Relevant subgraph
    ↓
Evidence retrieval
    ↓
Context construction
    ↓
LLM generation

The system should support multi-hop questions.

Example:

"What projects demonstrate both ML and agentic AI?"

Potential traversal:

Agentic AI
    ↓
related projects
    ↓
projects
    ↓
technology relationships
    ↓
ML
    ↓
evidence

Do not send the entire graph to the LLM.

Explain how relevant subgraphs should be selected.

============================================================
VECTOR RAG
============================================================

Graph RAG should NOT replace semantic retrieval.

Design a hybrid architecture using:

Graph RAG
+
Vector RAG

Vector RAG should handle:

- Long-form writing
- Blog posts
- Book content
- Research
- README files
- Project descriptions
- Documentation
- Semantic/fuzzy questions

Explain:

- Chunking strategy
- Chunk size
- Overlap
- Metadata
- Embeddings
- Retrieval
- Reranking
- Filtering
- Citation/evidence linking

Then explain how Graph RAG and Vector RAG should work together.

============================================================
HYBRID RETRIEVAL
============================================================

Design a retrieval router.

It should determine whether a query requires:

GRAPH ONLY

VECTOR ONLY

GRAPH + VECTOR

Potential query classes:

- Simple fact
- Entity lookup
- Relationship question
- Multi-hop question
- Semantic question
- Blog question
- Research question
- Project question
- General question

Explain how the system should decide which retrieval strategy to use.

Avoid unnecessary LLM calls.

Use deterministic routing wherever practical.

============================================================
KNOWLEDGE INGESTION
============================================================

Design an offline knowledge ingestion pipeline.

Potential sources:

- Portfolio website
- Resume
- Blog posts
- Project repositories
- README files
- Book
- Research documents
- Manually curated facts

Pipeline:

RAW SOURCES
    ↓
Parsing
    ↓
Cleaning
    ↓
Normalization
    ↓
Entity extraction
    ↓
Relationship extraction
    ↓
Entity resolution
    ↓
Graph construction
    ↓
Evidence linking
    ↓
Chunking
    ↓
Embedding generation
    ↓
Validation
    ↓
Knowledge release

Explain which parts should be deterministic and which can use LLMs.

============================================================
KNOWLEDGE VERSIONING
============================================================

The knowledge base must be versioned.

Example:

knowledge_version = 2026.08.x

Whenever portfolio content changes:

Source changes
    ↓
Ingestion
    ↓
Graph regeneration/update
    ↓
Embedding update
    ↓
Validation
    ↓
Evaluation
    ↓
Knowledge release

Explain:

- Version strategy
- Rollbacks
- Diffing knowledge releases
- Detecting broken relationships
- Regression testing knowledge

============================================================
LLM GATEWAY
============================================================

Design a provider-agnostic LLM gateway.

The application must NOT directly depend on a specific provider.

Architecture:

Application
    ↓
LLM Gateway
    ↓
Model Router
    ↓
Provider Adapter
    ↓
LLM Provider

Potential providers may include legitimate free-tier providers such as:

- Google Gemini
- Groq
- Hugging Face inference
- Other legitimate free providers

Do NOT design systems around abusing free APIs or violating provider terms.

Explain:

- Provider abstraction
- Common request/response interface
- Provider adapters
- Error normalization
- Streaming
- Token accounting
- Provider metadata

============================================================
MODEL ROUTING
============================================================

Do not use simplistic:

"Provider A → Provider B → Provider C"

routing.

Design a real model router.

Consider:

- Provider availability
- Model capability
- Task complexity
- Latency
- Context window
- Rate limits
- Current quota
- Quality
- Cost
- Historical performance

Example:

Simple factual query
    → fast model

Complex multi-hop query
    → stronger model

Provider unhealthy
    → alternate provider

All providers unavailable
    → fallback system

Explain the routing policy in detail.

============================================================
PROVIDER HEALTH
============================================================

Design provider health monitoring.

Track:

- Success rate
- Error rate
- 429s
- 5xx
- Timeouts
- Latency
- Quota exhaustion

Design a circuit breaker:

CLOSED
    ↓
Failures
    ↓
OPEN
    ↓
Cooldown
    ↓
HALF OPEN
    ↓
Healthy → CLOSED
Unhealthy → OPEN

Explain thresholds, cooldowns, recovery and observability.

============================================================
RETRIES
============================================================

Design retry behavior.

Explain:

- Which errors should retry
- Which errors should not retry
- Exponential backoff
- Jitter
- Retry limits
- Deadline propagation
- Interaction with circuit breakers

============================================================
TIMEOUTS
============================================================

Design timeout budgets for:

- Query processing
- Graph retrieval
- Vector retrieval
- Reranking
- LLM calls
- Entire request

Explain how total latency should be budgeted.

============================================================
RATE LIMITING
============================================================

Design multi-layer rate limiting.

Include:

- IP rate limiting
- Anonymous session rate limiting
- Burst limits
- Concurrency limits
- Global request budget
- Provider-specific budget

Initial conceptual values may be:

IP:
10 requests/minute

Burst:
3 requests/10 seconds

Session:
30 requests/hour

But these are configurable starting points.

Explain the weaknesses of IP-only rate limiting.

============================================================
ABUSE PREVENTION
============================================================

Design protection against:

- Bots
- Spam
- Automated scraping
- Extremely long prompts
- Prompt flooding
- Provider quota abuse
- Context exhaustion
- Prompt injection
- Malicious requests

Explain:

- Input limits
- Request limits
- Concurrency
- Bot protection
- Abuse heuristics
- Safe degradation

============================================================
CACHING
============================================================

Design multiple caching layers.

Include:

- Static knowledge cache
- Retrieval cache
- Response cache
- Semantic cache
- Provider health cache

Explain when caching is safe and when it is not.

Pay particular attention to conversational context.

============================================================
SEMANTIC CACHING
============================================================

Design a semantic cache for repeated portfolio questions.

Example:

"What projects have you built with Python?"

and:

"Which of your projects use Python?"

may potentially reuse the same answer.

Explain:

- Similarity threshold
- Cache key
- Metadata
- Context sensitivity
- Expiration
- Invalidation
- Safety considerations

============================================================
TOKEN OPTIMIZATION
============================================================

Design a context budget system.

Account for:

- System prompt
- Personality policy
- Graph context
- Vector context
- Conversation history
- User query
- Output budget

Explain:

- Context prioritization
- Evidence ranking
- Compression
- Summarization
- Deduplication
- Truncation
- Model-specific limits

============================================================
CONVERSATION MEMORY
============================================================

Separate:

SHORT-TERM CONVERSATION MEMORY

from:

LONG-TERM PORTFOLIO KNOWLEDGE.

Short-term:

- Recent turns
- Conversation summary

Long-term:

- Portfolio graph
- Documents

Do not mix user conversation with trusted portfolio facts.

Explain how memory should affect retrieval and caching.

============================================================
CONTEXT ENGINEERING
============================================================

Design a dedicated Context Builder.

Inputs:

- User query
- Graph results
- Vector results
- Conversation state
- Personality policy

Outputs:

- Grounded context
- Evidence
- Metadata
- Token-budgeted prompt context

Explain:

- Evidence ranking
- Deduplication
- Conflict resolution
- Provenance
- Context prioritization

============================================================
GROUNDING
============================================================

Design a grounding mechanism.

The system must prevent statements like:

"Harshith worked at X"

if the knowledge base does not support that claim.

Design:

LLM response
    ↓
Claim identification
    ↓
Knowledge verification
    ↓
Supported?
    ├── yes → allow
    └── no → regenerate/remove/fallback

Explain how strict this mechanism should be.

============================================================
PROMPT INJECTION
============================================================

Design a prompt injection defense architecture.

Retrieved knowledge must be treated as DATA.

It must never become instructions.

Separate:

SYSTEM INSTRUCTIONS
TRUSTED KNOWLEDGE
USER INPUT

Explain:

- Injection detection
- Context delimiting
- Instruction hierarchy
- Tool restrictions
- Output validation

============================================================
OUTPUT VALIDATION
============================================================

Design a post-generation validation layer.

Check:

- Factuality
- Grounding
- Safety
- Personality consistency
- Length
- Schema
- Evidence
- Unsupported claims

Explain what should happen if validation fails.

============================================================
STRUCTURED OUTPUT
============================================================

Design an internal response schema.

Conceptually:

{
    answer,
    evidence,
    confidence,
    metadata,
    validation_status
}

Do not expose hidden reasoning.

Explain where structured outputs are useful and where plain text is preferable.

============================================================
STREAMING
============================================================

Design streaming generation.

Explain:

- Streaming architecture
- Partial responses
- Disconnects
- Timeouts
- Provider failure during streaming
- Fallback limitations

============================================================
GRACEFUL DEGRADATION
============================================================

This is a core requirement.

The system must not simply break when providers fail.

Design:

NORMAL
    ↓
DEGRADED
    ↓
FALLBACK
    ↓
RECOVERY

NORMAL:
All systems healthy.

DEGRADED:
Some providers unavailable.

FALLBACK:
No LLM providers available.

RECOVERY:
Providers return.

Explain exactly what happens in each state.

============================================================
CHANDLER FALLBACK
============================================================

When all LLM providers are unavailable, use static pre-written responses.

These responses should maintain the ChandlerOS personality.

Example:

"It seems a lot of people want to know about Harshith."

"Which is flattering."

"For him."

"Less so for my infrastructure."

Another:

"Okay, apparently Harshith has gone viral."

"I would like to formally request that everyone calm down."

These are examples only.

Design the complete fallback architecture.

It must never falsely imply that an LLM is processing the request when it is not.

============================================================
VIRAL MODE
============================================================

Design an automatic viral/high-traffic mode.

Monitor:

- Requests/minute
- Active sessions
- Error rate
- Provider utilization
- Cache hit rate

States:

NORMAL
BUSY
HIGH_TRAFFIC
VIRAL

In VIRAL mode:

- Increase caching
- Tighten rate limits
- Prefer cheaper models
- Reduce output limits
- Disable nonessential processing
- Use static responses when necessary
- Protect provider quotas

Explain transition and recovery logic.

============================================================
OBSERVABILITY
============================================================

Design full observability.

Track:

- Request ID
- Latency
- Retrieval latency
- Graph latency
- Vector latency
- LLM latency
- Provider
- Model
- Prompt version
- Personality version
- Knowledge version
- Tokens
- Cache hit/miss
- Retries
- Errors
- Fallbacks
- Evaluation results

Explain what should and should not be logged.

============================================================
TRACING
============================================================

Design request traces.

Example:

REQUEST
    |
    +-- Query Understanding
    |
    +-- Graph Retrieval
    |
    +-- Vector Retrieval
    |
    +-- Context Building
    |
    +-- Personality
    |
    +-- Model Routing
    |
    +-- LLM
    |
    +-- Validation
    |
    +-- Response

Explain how this allows debugging.

============================================================
COST TRACKING
============================================================

Even though the goal is free, track theoretical cost.

Track:

- Requests
- Tokens
- Provider
- Model
- Estimated cost
- Cache savings
- Fallback rate

Explain how this can be used to optimize the architecture.

============================================================
EVALUATION
============================================================

Evaluation must be a first-class subsystem.

Design separate evaluation dimensions.

RETRIEVAL:

- Recall@K
- Precision@K
- MRR
- NDCG
- Entity retrieval accuracy
- Relationship retrieval accuracy
- Multi-hop accuracy

GENERATION:

- Factuality
- Groundedness
- Relevance
- Completeness
- Clarity

PERSONALITY:

- ChandlerOS consistency
- Humor appropriateness
- Sarcasm
- Warmth
- Conversationality
- Model-to-model consistency

SYSTEM:

- Latency
- Reliability
- Fallback success
- Cache effectiveness

Explain which metrics should be deterministic and which should use an LLM judge.

============================================================
GOLDEN DATASET
============================================================

Design a benchmark containing:

- Simple factual questions
- Relationship questions
- Multi-hop questions
- Unknown questions
- Trick questions
- Adversarial questions
- Prompt injection questions
- Serious questions
- Casual questions
- Personality questions

Each benchmark item should contain expected:

- Facts
- Entities
- Relationships
- Evidence
- Response characteristics
- Personality characteristics

============================================================
LLM-AS-A-JUDGE
============================================================

Design an LLM-as-a-judge framework.

Do not rely exclusively on an LLM judge.

Combine:

- Deterministic checks
- Knowledge-graph checks
- Retrieval metrics
- LLM judge
- Human evaluation

Explain judge bias and how to reduce it.

============================================================
REGRESSION TESTING
============================================================

Design a regression framework.

Every change to:

- Prompt
- Model
- Knowledge base
- Retrieval strategy
- Personality
- Routing

should be evaluated against the golden dataset.

Pipeline:

Change
    ↓
Evaluation
    ↓
Compare with baseline
    ↓
Regression?
    ↓
PASS / FAIL

============================================================
VERSIONING
============================================================

Version independently:

- Prompts
- Models
- Knowledge
- Personality
- Retrieval configuration
- Evaluation datasets

Explain why independent versioning matters.

============================================================
SECURITY
============================================================

Design security architecture covering:

- Secret management
- API-key protection
- CORS
- Security headers
- Input validation
- Prompt injection
- Abuse
- Logging
- Privacy
- Dependency security

============================================================
DATABASE / STORAGE
============================================================

Evaluate appropriate storage options.

Potential architecture:

Relational DB / SQLite / D1

for:

- Entities
- Relationships
- Documents
- Evidence
- Sessions
- Metadata

Vector storage for embeddings.

Do not assume a dedicated graph database is necessary.

Analyze:

- SQLite/D1
- Dedicated graph DB
- Vector DB
- Hybrid approaches

Choose based on actual scale and free-tier constraints.

============================================================
FREE INFRASTRUCTURE
============================================================

The entire system should target approximately $0/month.

Evaluate:

- Frontend hosting
- Backend/serverless
- Database
- Object storage
- Vector storage
- LLM providers
- Embeddings
- CI/CD
- Monitoring
- Analytics

For each component provide:

- Free tier
- Limits
- Advantages
- Disadvantages
- Failure mode
- Migration path

Do not assume free tiers are unlimited.

============================================================
DEPLOYMENT
============================================================

Design a production deployment architecture.

Potential:

Browser
    ↓
Cloudflare
    ↓
Serverless API
    ↓
Database
    ↓
Retrieval
    ↓
LLM Gateway
    ↓
LLM providers

Explain deployment environments:

Development
Staging
Production

============================================================
CI/CD
============================================================

Design CI/CD.

Pipeline:

Pull Request
    ↓
Lint
    ↓
Unit tests
    ↓
Integration tests
    ↓
Knowledge validation
    ↓
RAG evaluation
    ↓
LLM evaluation
    ↓
Personality evaluation
    ↓
Security checks
    ↓
Build
    ↓
Staging
    ↓
Smoke test
    ↓
Production

Explain which checks should block deployment.

============================================================
FAILURE MODE ANALYSIS
============================================================

Create a comprehensive failure matrix.

At minimum:

- Provider timeout
- Provider 429
- Provider 500
- Provider unavailable
- All providers unavailable
- Database unavailable
- Graph retrieval failure
- Vector retrieval failure
- Embedding failure
- Prompt injection
- Hallucination
- Incorrect graph relationship
- Stale knowledge
- Conflicting knowledge
- Cache failure
- Traffic spike
- Bot attack
- Model change
- Bad prompt deployment
- Bad knowledge deployment
- Deployment failure

For each:

Detection
Impact
Mitigation
Fallback
Recovery
Observability

============================================================
ARCHITECTURE TRADE-OFFS
============================================================

For every major architectural choice explain:

- Why
- Alternatives
- Advantages
- Disadvantages
- Complexity
- Cost
- Scalability
- Free-tier viability
- Vendor lock-in
- Migration path

Avoid "because this is industry standard" as justification.

============================================================
PROJECT PHASES
============================================================

Create an extremely detailed implementation roadmap.

IMPORTANT:

You are NOT implementing these phases.

You are describing what would eventually be implemented.

Break the project into logical phases.

For each phase specify:

- Goal
- Components
- Inputs
- Outputs
- Dependencies
- Engineering concepts learned
- Tests required
- Evaluation required
- Production considerations
- Blog post that can be written from it
- Definition of done

The roadmap should progress from simplest working system to production-grade architecture.

============================================================
BLOG SERIES
============================================================

This project will also become a technical blog series.

Design a chronological blog curriculum.

Potential topics:

1. Why I Built a Portfolio AI Agent
2. Architecture of a Production LLM System
3. Knowledge Engineering
4. Building a Personal Knowledge Graph
5. Graph RAG
6. Vector RAG
7. Hybrid Retrieval
8. Query Understanding
9. Context Engineering
10. Personality Engineering
11. ChandlerOS
12. Model-Agnostic LLM Architecture
13. LLM Gateway
14. Model Routing
15. Provider Failover
16. Rate Limiting
17. Semantic Caching
18. Token Optimization
19. Free-Tier LLM Engineering
20. Circuit Breakers
21. Retries and Timeouts
22. Graceful Degradation
23. Viral Mode
24. Grounding
25. Prompt Injection
26. Evaluation
27. Golden Datasets
28. LLM-as-a-Judge
29. Regression Testing
30. Prompt Versioning
31. Knowledge Versioning
32. Model Versioning
33. Observability
34. Cost Tracking
35. CI/CD
36. Production Deployment
37. Failure Engineering
38. What Happens When the Portfolio Goes Viral?

For every blog post specify:

- Problem
- Naive solution
- Why naive solution fails
- Architecture
- Implementation concepts
- Experiments
- Evaluation
- Trade-offs
- Production lessons

============================================================
ENGINEERING PRINCIPLES
============================================================

The design should follow:

1. Prefer deterministic code where deterministic code is sufficient.

2. Do not use an LLM unnecessarily.

3. Do not use an agent when a deterministic router is sufficient.

4. Do not use a vector database unnecessarily.

5. Do not use a graph database unnecessarily.

6. Precompute expensive operations.

7. Cache aggressively but safely.

8. Separate knowledge from personality.

9. Separate retrieval from generation.

10. Separate provider APIs from application logic.

11. Make providers replaceable.

12. Design for failure.

13. Evaluation is part of development.

14. Prompts are versioned software.

15. Knowledge is versioned software.

16. Models are replaceable dependencies.

17. Observability is mandatory.

18. Free-tier operation is a design constraint.

19. Security is a design requirement.

20. Simplicity beats unnecessary sophistication.

============================================================
FINAL DELIVERABLE
============================================================

Your response should be a COMPLETE TECHNICAL BLUEPRINT.

Do NOT write implementation code.

Do NOT start building anything.

Do NOT create files.

Do NOT provide vague recommendations.

Do NOT skip difficult components.

Produce:

1. Executive summary
2. Product requirements
3. Non-functional requirements
4. Complete architecture
5. Component-by-component explanation
6. System data flow
7. Knowledge architecture
8. Knowledge graph schema
9. Graph RAG design
10. Vector RAG design
11. Hybrid retrieval design
12. Query understanding design
13. Context engineering design
14. Personality architecture
15. ChandlerOS design
16. LLM gateway
17. Model routing
18. Provider adapters
19. Provider health
20. Circuit breakers
21. Retry strategy
22. Timeout strategy
23. Rate limiting
24. Abuse prevention
25. Caching
26. Semantic caching
27. Token optimization
28. Conversation memory
29. Grounding
30. Prompt injection defense
31. Output validation
32. Structured outputs
33. Streaming
34. Graceful degradation
35. Chandler fallback
36. Viral mode
37. Observability
38. Distributed tracing
39. Cost tracking
40. Evaluation framework
41. Golden dataset
42. LLM-as-a-judge
43. Regression testing
44. Prompt versioning
45. Model versioning
46. Knowledge versioning
47. Security
48. Database/storage comparison
49. Free infrastructure architecture
50. Deployment architecture
51. CI/CD architecture
52. Failure-mode matrix
53. Development roadmap
54. Testing strategy
55. Blog curriculum
56. Risks
57. Trade-offs
58. Future extensions
59. Definition of the final production-ready system

============================================================
MOST IMPORTANT CONSTRAINT
============================================================

This is a PLANNING exercise.

Do not implement.

Do not code.

Do not create the application.

Think like the architect responsible for designing the system before engineers begin implementation.

The resulting document should be detailed enough that another senior engineer could take it and begin implementation without needing to rediscover the architecture from scratch.