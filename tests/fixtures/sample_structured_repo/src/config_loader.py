def get_database_host(config: dict) -> str:
    return config["database"]["host"]


def get_api_timeout(config: dict) -> int:
    return config.get("api", {}).get("timeout", 30)
