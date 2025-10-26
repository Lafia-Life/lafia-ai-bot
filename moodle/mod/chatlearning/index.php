<?php
// SPDX-License-Identifier: Apache-2.0

require(__DIR__ . '/../../config.php');

$id = required_param('id', PARAM_INT);

$course = get_course($id);
require_login($course);

$context = context_course::instance($course->id);
$PAGE->set_url('/mod/chatlearning/index.php', ['id' => $course->id]);
$PAGE->set_title(format_string($course->fullname));
$PAGE->set_heading(format_string($course->fullname));

$modinfo = get_fast_modinfo($course);
$instances = $modinfo->get_instances_of('chatlearning');

$renderer = $PAGE->get_renderer('mod_chatlearning');

echo $OUTPUT->header();

echo $OUTPUT->heading(get_string('modulenameplural', 'mod_chatlearning'));

if (!$instances) {
    echo $OUTPUT->notification(get_string('status:nodocuments', 'mod_chatlearning'), 'info');
    echo $OUTPUT->footer();
    exit;
}

echo html_writer::start_tag('ul');
foreach ($instances as $cm) {
    if (!$cm->uservisible) {
        continue;
    }
    $name = format_string($cm->name);
    $url = new moodle_url('/mod/chatlearning/view.php', ['id' => $cm->id]);
    echo html_writer::tag('li', html_writer::link($url, $name));
}
echo html_writer::end_tag('ul');

echo $OUTPUT->footer();
