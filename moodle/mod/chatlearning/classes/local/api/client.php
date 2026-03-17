<?php
// SPDX-License-Identifier: Apache-2.0

namespace mod_chatlearning\local\api;

use coding_exception;
use curl;
use moodle_exception;
use stdClass;

class client {
    private string $baseurl;
    private ?string $apikey;
    private int $timeout;

    public function __construct() {
        $config = get_config('mod_chatlearning');
        $baseurl = $config->baseurl ?? '';
        $this->baseurl = rtrim($baseurl, '/');
        $this->apikey = $config->apikey ?? null;
        $this->timeout = (int)($config->timeout ?? 30);

        if ($this->baseurl === '') {
            throw new moodle_exception('status:requiresconfig', 'mod_chatlearning');
        }
    }

    public function get_documents(stdClass $context): array {
        $params = [
            'include_global' => !empty($context->includeglobaldocs) ? 'true' : 'false',
        ];
        if (!empty($context->allowedcourseids) && is_array($context->allowedcourseids)) {
            $params['course_id'] = array_values($context->allowedcourseids);
        }
        if (!empty($context->allowedsourcetypes) && is_array($context->allowedsourcetypes)) {
            $params['source_type'] = array_values($context->allowedsourcetypes);
        }
        if (($context->documentscope ?? '') === 'currentcourse') {
            $params['moodle_cmid'] = (string)$context->cmid;
        }
        $response = $this->request('get', '/api/documents', $params);
        return $response['documents'] ?? $response;
    }

    public function submit_question(stdClass $context, string $question): array {
        $payload = array_merge($this->build_context_params($context), [
            'question' => $question,
            'context_prompt' => $context->contextprompt ?? '',
        ]);
        return $this->request_stream('/api/chat', $payload);
    }

    public function upload_document(stdClass $context, array $fileinfo, array $extrafields = []): array {
        $params = $this->build_context_params($context);
        $payload = array_merge($params, $extrafields, ['file' => $this->prepare_file($fileinfo)]);
        return $this->request('upload', '/api/documents', [], $payload);
    }

    public function scrape_url(stdClass $context, string $url): array {
        $payload = array_merge($this->build_context_params($context), ['url' => $url]);
        return $this->request('post', '/api/scrape', [], $payload);
    }

    public function delete_document(stdClass $context, string $documentid): array {
        $payload = $this->build_context_params($context);
        $path = '/api/documents/' . rawurlencode($documentid) . '/delete';
        return $this->request('post', $path, [], $payload);
    }

    private function create_curl_client(): curl {
        return new curl();
    }

    private function build_request_options(array $headers = []): array {
        $options = [
            'CURLOPT_TIMEOUT' => $this->timeout,
            'CURLOPT_SSL_VERIFYPEER' => 1,
            'CURLOPT_SSL_VERIFYHOST' => 2,
        ];
        if (!empty($headers)) {
            $options['CURLOPT_HTTPHEADER'] = $headers;
        }
        return $options;
    }

    private function request(string $method, string $path, array $query = [], ?array $body = null): array {
        $curl = $this->create_curl_client();
        $url = $this->baseurl . $path;

        if (!empty($query)) {
            $url .= (strpos($url, '?') === false ? '?' : '&') . $this->build_query_string($query);
        }

        $headers = ['Accept: application/json'];
        if ($this->apikey) {
            $headers[] = 'Authorization: Bearer ' . $this->apikey;
        }

        switch ($method) {
            case 'get':
                $response = $curl->get($url, $this->build_request_options($headers));
                break;
            case 'post':
                $headers[] = 'Content-Type: application/json';
                $response = $curl->post($url, json_encode($body ?? []), $this->build_request_options($headers));
                break;
            case 'upload':
                if ($body === null) {
                    throw new coding_exception('Upload request requires a body.');
                }
                $response = $curl->post($url, $body, $this->build_request_options($headers));
                break;
            default:
                throw new coding_exception('Unsupported method: ' . $method);
        }

        $info = $curl->get_info();
        $status = $info['http_code'] ?? 0;

        if ($status < 200 || $status >= 300) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', (string)$status);
        }

        $decoded = json_decode($response, true);
        if ($decoded === null && json_last_error() !== JSON_ERROR_NONE) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', 'Invalid JSON response');
        }

        return $decoded ?? [];
    }

    private function request_stream(string $path, array $body): array {
        $curl = $this->create_curl_client();
        $url = $this->baseurl . $path;

        $headers = ['Accept: application/x-ndjson', 'Content-Type: application/json'];
        if ($this->apikey) {
            $headers[] = 'Authorization: Bearer ' . $this->apikey;
        }

        $response = $curl->post($url, json_encode($body), $this->build_request_options($headers));
        $info = $curl->get_info();
        $status = $info['http_code'] ?? 0;

        if ($status < 200 || $status >= 300) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', (string)$status);
        }

        $answer = '';
        $citations = [];

        $lines = preg_split("/\r?\n/", trim((string)$response));
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '') {
                continue;
            }

            $payload = json_decode($line, true);
            if (!is_array($payload)) {
                continue;
            }

            $type = $payload['type'] ?? '';
            if ($type === 'references' && !empty($payload['citations'])) {
                $citations = $payload['citations'];
            } elseif ($type === 'delta' && !empty($payload['content'])) {
                $answer .= (string)$payload['content'];
            } elseif ($type === 'done') {
                if (!empty($payload['answer'])) {
                    $answer = (string)$payload['answer'];
                }
                if (!empty($payload['citations'])) {
                    $citations = $payload['citations'];
                }
            } elseif ($type === 'error') {
                $message = $payload['message'] ?? 'Unknown error';
                throw new moodle_exception('status:error', 'mod_chatlearning', '', $message);
            }
        }

        return [
            'answer' => trim($answer),
            'citations' => $citations,
        ];
    }

    private function build_context_params(stdClass $context): array {
        $params = [
            'moodle_course_id' => $context->courseid,
            'moodle_cmid' => (string)$context->cmid,
            'moodle_user_id' => $context->userid,
            'moodle_username' => $context->username,
            'moodle_fullname' => $context->fullname,
            'chatlearning_instance' => $context->instanceid,
            'course_id' => (string)$context->courseid,
            'include_global_docs' => !empty($context->includeglobaldocs),
            'document_scope' => $context->documentscope ?? 'enrolledcourses',
        ];
        if (!empty($context->allowedcourseids) && is_array($context->allowedcourseids)) {
            $params['allowed_course_ids'] = array_map('strval', array_values($context->allowedcourseids));
        }
        if (!empty($context->allowedsourcetypes) && is_array($context->allowedsourcetypes)) {
            $params['allowed_source_types'] = array_map('strval', array_values($context->allowedsourcetypes));
        }
        return $params;
    }

    private function prepare_file(array $fileinfo) {
        if (!isset($fileinfo['tmp_name']) || !is_readable($fileinfo['tmp_name'])) {
            throw new moodle_exception('status:error', 'mod_chatlearning', '', 'Uploaded file not found');
        }

        $filename = $fileinfo['name'] ?? basename($fileinfo['tmp_name']);
        $mimetype = $fileinfo['type'] ?? 'application/octet-stream';

        if (function_exists('curl_file_create')) {
            return curl_file_create($fileinfo['tmp_name'], $mimetype, $filename);
        }

        return '@' . $fileinfo['tmp_name'];
    }

    private function build_query_string(array $query): string {
        $parts = [];
        foreach ($query as $key => $value) {
            if (is_array($value)) {
                foreach ($value as $item) {
                    $parts[] = rawurlencode((string)$key) . '=' . rawurlencode((string)$item);
                }
                continue;
            }
            if ($value === null) {
                continue;
            }
            $parts[] = rawurlencode((string)$key) . '=' . rawurlencode((string)$value);
        }
        return implode('&', $parts);
    }
}
