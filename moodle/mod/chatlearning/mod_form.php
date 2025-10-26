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

        $this->standard_coursemodule_elements();

        $this->add_action_buttons();
    }

    public function data_preprocessing(&$data) {
        parent::data_preprocessing($data);
        if (!isset($data['allowuploads'])) {
            $data['allowuploads'] = 1;
        }
    }
}
