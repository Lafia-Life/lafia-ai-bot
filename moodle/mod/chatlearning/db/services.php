<?php
// SPDX-License-Identifier: Apache-2.0

defined('MOODLE_INTERNAL') || die();

$functions = [
    'mod_chatlearning_get_documents' => [
        'classname' => 'mod_chatlearning\external\api',
        'methodname' => 'get_documents',
        'classpath' => '',
        'description' => 'Return indexed documents for this ChatLearning instance.',
        'type' => 'read',
        'capabilities' => 'mod/chatlearning:view',
        'ajax' => true,
    ],
    'mod_chatlearning_submit_question' => [
        'classname' => 'mod_chatlearning\external\api',
        'methodname' => 'submit_question',
        'classpath' => '',
        'description' => 'Submit a chat question to the backend.',
        'type' => 'write',
        'capabilities' => 'mod/chatlearning:view',
        'ajax' => true,
    ],
    'mod_chatlearning_scrape_url' => [
        'classname' => 'mod_chatlearning\external\api',
        'methodname' => 'scrape_url',
        'classpath' => '',
        'description' => 'Scrape a web page and ingest it via the backend.',
        'type' => 'write',
        'capabilities' => 'mod/chatlearning:manage',
        'ajax' => true,
    ],
];

$services = [
    'ChatLearning internal API' => [
        'functions' => array_keys($functions),
        'restrictedusers' => 0,
        'enabled' => 1,
        'shortname' => 'mod_chatlearning_service',
    ],
];
