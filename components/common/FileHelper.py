import yaml


def get_config(file_name="config.yaml") -> dict:
    to_ret = None
    with open(file_name, "r") as stream:
        try:
            to_ret = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return to_ret
