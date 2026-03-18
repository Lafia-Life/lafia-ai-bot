# ChatLearning Moodle Activity

This Moodle activity module embeds the ChatLearning FastAPI experience directly in a course.

> **Status:** Prototype. Wire up the settings screen with the FastAPI host and API key before enabling.

## Features

- Native Moodle activity that keeps the existing upload → retrieval → chat flow.
- Admin-configurable FastAPI host and authorization key.
- AJAX bridge that proxies Moodle user/course identity to the backend.
- AMD front-end that mirrors the current web UI for uploading, searching, and chatting.
- Enrollment-aware document scope options (current course, enrolled courses, or all courses for managers).
- Moodle sync action for importing `PDF` resources and `SCORM` package ZIP files.

## Getting Started

1. Copy `moodle/mod/chatlearning` into your Moodle installation under `mod/chatlearning`.
2. Visit *Site administration → Notifications* to install the activity module.
3. Configure *Site administration → Plugins → Activity modules → ChatLearning* with the FastAPI base URL and API key.
4. Add a new ChatLearning activity to a course and interact with the chat UI.

### Development Notes

- The AMD source lives in `amd/src/chat_ui.js`. Rebuild with Moodle's `grunt` pipeline to generate `amd/build` artifacts before packaging.
- Back-end requests flow through `classes/local/api/client.php`. Extend this client when new FastAPI endpoints are exposed.
- Server-side templates reside in `templates/`. Use Moodle's template renderer for complex layouts.
