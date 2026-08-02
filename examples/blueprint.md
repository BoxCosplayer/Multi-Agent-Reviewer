# Customer Support Knowledge Assistant

Build an internal web application that helps support agents answer customer
questions using approved company documentation.

## Users

- Support agents authenticate with the company identity provider.
- Knowledge administrators manage source documents and access policies.

## Required capabilities

- Ingest PDF, Markdown, and HTML documents.
- Index approved content for semantic retrieval.
- Answer questions with citations to the source documents.
- Stream responses to the browser.
- Record feedback and audit events.
- Prevent users from retrieving content outside their assigned business unit.
- Allow administrators to revoke a document and remove it from future answers.

## Constraints

- The first release serves 500 support agents.
- Expected peak load is 30 questions per second.
- Source documents may contain confidential customer and product information.
- The application must run in a managed cloud environment.
- The architecture should avoid unnecessary operational complexity.
