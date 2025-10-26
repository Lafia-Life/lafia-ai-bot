<?php
// SPDX-License-Identifier: Apache-2.0

defined('MOODLE_INTERNAL') || die();

function chatlearning_supports($feature) {
    switch ($feature) {
        case FEATURE_MOD_INTRO:
        case FEATURE_SHOW_DESCRIPTION:
            return true;
        case FEATURE_MOD_ARCHETYPE:
            return MOD_ARCHETYPE_OTHER;
        case FEATURE_BACKUP_MOODLE2:
            return true;
        case FEATURE_COMPLETION_TRACKS_VIEWS:
            return true;
        case FEATURE_GRADE_HAS_GRADE:
        case FEATURE_GRADE_OUTCOMES:
        default:
            return false;
    }
}

function chatlearning_add_instance(stdClass $data, mod_chatlearning_mod_form $mform = null) {
    global $DB;

    $data->timecreated = time();
    $data->timemodified = $data->timecreated;
    $data->name = trim($data->name);
    $data->contextprompt = $data->contextprompt ?? '';
    $data->allowuploads = (int)($data->allowuploads ?? 1);
    $data->allowedmimetypes = $data->allowedmimetypes ?? '';

    if (!empty($data->introeditor)) {
        $data->intro = $data->introeditor['text'];
        $data->introformat = $data->introeditor['format'];
    }

    return $DB->insert_record('chatlearning', $data);
}

function chatlearning_update_instance(stdClass $data, mod_chatlearning_mod_form $mform = null) {
    global $DB;

    $record = $DB->get_record('chatlearning', ['id' => $data->instance], '*', MUST_EXIST);

    $record->name = trim($data->name);
    $record->timemodified = time();
    $record->contextprompt = $data->contextprompt ?? '';
    $record->allowuploads = (int)($data->allowuploads ?? 1);
    $record->allowedmimetypes = $data->allowedmimetypes ?? '';

    if (!empty($data->introeditor)) {
        $record->intro = $data->introeditor['text'];
        $record->introformat = $data->introeditor['format'];
    }

    $record->intro = $record->intro ?? '';
    $record->introformat = $record->introformat ?? FORMAT_HTML;

    return $DB->update_record('chatlearning', $record);
}

function chatlearning_delete_instance($id) {
    global $DB;

    if (!$record = $DB->get_record('chatlearning', ['id' => $id])) {
        return false;
    }

    $DB->delete_records('chatlearning_sessions', ['chatlearningid' => $id]);
    $DB->delete_records('chatlearning', ['id' => $id]);

    return true;
}

function chatlearning_get_coursemodule_info($coursemodule) {
    global $DB;

    if (!$record = $DB->get_record('chatlearning', ['id' => $coursemodule->instance])) {
        return null;
    }

    $info = new cached_cm_info();
    $info->name = $record->name;

    if (!empty($record->intro)) {
        $info->content = format_module_intro('chatlearning', $record, $coursemodule->id, false);
    }

    $info->customdata = (object)[
        'allowuploads' => (bool)$record->allowuploads,
    ];

    return $info;
}

