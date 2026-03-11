<?php
// SPDX-License-Identifier: Apache-2.0

defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('modsettingchatlearning', get_string('pluginsettingsname', 'mod_chatlearning'));

    $settings->add(new admin_setting_configtext(
        'mod_chatlearning/baseurl',
        get_string('setting:baseurl', 'mod_chatlearning'),
        get_string('setting:baseurl_desc', 'mod_chatlearning'),
        '',
        PARAM_URL
    ));

    $settings->add(new admin_setting_configpasswordunmask(
        'mod_chatlearning/apikey',
        get_string('setting:apikey', 'mod_chatlearning'),
        get_string('setting:apikey_desc', 'mod_chatlearning'),
        ''
    ));

    $settings->add(new admin_setting_configtext(
        'mod_chatlearning/timeout',
        get_string('setting:timeout', 'mod_chatlearning'),
        get_string('setting:timeout_desc', 'mod_chatlearning'),
        30,
        PARAM_INT
    ));

    $ADMIN->add('modsettings', $settings);
}
