import os


class GlobalVar:
    PROJECT_BASE_PATH = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    CONFIG_PATH = os.path.join(PROJECT_BASE_PATH, 'configs', 'conf.json')

    LOG_FOLDER_PATH = os.path.join(PROJECT_BASE_PATH, 'logs')