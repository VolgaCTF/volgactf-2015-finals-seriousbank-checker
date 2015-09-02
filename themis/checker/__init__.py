# -*- coding: utf-8 -*-
from abc import ABCMeta, abstractmethod
import beanstalkc
import json
from sys import exc_info, stdout
import logging
import os
from enum import Enum


class Result(Enum):
    UP = 101
    CORRUPT = 102
    MUMBLE = 103
    DOWN = 104
    INTERNAL_ERROR = 110


class Server(object):
    __metaclass__ = ABCMeta

    def __init__(self):
        self._logger = self.get_logger()

    def get_logger(self):
        console_handler = logging.StreamHandler(stdout)
        log_format = '[%(asctime)s] - %(levelname)s - %(message)s'
        formatter = logging.Formatter(log_format)
        console_handler.setFormatter(formatter)
        logger = logging.Logger(__name__)
        level_str = os.getenv('LOG_LEVEL', 'INFO')
        if level_str == 'CRITICAL':
            level = logging.CRITICAL
        elif level_str == 'ERROR':
            level = logging.ERROR
        elif level_str == 'WARNING':
            level = logging.WARNING
        elif level_str == 'INFO':
            level = logging.INFO
        elif level_str == 'DEBUG':
            level = logging.DEBUG
        elif level_str == 'NOTSET':
            level = logging.NOTSET
        else:
            level = logging.INFO
        logger.setLevel(level)
        logger.addHandler(console_handler)
        return logger

    @property
    def logger(self):
        return self._logger

    @abstractmethod
    def push(self, endpoint, flag_id, flag):
        pass

    @abstractmethod
    def pull(self, endpoint, flag_id, flag):
        pass

    def internal_push(self, endpoint, flag_id, flag):
        result, new_flag_id = Result.INTERNAL_ERROR, flag_id
        try:
            result, new_flag_id = self.push(endpoint, flag_id, flag)
        except KeyboardInterrupt:
            raise
        except Exception:
            self.logger.exception('An exception occurred', exc_info=exc_info())
        return result.value, new_flag_id

    def internal_pull(self, endpoint, flag_id, flag):
        result = Result.INTERNAL_ERROR
        try:
            result = self.pull(endpoint, flag_id, flag)
        except KeyboardInterrupt:
            raise
        except Exception:
            self.logger.exception('An exception occurred', exc_info=exc_info())
        return result.value

    def run(self):
        host, port = os.getenv('BEANSTALKD_URI').split(':')
        beanstalk = beanstalkc.Connection(host=host, port=int(port))
        self.logger.info('Connected to beanstalk server')

        beanstalk.watch(os.getenv('TUBE_LISTEN'))

        running = True
        while running:
            job = None
            try:
                job = beanstalk.reserve()
                job_data = json.loads(job.body)
                job_result = None

                if job_data['operation'] == 'push':
                    status, flag_id = self.internal_push(
                        job_data['endpoint'],
                        job_data['flag_id'],
                        job_data['flag'])

                    job_result = dict(operation=job_data['operation'],
                                      status=status,
                                      flag=job_data['flag'],
                                      flag_id=flag_id,
                                      endpoint=job_data['endpoint'])

                    self.logger.info(
                        'PUSH flag {0} to {1}: result {2}, flag_id {3}'.format(
                            job_data['flag'],
                            job_data['endpoint'],
                            job_result['status'],
                            job_result['flag_id']))
                elif job_data['operation'] == 'pull':
                    status = self.internal_pull(
                        job_data['endpoint'],
                        job_data['flag_id'],
                        job_data['flag'])

                    job_result = dict(operation=job_data['operation'],
                                      request_id=job_data['request_id'],
                                      status=status)

                    self.logger.info(
                        'PULL flag {0} from {1} with flag_id {2}: result {3}'.format(
                            job_data['flag'],
                            job_data['endpoint'],
                            job_data['flag_id'],
                            job_result['status']))
                else:
                    self.logger.warn('Unknown job!')

                if job_result:
                    beanstalk.use(os.getenv('TUBE_REPORT'))
                    beanstalk.put(json.dumps(job_result))
            except KeyboardInterrupt:
                running = False
                self.logger.info('Received shutdown signal')
            except beanstalkc.SocketError:
                raise
            except Exception:
                self.logger.exception('An exception occurred',
                                      exc_info=exc_info())
            finally:
                if job:
                    job.delete()

        beanstalk.close()
        self.logger.info('Disconnected from beanstalk server')
