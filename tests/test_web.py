import re

from fastapi.testclient import TestClient

from app.main import create_app
from app.presentation.web import DIRECTORIO


def cliente(settings) -> TestClient:
    return TestClient(create_app(settings))


def test_la_interfaz_se_sirve_en_app_con_csp(settings) -> None:
    with cliente(settings) as client:
        pagina = client.get("/app/")
    assert pagina.status_code == 200
    assert pagina.headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in pagina.text
    assert 'src="js/main.js"' in pagina.text


def test_tipos_de_contenido_que_exige_el_navegador(settings) -> None:
    esperados = {
        "/app/js/main.js": "text/javascript",
        "/app/css/base.css": "text/css",
        "/app/assets/icons/sprite.svg": "image/svg+xml",
        "/app/assets/fonts/inter-latin-wght.woff2": "font/woff2",
    }
    with cliente(settings) as client:
        for ruta, tipo in esperados.items():
            respuesta = client.get(ruta)
            assert respuesta.status_code == 200, ruta
            assert respuesta.headers["content-type"].startswith(tipo), ruta


def test_el_montaje_no_altera_las_rutas_existentes(settings) -> None:
    with cliente(settings) as client:
        assert client.get("/").json()["docs"] == "/docs"
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401


def test_la_interfaz_no_usa_recursos_externos_ni_inserta_html() -> None:
    """Exigencias de docs/frontend.md: todo local y datos de la API solo con textContent."""
    externos = re.compile(r"""(?:src|href)=["']https?://|url\(["']?https?://|@import""")
    for archivo in DIRECTORIO.rglob("*"):
        if archivo.suffix in {".html", ".css", ".js"}:
            contenido = archivo.read_text(encoding="utf-8")
            assert not externos.search(contenido), archivo
            assert ".innerHTML" not in contenido, archivo
            assert ".outerHTML" not in contenido, archivo
            assert "insertAdjacentHTML" not in contenido, archivo


def test_todo_icono_usado_existe_en_el_sprite() -> None:
    sprite = (DIRECTORIO / "assets/icons/sprite.svg").read_text(encoding="utf-8")
    definidos = set(re.findall(r'<symbol id="([^"]+)"', sprite))
    usados: set[str] = set()
    for archivo in (DIRECTORIO / "js").rglob("*.js"):
        contenido = archivo.read_text(encoding="utf-8")
        usados |= set(re.findall(r"""ic\('([a-z0-9-]+)'""", contenido))
        usados |= set(re.findall(r"""chip\('[a-z]*', '([a-z0-9-]+)'""", contenido))
    assert usados - definidos == set()


def test_las_pantallas_de_la_clinica_se_cargan_y_respetan_la_csp() -> None:
    principal = (DIRECTORIO / "js/main.js").read_text(encoding="utf-8")
    assert "./modulos/clinica.js" in principal
    assert 'href="css/clinica.css"' in (DIRECTORIO / "index.html").read_text(encoding="utf-8")
    for archivo in (DIRECTORIO / "js/vistas/clinica").rglob("*.js"):
        # style-src 'self' bloquea el atributo style; `estilo` usa el CSSOM, que si se permite.
        assert not re.search(r"style:", archivo.read_text(encoding="utf-8")), archivo


def test_las_rutas_de_los_modulos_importados_existen() -> None:
    for archivo in (DIRECTORIO / "js").rglob("*.js"):
        contenido = archivo.read_text(encoding="utf-8")
        for destino in re.findall(r"""from '(\.[^']+)'|import '(\.[^']+)'""", contenido):
            ruta = destino[0] or destino[1]
            assert (archivo.parent / ruta).resolve().is_file(), (archivo, ruta)
