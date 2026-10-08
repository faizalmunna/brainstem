---
name: setup
description: Configure Brainstem's evidence-first engineering workflow when this plugin is installed in a supported coding-agent host.
---

Brainstem is a local repository-intelligence and workflow control plane. This
plugin provides the workflow instructions; it does not silently add a server,
credential, network permission, or write permission.

1. Identify the repository the user wants to work in. Do not assume the
   current directory is the intended repository when the host exposes several
   workspaces.
2. If Brainstem MCP tools are already available, begin with
   `describe_project` and then call `prepare_task` for the user's concrete
   task. Treat the returned evidence packet as the starting context.
3. If the tools are not available, say that the workflow skill is active but
   the local MCP connection still needs to be configured. Direct the user to
   `brainstem host install <host> --path <repository> --apply`, using a
   `readonly` profile unless the user explicitly needs more authority.
4. Before a non-trivial change, create a durable workflow and record design,
   plan, executed verification, and independent review evidence. Use the
   `engineering-workflow` skill for the detailed gate sequence.
5. Do not treat a model assertion, a chat transcript, or an unexecuted command
   as verification. Never put API keys, access tokens, or secrets in a
   Brainstem artifact or a plugin configuration.

If Brainstem is unavailable, continue with the host's normal workflow, but do
not claim that Brainstem indexed the repository or verified a change.
