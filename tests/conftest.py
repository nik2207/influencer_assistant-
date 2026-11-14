import os
import tempfile

# Must run before any app import so settings pick these up.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-at-least-32-bytes"
os.environ["GOOGLE_CLIENT_ID"] = "cid.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "csecret"

from app.routers import auth  # noqa: E402

auth.limiter.enabled = False  # tests register many users from one IP
