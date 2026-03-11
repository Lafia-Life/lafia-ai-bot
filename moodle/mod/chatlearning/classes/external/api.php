<?php
// SPDX-License-Identifier: Apache-2.0

namespace mod_chatlearning\external;

use context_module;
use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_multiple_structure;
use core_external\external_single_structure;
use core_external\external_value;
use mod_chatlearning\local\api\client;
use moodle_exception;
use stdClass;

class api extends external_api {
    public static function get_documents_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
        ]);
    }

    public static function get_documents(int $cmid): array {
        global $DB;

        ['cmid' => $cmid] = self::validate_parameters(self::get_documents_parameters(), ['cmid' => $cmid]);

        $cm = get_coursemodule_from_id('chatlearning', $cmid, 0, false, MUST_EXIST);
        $course = get_course($cm->course);
        $instance = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);
        $context = context_module::instance($cmid);

        self::validate_context($context);
        require_login($course, false, $cm);
        require_capability('mod/chatlearning:view', $context);

        $payload = self::build_context_payload($cmid, $course->id, $instance, $context);
        $client = new client();

        $documents = $client->get_documents($payload);

        return self::filter_documents($documents, $payload);
    }

    public static function get_documents_returns(): external_multiple_structure {
        return new external_multiple_structure(
            new external_single_structure([
                'document_id' => new external_value(PARAM_TEXT, 'Document id'),
                'filename' => new external_value(PARAM_TEXT, 'Filename'),
                'page_count' => new external_value(PARAM_INT, 'Page count', VALUE_OPTIONAL),
                'source_type' => new external_value(PARAM_TEXT, 'Source type', VALUE_OPTIONAL),
                'url' => new external_value(PARAM_TEXT, 'Source URL', VALUE_OPTIONAL),
                'course_id' => new external_value(PARAM_TEXT, 'Course identifier', VALUE_OPTIONAL),
            ])
        );
    }

    public static function submit_question_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'question' => new external_value(PARAM_RAW, 'Question text'),
        ]);
    }

    public static function submit_question(int $cmid, string $question): array {
        global $DB;

        ['cmid' => $cmid, 'question' => $question] = self::validate_parameters(
            self::submit_question_parameters(),
            ['cmid' => $cmid, 'question' => $question]
        );

        $cm = get_coursemodule_from_id('chatlearning', $cmid, 0, false, MUST_EXIST);
        $course = get_course($cm->course);
        $instance = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);
        $context = context_module::instance($cmid);

        self::validate_context($context);
        require_login($course, false, $cm);
        require_capability('mod/chatlearning:view', $context);

        $payload = self::build_context_payload($cmid, $course->id, $instance, $context);
        $client = new client();
        $result = $client->submit_question($payload, $question);

        return [
            'answer' => $result['answer'] ?? '',
            'citations' => $result['citations'] ?? [],
        ];
    }

    public static function submit_question_returns(): external_single_structure {
        return new external_single_structure([
            'answer' => new external_value(PARAM_RAW, 'Answer text'),
            'citations' => new external_multiple_structure(
                new external_single_structure([
                    'document_id' => new external_value(PARAM_TEXT, 'Document id'),
                    'filename' => new external_value(PARAM_TEXT, 'Filename'),
                    'page_start' => new external_value(PARAM_INT, 'Start page', VALUE_OPTIONAL),
                    'page_end' => new external_value(PARAM_INT, 'End page', VALUE_OPTIONAL),
                    'score' => new external_value(PARAM_FLOAT, 'Similarity score', VALUE_OPTIONAL),
                    'excerpt' => new external_value(PARAM_RAW, 'Excerpt', VALUE_OPTIONAL),
                    'source_type' => new external_value(PARAM_TEXT, 'Source type', VALUE_OPTIONAL),
                    'url' => new external_value(PARAM_TEXT, 'Source URL', VALUE_OPTIONAL),
                    'course_id' => new external_value(PARAM_TEXT, 'Course identifier', VALUE_OPTIONAL),
                ])
            ),
        ]);
    }

    public static function scrape_url_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'url' => new external_value(PARAM_URL, 'URL to ingest'),
        ]);
    }

    public static function scrape_url(int $cmid, string $url): array {
        global $DB;

        ['cmid' => $cmid, 'url' => $url] = self::validate_parameters(
            self::scrape_url_parameters(),
            ['cmid' => $cmid, 'url' => $url]
        );

        $cm = get_coursemodule_from_id('chatlearning', $cmid, 0, false, MUST_EXIST);
        $course = get_course($cm->course);
        $instance = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);
        $context = context_module::instance($cmid);

        self::validate_context($context);
        require_login($course, false, $cm);
        require_capability('mod/chatlearning:manage', $context);

        $payload = self::build_context_payload($cmid, $course->id, $instance, $context);
        $client = new client();
        $result = $client->scrape_url($payload, $url);

        return $result;
    }

    public static function scrape_url_returns(): external_single_structure {
        return new external_single_structure([
            'document' => new external_single_structure([
                'document_id' => new external_value(PARAM_TEXT, 'Document id'),
                'filename' => new external_value(PARAM_TEXT, 'Filename'),
                'page_count' => new external_value(PARAM_INT, 'Page count', VALUE_OPTIONAL),
                'source_type' => new external_value(PARAM_TEXT, 'Source type', VALUE_OPTIONAL),
                'url' => new external_value(PARAM_TEXT, 'Source URL', VALUE_OPTIONAL),
                'course_id' => new external_value(PARAM_TEXT, 'Course identifier', VALUE_OPTIONAL),
            ]),
            'chunks_indexed' => new external_value(PARAM_INT, 'Number of chunks indexed'),
        ]);
    }

    public static function sync_moodle_documents_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'Course module ID'),
            'include_pdf' => new external_value(PARAM_RAW, 'Include PDF resources', VALUE_DEFAULT, '1'),
            'include_scorm' => new external_value(PARAM_RAW, 'Include SCORM packages', VALUE_DEFAULT, '1'),
        ]);
    }

    public static function sync_moodle_documents(int $cmid, $include_pdf = true, $include_scorm = true): array {
        global $DB;

        $params = self::validate_parameters(
            self::sync_moodle_documents_parameters(),
            ['cmid' => $cmid, 'include_pdf' => $include_pdf, 'include_scorm' => $include_scorm]
        );
        $cmid = (int)$params['cmid'];
        $include_pdf = self::normalize_bool_param($params['include_pdf'], true);
        $include_scorm = self::normalize_bool_param($params['include_scorm'], true);

        $cm = get_coursemodule_from_id('chatlearning', $cmid, 0, false, MUST_EXIST);
        $course = get_course($cm->course);
        $instance = $DB->get_record('chatlearning', ['id' => $cm->instance], '*', MUST_EXIST);
        $context = context_module::instance($cmid);

        self::validate_context($context);
        require_login($course, false, $cm);
        require_capability('mod/chatlearning:manage', $context);

        if (empty($instance->allowmoodlesync)) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', 'Moodle sync is disabled for this activity.');
        }

        $pdfenabled = !isset($instance->sourcepdf) || (int)$instance->sourcepdf === 1;
        $scormenabled = !isset($instance->sourcescorm) || (int)$instance->sourcescorm === 1;

        $include_pdf = $include_pdf && $pdfenabled;
        $include_scorm = $include_scorm && $scormenabled;

        if (!$include_pdf && !$include_scorm) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', 'No source types are enabled for sync.');
        }

        $payload = self::build_context_payload($cmid, $course->id, $instance, $context);
        $courseids = self::resolve_allowed_course_ids($instance, $course->id, $context);
        $client = new client();

        $filesdiscovered = 0;
        $documentsindexed = 0;
        $documentsskipped = 0;

        foreach ($courseids as $courseid) {
            $entries = self::collect_sync_entries((int)$courseid, $include_pdf, $include_scorm);
            $filesdiscovered += count($entries);

            foreach ($entries as $entry) {
                $tmpfile = tempnam(sys_get_temp_dir(), 'chatlearning_');
                if ($tmpfile === false) {
                    $documentsskipped++;
                    continue;
                }

                try {
                    /** @var \stored_file $storedfile */
                    $storedfile = $entry['file'];
                    $storedfile->copy_content_to($tmpfile);

                    $fileinfo = [
                        'tmp_name' => $tmpfile,
                        'name' => $storedfile->get_filename(),
                        'type' => $storedfile->get_mimetype(),
                    ];
                    $extra = [
                        'course_id' => (string)$courseid,
                        'source_type_hint' => $entry['source_type'],
                        'external_ref' => $entry['external_ref'],
                    ];

                    $result = $client->upload_document($payload, $fileinfo, $extra);
                    if ((int)($result['chunks_indexed'] ?? 0) > 0) {
                        $documentsindexed++;
                    } else {
                        $documentsskipped++;
                    }
                } catch (\Throwable $ex) {
                    $documentsskipped++;
                } finally {
                    @unlink($tmpfile);
                }
            }
        }

        return [
            'courses_scanned' => count($courseids),
            'files_discovered' => $filesdiscovered,
            'documents_indexed' => $documentsindexed,
            'documents_skipped' => $documentsskipped,
        ];
    }

    private static function normalize_bool_param($value, bool $default = true): bool {
        if ($value === null || $value === '') {
            return $default;
        }
        if (is_bool($value)) {
            return $value;
        }
        if (is_int($value) || is_float($value)) {
            return ((int)$value) !== 0;
        }
        $normalized = strtolower(trim((string)$value));
        if ($normalized === '') {
            return $default;
        }
        return in_array($normalized, ['1', 'true', 'yes', 'on'], true);
    }

    public static function sync_moodle_documents_returns(): external_single_structure {
        return new external_single_structure([
            'courses_scanned' => new external_value(PARAM_INT, 'Number of courses scanned'),
            'files_discovered' => new external_value(PARAM_INT, 'Number of Moodle files found for sync'),
            'documents_indexed' => new external_value(PARAM_INT, 'Number of documents indexed'),
            'documents_skipped' => new external_value(PARAM_INT, 'Number of documents skipped'),
        ]);
    }

    private static function build_context_payload(
        int $cmid,
        int $courseid,
        stdClass $instance,
        context_module $context
    ): stdClass {
        global $USER;

        $payload = new stdClass();
        $payload->cmid = $cmid;
        $payload->courseid = $courseid;
        $payload->userid = $USER->id;
        $payload->username = $USER->username;
        $payload->fullname = fullname($USER, true);
        $payload->instanceid = $instance->id;
        $payload->contextprompt = $instance->contextprompt ?? '';
        $payload->allowuploads = (bool)($instance->allowuploads ?? 0);
        $payload->allowedmimetypes = $instance->allowedmimetypes ?? '';
        $payload->allowedcourseids = self::resolve_allowed_course_ids($instance, $courseid, $context);
        $payload->allowedsourcetypes = self::resolve_allowed_source_types($instance);
        $payload->includeglobaldocs = !empty($instance->allowglobaldocs);

        return $payload;
    }

    private static function resolve_allowed_source_types(stdClass $instance): array {
        $types = ['web', 'image'];
        if (!isset($instance->sourcepdf) || (int)$instance->sourcepdf === 1) {
            $types[] = 'pdf';
        }
        if (!isset($instance->sourcescorm) || (int)$instance->sourcescorm === 1) {
            $types[] = 'scorm';
        }
        if (empty($types)) {
            $types[] = 'pdf';
        }
        return array_values(array_unique($types));
    }

    private static function resolve_allowed_course_ids(stdClass $instance, int $defaultcourseid, context_module $context): array {
        global $CFG, $DB, $USER;

        $scope = (string)($instance->documentscope ?? 'enrolledcourses');
        if ($scope === 'allcourses' && !has_capability('mod/chatlearning:manage', $context)) {
            $scope = 'enrolledcourses';
        }

        if ($scope === 'allcourses') {
            $courseids = $DB->get_fieldset_select('course', 'id', 'id <> :siteid', ['siteid' => SITEID]);
            if (!empty($courseids)) {
                return array_map('intval', $courseids);
            }
        }

        if ($scope === 'enrolledcourses') {
            require_once($CFG->libdir . '/enrollib.php');
            $courses = enrol_get_all_users_courses($USER->id, true, 'id');
            $courseids = array_map('intval', array_keys($courses));
            if (!empty($courseids)) {
                return $courseids;
            }
        }

        return [(int)$defaultcourseid];
    }

    private static function filter_documents(array $documents, stdClass $payload): array {
        $allowedcourseids = array_map('strval', $payload->allowedcourseids ?? []);
        $allowedsourcetypes = array_map('strtolower', $payload->allowedsourcetypes ?? []);
        $includeglobaldocs = !empty($payload->includeglobaldocs);

        return array_values(array_filter($documents, function(array $document) use ($allowedcourseids, $allowedsourcetypes, $includeglobaldocs): bool {
            $sourcetype = strtolower((string)($document['source_type'] ?? 'pdf'));
            if (!empty($allowedsourcetypes) && !in_array($sourcetype, $allowedsourcetypes, true)) {
                return false;
            }

            $courseid = $document['course_id'] ?? null;
            if ($courseid === null || $courseid === '') {
                return $includeglobaldocs || empty($allowedcourseids);
            }

            if (empty($allowedcourseids)) {
                return true;
            }

            return in_array((string)$courseid, $allowedcourseids, true);
        }));
    }

    private static function collect_sync_entries(int $courseid, bool $includepdf, bool $includescorm): array {
        global $USER;
        $entries = [];
        $fs = get_file_storage();
        $modinfo = get_fast_modinfo($courseid, $USER->id);

        foreach ($modinfo->cms as $cm) {
            if (!$cm->uservisible) {
                continue;
            }

            $modulecontext = context_module::instance($cm->id);

            if ($includepdf && $cm->modname === 'resource') {
                $files = $fs->get_area_files(
                    $modulecontext->id,
                    'mod_resource',
                    'content',
                    0,
                    'id',
                    false
                );
                foreach ($files as $file) {
                    if (!self::is_pdf_file($file)) {
                        continue;
                    }
                    $entries[] = [
                        'file' => $file,
                        'source_type' => 'pdf',
                        'external_ref' => 'moodle:resource:' . $file->get_id(),
                    ];
                }
            }

            if ($includescorm && $cm->modname === 'scorm') {
                $files = $fs->get_area_files(
                    $modulecontext->id,
                    'mod_scorm',
                    'package',
                    0,
                    'id',
                    false
                );
                foreach ($files as $file) {
                    if (!self::is_scorm_package($file)) {
                        continue;
                    }
                    $entries[] = [
                        'file' => $file,
                        'source_type' => 'scorm',
                        'external_ref' => 'moodle:scorm:' . $file->get_id(),
                    ];
                }
            }
        }

        return $entries;
    }

    private static function is_pdf_file(\stored_file $file): bool {
        $filename = strtolower($file->get_filename());
        $mimetype = strtolower((string)$file->get_mimetype());
        return str_ends_with($filename, '.pdf') || $mimetype === 'application/pdf';
    }

    private static function is_scorm_package(\stored_file $file): bool {
        $filename = strtolower($file->get_filename());
        $mimetype = strtolower((string)$file->get_mimetype());
        return str_ends_with($filename, '.zip') || strpos($mimetype, 'zip') !== false;
    }
}
