<?php
// SPDX-License-Identifier: Apache-2.0

defined('MOODLE_INTERNAL') || die();

function xmldb_chatlearning_upgrade(int $oldversion): bool {
    global $DB;

    $dbman = $DB->get_manager();

    if ($oldversion < 2026031100) {
        $table = new xmldb_table('chatlearning');

        $field = new xmldb_field('documentscope', XMLDB_TYPE_CHAR, '32', null, XMLDB_NOTNULL, null, 'enrolledcourses', 'allowedmimetypes');
        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        $field = new xmldb_field('allowglobaldocs', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '0', 'documentscope');
        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        $field = new xmldb_field('allowmoodlesync', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '1', 'allowglobaldocs');
        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        $field = new xmldb_field('sourcepdf', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '1', 'allowmoodlesync');
        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        $field = new xmldb_field('sourcescorm', XMLDB_TYPE_INTEGER, '1', null, XMLDB_NOTNULL, null, '1', 'sourcepdf');
        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        upgrade_mod_savepoint(true, 2026031100, 'chatlearning');
    }

    return true;
}
