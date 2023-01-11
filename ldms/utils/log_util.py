import logging 
import logging.handlers
import os

def get_log_files():
    """Get location of log files

    Returns:
        list(main_log, error_log)
    """
    main_log = os.environ.get("LOGFILE", "logs/main.log") 
    error_log = os.environ.get("ERROR_LOGFILE", "logs/error.log")

    # Create the file if it does not exist
    if not os.path.exists(main_log):
        open(main_log, 'w').close()
    if not os.path.exists(error_log):
        open(error_log, 'w').close()
    return (main_log, error_log)

def _get_logger(is_error):
    """Get a logger 

    Args:
        is_error (bool): Are we logging errors ?

    Returns:
        Logger
    """
    LOG_FILES = get_log_files()
    handler = logging.handlers.RotatingFileHandler(LOG_FILES[0] if not is_error else LOG_FILES[1],
        maxBytes=10*1024*1024, #set to 10mb max size
        backupCount=100)
    # LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FORMAT = '[%(levelname)s] %(asctime)s | %(message)s' 
    # formatter = logging.Formatter(logging.BASIC_FORMAT)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)

    logger = logging.getLogger('ldms.apps.{__name__}' + str(is_error))
    logger.setLevel(logging.WARNING if is_error else logging.INFO)
    if (logger.hasHandlers()):# Do this to stop duplicated output
        logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = True
    return logger
 
def log(message):
    _get_logger(False).info(str(message))

def log_error(error):
    _get_logger(True).exception(str(error))