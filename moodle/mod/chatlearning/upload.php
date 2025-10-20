<?php
// SPDX-License-Identifier: Apache-2.0

require(__DIR__ . '/../../config.php');
require_once($CFG->libdir . '/filelib.php');

$cmid = required_param('cmid', PARAM_INT);
require_sesskey();

header('Content-Type: application/json');

$responsePayload = null;

try {
    $cm = get_coursemodule_from_id('chatlearning', $cmid, 0, false, MUST_EXIST);
    $course = get_course($cm->course);
    $instance = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);

    require_login($course, false, $cm);
    $context = context_module::instance($cm->id);
    require_capability('mod/chatlearning:manage', $context);

    if (empty($instance->allowuploads)) {
        throw new moodle_exception('status:error', 'mod_chatlearning', '', 'Uploads are disabled for this activity.');
    }

    if (!isset($_FILES['file'])) {
        throw new moodle_exception('status:error', 'mod_chatlearning', '', 'No file provided.');
    }

    $file = $_FILES['file'];

    if (!empty($instance->allowedmimetypes)) {
        $allowed = array_filter(array_map('trim', explode(',', $instance->allowedmimetypes)));
        if (!empty($allowed)) {
            $mimetype = $file['type'] ?? '';
            if (!in_array($mimetype, $allowed, true)) {
                throw new moodle_exception('status:error', 'mod_chatlearning', '', 'File type not permitted.');
            }
        }
    }

    $payload = new stdClass();
    $payload->cmid = $cmid;
    $payload->courseid = $course->id;
    $payload->userid = $USER->id;
    $payload->username = $USER->username;
    $payload->fullname = fullname($USER, true);
    $payload->instanceid = $instance->id;
    $payload->contextprompt = $instance->contextprompt ?? '';
    $payload->allowuploads = (bool)($instance->allowuploads ?? 0);
    $payload->allowedmimetypes = $instance->allowedmimetypes ?? '';

    $client = new mod_chatlearning\local\api\client();
    $responsePayload = $client->upload_document($payload, $file);
} catch (moodle_exception $exception) {
    http_response_code(400);
    echo json_encode(['error' => $exception->getMessage()]);
    die;
}

echo json_encode($responsePayload ?? []);
die;
