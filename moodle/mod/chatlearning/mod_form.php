<?php
// SPDX-License-Identifier: Apache-2.0

require_once($CFG->dirroot . '/course/moodleform_mod.php');

class mod_chatlearning_mod_form extends moodleform_mod {
    public function definition() {
        $mform = $this->_form;

        $mform->addElement('text', 'name', get_string('activityname', 'mod_chatlearning'), ['size' => '64']);
        $mform->setType('name', PARAM_TEXT);
        $mform->addRule('name', null, 'required', null, 'client');

        $this->standard_intro_elements(get_string('intro', 'mod_chatlearning'));

        $mform->addElement('textarea', 'contextprompt', get_string('contextprompt', 'mod_chatlearning'), ['rows' => 4, 'cols' => 60]);
        $mform->setType('contextprompt', PARAM_RAW);
        $mform->addHelpButton('contextprompt', 'contextprompt', 'mod_chatlearning');

        $mform->addElement('advcheckbox', 'allowuploads', get_string('allowuploads', 'mod_chatlearning'));
        $mform->setDefault('allowuploads', 1);

        $mform->addElement('text', 'allowedmimetypes', get_string('allowedmimetypes', 'mod_chatlearning'));
        $mform->setType('allowedmimetypes', PARAM_TEXT);
        $mform->addHelpButton('allowedmimetypes', 'allowedmimetypes', 'mod_chatlearning');

        $scopeoptions = [
            'currentcourse' => get_string('documentscope:currentcourse', 'mod_chatlearning'),
            'enrolledcourses' => get_string('documentscope:enrolledcourses', 'mod_chatlearning'),
            'allcourses' => get_string('documentscope:allcourses', 'mod_chatlearning'),
        ];
        $mform->addElement('select', 'documentscope', get_string('documentscope', 'mod_chatlearning'), $scopeoptions);
        $mform->setType('documentscope', PARAM_ALPHA);
        $mform->setDefault('documentscope', 'enrolledcourses');
        $mform->addHelpButton('documentscope', 'documentscope', 'mod_chatlearning');

        $mform->addElement('advcheckbox', 'allowglobaldocs', get_string('allowglobaldocs', 'mod_chatlearning'));
        $mform->setDefault('allowglobaldocs', 0);
        $mform->addHelpButton('allowglobaldocs', 'allowglobaldocs', 'mod_chatlearning');

        $mform->addElement('advcheckbox', 'allowmoodlesync', get_string('allowmoodlesync', 'mod_chatlearning'));
        $mform->setDefault('allowmoodlesync', 1);
        $mform->addHelpButton('allowmoodlesync', 'allowmoodlesync', 'mod_chatlearning');

        $mform->addElement('advcheckbox', 'sourcepdf', get_string('sourcepdf', 'mod_chatlearning'));
        $mform->setDefault('sourcepdf', 1);

        $mform->addElement('advcheckbox', 'sourcescorm', get_string('sourcescorm', 'mod_chatlearning'));
        $mform->setDefault('sourcescorm', 1);

        $this->standard_coursemodule_elements();

        $this->add_action_buttons();
    }

    public function data_preprocessing(&$data) {
        parent::data_preprocessing($data);
        if (!isset($data['allowuploads'])) {
            $data['allowuploads'] = 1;
        }
        if (!isset($data['documentscope'])) {
            $data['documentscope'] = 'enrolledcourses';
        }
        if (!isset($data['allowglobaldocs'])) {
            $data['allowglobaldocs'] = 0;
        }
        if (!isset($data['allowmoodlesync'])) {
            $data['allowmoodlesync'] = 1;
        }
        if (!isset($data['sourcepdf'])) {
            $data['sourcepdf'] = 1;
        }
        if (!isset($data['sourcescorm'])) {
            $data['sourcescorm'] = 1;
        }
    }
}
