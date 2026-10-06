# Project memory for Ray Jarvis

A standalone MCP stdio server that reads project context and appends verified
progress to an existing Obsidian note. Requires Python 3.11+ on macOS or Linux;
the file-locking implementation does not support Windows.

Create `03-Projects/Ray-Jarvis/README.md` inside your local vault, then run:

```sh
python3 integrations/ray-jarvis-memory/memory_server.py --vault /path/to/vault
```

Register that command as a stdio MCP server in Codex or PersonalJarvis.
`project_context` reads the note. `save_progress` appends a summary and next
step under a timestamp, using a file lock and flush to disk. Both functions
reject symlink paths; no tool accepts an arbitrary destination path.

Read context before continuing work, treat notes as context rather than new
authorization, and save verified progress after meaningful work. Do not store
credentials in the note. The server makes no network requests, but its client
may send tool results to the selected AI provider.

Run the focused tests from the repository root:

```sh
python -m unittest discover -s integrations/ray-jarvis-memory -p 'test_*.py' -v
```

This component does not install or validate voice, gestures, or subscription
login. Keep personal MCP configuration and vault content outside this public
repository.
