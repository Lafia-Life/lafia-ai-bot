<?php
// SPDX-License-Identifier: Apache-2.0

$string['pluginname'] = 'ChatLearning';
$string['modulename'] = 'ChatLearning';
$string['modulenameplural'] = 'ChatLearning activities';
$string['activityname'] = 'Activity name';
$string['intro'] = 'Description';
$string['contextprompt'] = 'Context prompt';
$string['contextprompt_help'] = 'Optional system prompt that is sent to the backend for every chat request.';
$string['allowuploads'] = 'Allow uploads';
$string['allowedmimetypes'] = 'Allowed MIME types';
$string['allowedmimetypes_help'] = 'Comma-separated list of MIME types (for example: application/pdf). Leave empty to use the backend defaults.';
$string['manageinstanceslink'] = 'Manage ChatLearning activities';
$string['pluginadministration'] = 'ChatLearning administration';

$string['setting:baseurl'] = 'FastAPI base URL';
$string['setting:baseurl_desc'] = 'Base URL of the ChatLearning FastAPI deployment (for example: https://chat.example.com).';
$string['setting:apikey'] = 'API key';
$string['setting:apikey_desc'] = 'Optional API key sent as an Authorization header with every request.';
$string['setting:timeout'] = 'Request timeout (seconds)';
$string['setting:timeout_desc'] = 'How long to wait for a response from the FastAPI backend before timing out.';

$string['capability:view'] = 'View ChatLearning activity';
$string['capability:manage'] = 'Manage ChatLearning activity';

$string['label:documents'] = 'Indexed documents';
$string['label:chat'] = 'Ask a question';
$string['label:references'] = 'Supporting references';
$string['label:uploads'] = 'Upload documents';
$string['label:scrape'] = 'Add URL';
$string['status:uploading'] = 'Uploading...';
$string['status:thinking'] = 'Thinking...';
$string['status:searching'] = 'Searching supporting passages...';
$string['status:nodocuments'] = 'No documents indexed yet.';
$string['status:noreferences'] = 'No supporting references found yet.';
$string['status:error'] = 'Request failed: {$a}';
$string['status:requiresconfig'] = 'The plugin needs to be configured by an administrator before use.';

$string['privacy:metadata'] = 'The ChatLearning activity stores minimal metadata to associate Moodle users with backend conversations.';
$string['privacy:metadata:chatlearning_sessions'] = 'Chat sessions initiated by Moodle users.';
$string['privacy:metadata:chatlearning_sessions:userid'] = 'The Moodle user ID who initiated the chat.';
$string['privacy:metadata:chatlearning_sessions:courseid'] = 'The Moodle course where the chat happened.';
$string['privacy:metadata:chatlearning_sessions:chatlearningid'] = 'The ChatLearning activity instance.';
$string['privacy:metadata:chatlearning_sessions:conversationid'] = 'Conversation identifier returned by the FastAPI backend.';
$string['privacy:metadata:chatlearning_sessions:timecreated'] = 'When the chat session was created.';
