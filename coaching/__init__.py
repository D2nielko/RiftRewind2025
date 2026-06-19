"""
Natural-language LoL coaching tool.

A retrieval layer on top of the existing Riot ingestion + ML app:
match records and Data Dragon docs are embedded once (embed-v4.0, cached to
disk), then queries run a two-stage retrieve (cosine top-50 -> rerank-v3.5
top-5) and Cohere Command (command-a) produces a grounded, cited answer.
"""
