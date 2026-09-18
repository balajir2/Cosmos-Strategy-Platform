import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_mount_frontend_if_built_skips_when_directory_missing(tmp_path):
    app = FastAPI()
    initial_routes = len(app.routes)
    mounted = main.mount_frontend_if_built(app, str(tmp_path / "does-not-exist"))
    assert mounted is False
    assert len(app.routes) == initial_routes


def test_mount_frontend_if_built_mounts_when_directory_exists(tmp_path):
    build_dir = tmp_path / "out"
    build_dir.mkdir()
    (build_dir / "index.html").write_text("<html></html>")
    app = FastAPI()
    initial_routes = len(app.routes)
    mounted = main.mount_frontend_if_built(app, str(build_dir))
    assert mounted is True
    assert len(app.routes) == initial_routes + 1


def test_mount_frontend_serves_clean_url_for_nested_static_export_route(tmp_path):
    """Regression test: Next.js's static export with trailingSlash: true emits
    admin/project/index.html for the /admin/project route (not the flat
    admin/project.html it would emit without that setting). StaticFiles(html=True)
    can only resolve the nested-index-html shape, not the flat one - it has no
    logic to append ".html" to an extensionless request path. This test builds
    the nested shape directly and confirms a clean-URL GET actually resolves,
    catching the exact bug a flat-file build would silently reintroduce."""
    build_dir = tmp_path / "out"
    (build_dir / "admin" / "project").mkdir(parents=True)
    (build_dir / "index.html").write_text("<html>home</html>")
    (build_dir / "admin" / "project" / "index.html").write_text("<html>project</html>")

    app = FastAPI()
    main.mount_frontend_if_built(app, str(build_dir))
    client = TestClient(app)

    response = client.get("/admin/project", follow_redirects=True)

    assert response.status_code == 200
    assert "project" in response.text
