<?php
// SPDX-License-Identifier: Apache-2.0

require(__DIR__ . '/../../config.php');

$id = required_param('id', PARAM_INT);

$cm = get_coursemodule_from_id('chatlearning', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$chatlearning = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);

$PAGE->set_url('/mod/chatlearning/view.php', ['id' => $cm->id]);
$PAGE->set_title(format_string($chatlearning->name));
$PAGE->set_heading(format_string($course->fullname));
$PAGE->set_pagelayout('incourse');

$renderer = $PAGE->get_renderer('mod_chatlearning');

$pluginconfig = get_config('mod_chatlearning');
$apibase = rtrim((string)($pluginconfig->baseurl ?? ''), '/');

$jsconfig = [
    'cmid' => $cm->id,
    'sesskey' => sesskey(),
    'contextPrompt' => $chatlearning->contextprompt ?? '',
    'allowUploads' => (bool)$chatlearning->allowuploads,
    'allowedMimeTypes' => $chatlearning->allowedmimetypes ?? '',
    'apiBase' => $apibase,
    'documentBase' => $apibase ? $apibase . '/documents/' : '',
];

$PAGE->requires->js_call_amd('mod_chatlearning/chat_ui', 'init', [$jsconfig]);

echo $OUTPUT->header();

if (!empty($chatlearning->intro)) {
    echo $OUTPUT->box(format_module_intro('chatlearning', $chatlearning, $cm->id), 'generalbox mod_introbox');
}

$templatecontext = [
    'cmid' => $cm->id,
    'allowuploads' => (bool)$chatlearning->allowuploads,
    'allowedmimetypes' => $chatlearning->allowedmimetypes ?? '',
];

echo $renderer->render_from_template('mod_chatlearning/chat_page', $templatecontext);

echo $OUTPUT->footer();
