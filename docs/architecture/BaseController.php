<?php

namespace Infrastructure;

class BaseController {
    
    protected $Ioc;
    protected $db;
    
    private static $instance;

    public function __construct() {
        self::$instance =& $this;

        spl_autoload_extensions('.php');

        spl_autoload_register(function($classname) {
            if (strpos($classname, '\\') !== false) {
                $classfile = str_replace('\\', DIRECTORY_SEPARATOR, $classname);

                if ($classname[0] !== '/') {
                    $classfile = APPPATH. $classfile. '.php';
                }

                require($classfile);
            }
        });

        $this->Ioc = new \Infrastructure\Ioc();
        $this->db = new \Infrastructure\Database();

        $requestPath = trim((string) parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH), '/');
        $firstSegment = explode('/', $requestPath)[0] ?? '';

        if (!$this->ActiveUserMapper->isInitialized()) {
            if ($firstSegment === 'api') {
                $this->initializeActiveUser();
            }
            else {
                $this->initializeWebActiveUser();
            }
        }

        //TODO: add request log start
    }

    private function initializeActiveUser() {
        $apiKey = $this->RequestHelper->getApiKey();

        if ($apiKey === false) {
            $this->ResponseHelper->sendForbidden(
                $this->GenericForbiddenError->get()
            );
        }

        $userId = $this->ApiKeyStorage->getUserIdByApiKey($apiKey);

        if (!$userId) {
            $this->ResponseHelper->sendInvalidApiKeyResponse();
        }

        $userData = $this->UserStorage->getById($userId);

        if (!$userData) {
            $this->ResponseHelper->sendInvalidApiKeyResponse();
        }

        $this->ActiveUserMapper->init($userData);

        if (!$userData->is_enabled) {
            $this->ResponseHelper->sendDisabledUserResponse();
        }
    }

    private function clearWebUserSession() {
        $authContext = function_exists('app_session_get_auth_context')
            ? app_session_get_auth_context()
            : null;

        if ($authContext !== null) {
            $this->WebUserSessionStorage->deleteBySelector($authContext['selector']);
        }

        if (function_exists('app_session_clear_auth_context')) {
            app_session_clear_auth_context();
        }
    }

    public function __get($name) {
        if (!$this->Ioc) {
            spl_autoload_extensions('.php');

            spl_autoload_register(function($classname) {
                if (strpos($classname, '\\') !== false) {
                    $classfile = str_replace('\\', '/', $classname);

                    if ($classname[0] !== '/') {
                        $classfile = APPPATH. $classfile. '.php';
                    }

                    require($classfile);
                }
            });
        }

        $this->Ioc = new \Infrastructure\Ioc();

        if (!isset($this->$name)) {
            $this->$name = $this->Ioc->getDependency($name, 'Controller');
        }

        return $this->$name;
    }

    public function _remap($firstSegment, $urlSegments) {
        try {
            $resourceParams = $this->seperateClassPartsAndParams($firstSegment, $urlSegments);

            if ($resourceParams === false || !$this->loadResourceFiles($resourceParams)) {
                $this->ResponseHelper->sendNotFound(
                    $this->GenericNotFoundError->get()
                );
            }

            $requestMethod = $this->RequestHelper->getMethod();
            $resource = new $resourceParams->class($this->Ioc);

            $resourceMethod = array($resource, $requestMethod);

            if (!is_callable($resourceMethod)) {
                $resource->options();

                $this->ResponseHelper->sendMethodNotAllowed(
                    $this->GenericMethodNotAllowedError->get($requestMethod)
                );
            }

            if (
                ($requestMethod === 'post' || $requestMethod === 'put' || $requestMethod === 'patch') &&
                $this->RequestHelper->checkIfTheBodyCointainsInvalidJson()
            ) {
                $this->ResponseHelper->sendBadRequest(
                    $this->GenericBodyNotJsonError->get()
                );
            }

            call_user_func_array($resourceMethod, $resourceParams->params);
        }
        catch (\exceptions\ClientErrors\BadRequest $ex) {
            $this->ResponseHelper->sendBadRequest($ex->getError());
        }
        catch (\exceptions\ClientErrors\Unauthorized $ex) {
            $this->ResponseHelper->sendUnauthorized($ex->getError());
        }
        catch (\exceptions\ClientErrors\Forbidden $ex) {
            $this->ResponseHelper->sendForbidden($ex->getError());
        }
        catch (\exceptions\ClientErrors\NotFound $ex) {
            $this->ResponseHelper->sendNotFound($ex->getError());
        }
        catch (\exceptions\ClientErrors\Conflict $ex) {
            $this->ResponseHelper->sendConflict($ex->getError());
        }
        catch (\exceptions\DatabaseError $ex) {
            $this->ResponseHelper->sendInternalServerError();
        }
        catch (\exceptions\ExternalError $ex) {
            $this->ResponseHelper->sendServiceUnavailable();
        }
        catch (\Exception $ex) {
            $subject = 'Unhandled '. get_class($ex);
            $message = 'Message: '. $ex->getMessage(). "\n\nTrace: ". json_encode($ex->getTrace(), JSON_PRETTY_PRINT). "\n\nPost:\n". json_encode($this->RequestHelper->getBody(), JSON_PRETTY_PRINT). "\n\nQuery:\n". json_encode($this->RequestHelper->getQuery(), JSON_PRETTY_PRINT);
         
            $logDir = APPPATH. 'logs';
            
            if (!is_dir($logDir)) {
                @mkdir($logDir, 0755, true);
            }
            $fileForErrorLog = $logDir. DIRECTORY_SEPARATOR. 'error_'. date('Y-m-d'). '.log';
            $fileForErrorLogHandle = fopen($fileForErrorLog, 'a');

            if ($fileForErrorLogHandle !== false) {
                fwrite($fileForErrorLogHandle, $subject. "\n". $message. "\n\n");
                fclose($fileForErrorLogHandle);
            }
            
            $this->ResponseHelper->sendInternalServerError();
        }
    }

    private function initializeWebActiveUser() {
        if (session_status() !== PHP_SESSION_ACTIVE) {
            return;
        }

        $authContext = function_exists('app_session_get_auth_context')
            ? app_session_get_auth_context()
            : null;

        if ($authContext === null) {
            if (
                isset($_SESSION['auth_selector']) ||
                isset($_SESSION['auth_token'])
            ) {
                $this->clearWebUserSession();
            }

            return;
        }

        $userId = $this->WebUserSessionStorage->getUserIdBySelectorAndToken(
            $authContext['selector'],
            $authContext['token'],
            app_session_user_agent_hash()
        );

        if (!$userId) {
            $this->clearWebUserSession();

            return;
        }

        $userData = $this->UserStorage->getById($userId);

        if (!$userData || !$userData->is_enabled) {
            $this->clearWebUserSession();

            return;
        }

        $this->ActiveUserMapper->init($userData);
    }

    private function seperateClassPartsAndParams($firstSegment, $urlSegments) {
        if (strspn($firstSegment, 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') != strlen($firstSegment)) {
            return false;
        }

        $firstSegmentUCFirst = ucfirst($firstSegment);

        if (!is_dir(APPPATH. 'controllers/'. $firstSegmentUCFirst)) {
            return false;
        }

        $resourceParams = new \stdClass();
        $resourceParams->classParts = array($firstSegmentUCFirst);
        $resourceParams->filePath = APPPATH. 'controllers/'. $firstSegmentUCFirst;
        $resourceParams->params = array();

        foreach ($urlSegments as $segment) {
            $segmentLenght = strlen($segment);

            if (strspn($segment, 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') == $segmentLenght) {
                $segmentUCFirst = ucfirst($segment);
                $path = $resourceParams->filePath. '/'. $segmentUCFirst;

                if (is_dir($path)) {
                    $resourceParams->classParts[] = $segmentUCFirst;
                    $resourceParams->filePath = $path;

                    continue;
                }
            }

            if (strspn($segment, '0123456789') == $segmentLenght) {
                $resourceParams->filePath .= '/{id}';

                if (!is_dir($resourceParams->filePath)) {
                    return false;
                }

                $resourceParams->classParts[] = 'ID';
                $resourceParams->params[] = (int)$segment;
            }
            else {
                $resourceParams->filePath .= '/{str}';

                if (!is_dir(($resourceParams->filePath))) {
                    return false;
                }

                $resourceParams->classParts[] = 'STR';
                $resourceParams->params[] = $segment;
            }
        }

        $resourceParams->class = implode('_', $resourceParams->classParts);

        $resourceParams->filePath .= '/'. $resourceParams->class. '.php';

        if (!file_exists($resourceParams->filePath)) {
            return false;
        }

        return $resourceParams;
    }

    private function loadResourceFiles($resourceParams) {
        require(APPPATH. '/controllers/AbstractController.php');

        require $resourceParams->filePath;

        return class_exists($resourceParams->class, false);
    }

    public static function &get_instance() {
        return self::$instance;
    }
}
