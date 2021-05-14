import logging


# Set up logging
logger = logging.getLogger(__name__)
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler('app.log')
c_handler.setLevel(logging.DEBUG)
f_handler.setLevel(logging.ERROR)

# Create formatters and add them to handlers
fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
c_format = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
f_format = logging.Formatter(fmt=fmt, datefmt='%d-%b-%y %H:%M:%S')
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)

logger.addHandler(c_handler)
logger.addHandler(f_handler)
logger.setLevel(logging.DEBUG)