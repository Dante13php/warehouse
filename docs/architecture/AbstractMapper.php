<?php

namespace mappers;

abstract class AbstractMapper {

    private $Ioc;

    public function __construct($Ioc) {
        $this->Ioc = $Ioc;
    }

    public function __get($name) {
        $this->$name = $this->Ioc->getDependency($name, 'Mapper');

        return $this->$name;
    }
}