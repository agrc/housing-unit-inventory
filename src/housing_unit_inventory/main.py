import logging

from . import county_scripts


def process():
    logging.basicConfig(level=logging.DEBUG)
    county_scripts.davis_county()


if __name__ == '__main__':
    process()
