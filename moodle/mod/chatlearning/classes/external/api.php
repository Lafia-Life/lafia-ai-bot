<?php
// SPDX-License-Identifier: Apache-2.0

namespace mod_chatlearning\external;

use context_module;
use mod_chatlearning\local\api\client;
use moodle_exception;
use external_api;
use external_function_parameters;
use external_multiple_structure;
use external_single_structure;
use external_value;
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

        $client = new client();

        $payload = self::build_context_payload($cmid, $course->id, $instance);

        $documents = $client->get_documents($payload);

        return $documents;
    }

    public static function get_documents_returns(): external_multiple_structure {
        return new external_multiple_structure(
            new external_single_structure([
                'document_id' => new external_value(PARAM_TEXT, 'Document id'),
                'filename' => new external_value(PARAM_TEXT, 'Filename'),
                'page_count' => new external_value(PARAM_INT, 'Page count', VALUE_OPTIONAL),
                'source_type' => new external_value(PARAM_TEXT, 'Source type', VALUE_OPTIONAL),
                'url' => new external_value(PARAM_TEXT, 'Source URL', VALUE_OPTIONAL),
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

        $payload = self::build_context_payload($cmid, $course->id, $instance);
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

        $payload = self::build_context_payload($cmid, $course->id, $instance);
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
            ]),
            'chunks_indexed' => new external_value(PARAM_INT, 'Number of chunks indexed'),
        ]);
    }

    private static function build_context_payload(int $cmid, int $courseid, stdClass $instance): stdClass {
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

        return $payload;
    }
}
