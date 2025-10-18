Use this file to provide workspace-specific custom instructions to Copilot.

- [x] Verify that the copilot-instructions.md file in the .github directory is created. (File created with initial instructions.)

- [x] Clarify Project Requirements (MVP for PDF chat assistant using single FastAPI backend + minimal UI.)
  Ask for project type, language, and frameworks if not specified. Skip if already provided.

- [x] Scaffold the Project (FastAPI app skeleton with ingestion/retrieval services and minimal UI assets.)
  Ensure that the previous step has been marked as completed.
  Call project setup tool with projectType parameter.
  Run scaffolding commands using '.' as the working directory.
  If no appropriate projectType is available, use documentation/tools or create the structure manually.

- [x] Customize the Project (Implemented PDF ingestion, vector storage, and chat retrieval endpoints.)
  Verify earlier steps are complete and marked.
  Develop a modification plan aligned with requirements.
  Apply changes using appropriate tools and references.
  Skip this step for "Hello World" projects.

- [x] Install Required Extensions (No extensions requested by project setup tool.)
  Only install extensions mentioned by get_project_setup_info; otherwise mark as completed.

- [x] Compile the Project (.venv created, dependencies installed, and python -m compileall verified.)
  Confirm prior steps are complete.
  Install missing dependencies.
  Run diagnostics and resolve issues.
  Review markdown instructions for additional requirements.

- [x] Create and Run Task (Added VS Code task to launch uvicorn with reload.)
  Ensure prior steps are done.
  Consult VS Code task docs if needed and use create_and_run_task when appropriate.
  Skip if unnecessary.

- [x] Launch the Project (Run FastAPI dev server task started in reload mode.)
  Confirm all prior steps are complete.
  Ask for debug preference and launch only if confirmed.

- [x] Ensure Documentation is Complete
  Confirm prior steps.
  Verify README.md and this instruction file exist and reflect current project status.
  Remove outdated comments and keep instructions current.

Execution Guidelines
Progress Tracking:
- Use available tools to track checklist progress.
- Mark steps complete with summaries.
- Review checklist status before starting a new step.

Communication Rules:
- Avoid verbose explanations or full command outputs.
- Briefly note skipped steps.
- Only describe project structure when asked.
- Keep responses focused.

Development Rules:
- Work from the current directory unless told otherwise.
- Add media or external links only when requested.
- Flag placeholders so they can be replaced later.
- Use the VS Code API tool solely for extension projects.
- Do not suggest reopening the project in VS Code.
- Follow any additional project setup guidance.

Folder Creation Rules:
- Use the current directory as the root.
- When running terminal commands, rely on '.' to maintain context.
- Create new folders only on explicit request (aside from .vscode for tasks).
- If scaffolding commands complain about folder names, advise the user to rename and reopen as needed.

Extension Installation Rules:
- Install only extensions specified by get_project_setup_info.

Project Content Rules:
- Default to a "Hello World" baseline when requirements are unclear.
- Avoid unnecessary integrations or links.
- Do not generate media unless requested.
- Note placeholders for future replacement.
- Ensure every addition supports the requested workflow.
- Seek clarification for unconfirmed features.
- For VS Code extensions, query the VS Code API docs as needed.

Task Completion Rules:
- Completion requires: project scaffolded and compiled cleanly, this instruction file present, README current, and user has launch/debug guidance.
- Update progress tracking before starting new tasks.

- Work through each checklist item systematically.
- Keep communication concise and focused.
- Follow development best practices.
