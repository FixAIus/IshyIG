import json

async def log(level, msg, **kwargs):
    """Centralized logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))
