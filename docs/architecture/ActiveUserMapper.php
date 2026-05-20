<?php

namespace mappers;

class ActiveUserMapper extends AbstractMapper {

    protected $userData = false;
    protected $apiKey = null;

    public function init($userData) {
        $this->userData = $userData;
        $this->apiKey = null;
    }

    public function isInitialized() {
        return $this->userData !== false;
    }

    public function getId() {
        if (isset($this->userData->user_id)) {
            return $this->userData->user_id;
        }

        throw new \RuntimeException('The active user is not initialized');
    }

    public function getUsername() {
        if (isset($this->userData->username)) {
            return $this->userData->username;
        }

        throw new \RuntimeException('The active user is not initialized');
    }

    public function isEnabled() {
        if (isset($this->userData->is_enabled)) {
            return $this->userData->is_enabled;
        }

        throw new \RuntimeException('The active user is not initialized');
    }

    public function getApiKey() {
        if (!isset($this->userData->user_id)) {
            throw new \RuntimeException('The active user is not initialized');
        }

        if (is_null($this->apiKey)) {
            $this->apiKey = $this->ApiKeyStorage->getApiKeyByUserId($this->userData->user_id);
        }

        return $this->apiKey;
    }

    public function isWaiter() {
        if (isset($this->userData->is_manager)) {
            return (int) $this->userData->is_manager === 0;
        }

        throw new \RuntimeException('The active user is not initialized');
    }

    public function isManager() {
        return !$this->isWaiter();
    }


}
