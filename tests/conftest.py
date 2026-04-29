import sys
from unittest.mock import MagicMock

# Stub out python-telegram-bot so tests don't need the package installed
sys.modules.setdefault("telegram", MagicMock())
sys.modules.setdefault("telegram.ext", MagicMock())

# Stub out pymongo so tests don't need the package installed
sys.modules.setdefault("pymongo", MagicMock())
sys.modules.setdefault("pymongo.mongo_client", MagicMock())
sys.modules.setdefault("pymongo.server_api", MagicMock())

# Stub out SecretVariables (credentials not present in test env)
secret_stub = MagicMock()
secret_stub.MONGODB_URI = "mongodb://localhost"
secret_stub.COLLECTION = "test"
sys.modules.setdefault("SecretVariables", secret_stub)
