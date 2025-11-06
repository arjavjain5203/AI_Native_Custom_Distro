# Codebase Understanding

## Purpose

This document explains how the platform understands existing repositories in v1, how indexing works, and what the practical limits are.

## v1 Goal

The v1 goal is not general software reasoning over very large repositories. It is targeted support for small and medium Python/FastAPI projects so the system can retrieve relevant files and make bounded code modifications with acceptable reliability.

## Indexing Pipeline

The indexing flow is:

1. scan the repository
2. filter supported file types
3. chunk files into retrieval units
4. generate embeddings
5. store embeddings in FAISS
6. store metadata in SQLite

Metadata should include:

- repository path
- file path
- chunk identifier
- framework hints
- last indexed timestamp

## Retrieval Workflow

When the user asks for a code modification:

1. the system checks whether the repository is indexed
2. the Coding Agent uses the task description to retrieve relevant chunks
3. the retrieved context is supplied to the coding model
4. proposed changes are mapped back to real files
5. filesystem tools apply the changes

This retrieval-first approach is critical for keeping edits grounded in the actual codebase.

## Example Use Case

For the request `add authentication to this fastapi project`, the platform should:

- identify the active repository
- retrieve application entry points, route files, settings, and dependencies
- generate a bounded plan for code changes
- modify only the files needed for the feature

## Supported Scope in v1

Version 1 is limited to:

- small and medium repositories
- Python-oriented project structures
- FastAPI as the primary supported framework
- bounded code generation and modification

The system should reject unsupported repository shapes clearly rather than pretending to understand them.

## Known Limitations

The following are not realistic in v1:

- very large monorepos
- broad cross-language reasoning
- complex refactors across many unrelated modules
- full semantic understanding of arbitrary frameworks

Those limitations should be explicit in both the product behavior and the documentation.

## Implementation Notes

Chunking strategy should prefer practical context windows over theoretical purity. The important outcome is that retrieved snippets give the Coding Agent enough context to edit the correct files safely. Exact chunk size and embedding model choice can be tuned later as long as the pipeline remains deterministic.
