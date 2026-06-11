import yaml
from utils.path_tool import get_abs_path


def load_yaml_config(config_path: str, encoding: str = "utf-8") -> dict:
    """加载 YAML 配置；本地配置不存在时返回空字典，方便开源和本地分离。"""
    try:
        with open(config_path, "r", encoding=encoding) as f:
            return yaml.load(f, Loader=yaml.FullLoader) or {}
    except FileNotFoundError:
        return {}


def load_agent_config(config_path: str = get_abs_path("config/agent.yml"), encoding: str = "utf-8"):
    return load_yaml_config(config_path, encoding=encoding)


agent_conf = load_agent_config()

if __name__ == '__main__':
    print(agent_conf)
