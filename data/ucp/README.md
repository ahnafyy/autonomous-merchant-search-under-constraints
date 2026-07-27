# UCP Input Data

This directory contains public-safe metadata and immutable snapshot manifests for the
UCP experiment. Do not store API keys, bearer tokens, cookies, or raw credentials.

Start with `inventory.example.json`. Each endpoint record names an authentication
environment variable, never its value. An endpoint is eligible for live collection
only when its permission status is verified, its selected operation is side-effect
free, and it supports exact-product lookup.

Raw live responses may be retained only when endpoint terms permit it. Generated
research artifacts should identify an immutable input snapshot by ID and hash rather
than copying restricted payloads.