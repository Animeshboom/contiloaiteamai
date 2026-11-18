"""StudioTrack Gmail MCP server.

A standalone MCP server exposing a small, controlled set of email tools. It enforces
its own recipient and approval policy against the StudioTrack database (read-only),
so a misbehaving client or AI agent cannot use it to email arbitrary addresses or to
send a report that a team lead has not approved.
"""
