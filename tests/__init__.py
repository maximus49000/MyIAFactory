import shutil
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "exemples" / "demo"


def copie_demo(destination, source=DEMO):
    """Copie la démo sans ce que le serveur y écrit quand on la lance sur place (historiques, équipe) :
    un test ne doit dépendre ni de l'état de la machine ni de prix lus un jour sur Internet."""
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns("*.jsonl", "*.tmp", "equipe.json", "__pycache__"))
    return destination


CLE_TEST = bytes.fromhex("11" * 32)   # la clé des connaissances de test (voir `_connaissances_de_test`)


def connaissances_jetables(test, actif=True, niveau="standard"):
    """Un dossier de connaissances neuf pour un test (rien ne passe d'un test à l'autre)."""
    import json
    import os
    import tempfile
    from unittest import mock
    t = tempfile.TemporaryDirectory()
    test.addCleanup(t.cleanup)
    d = Path(t.name)
    (d / "partage.json").write_text(json.dumps({"actif": actif, "niveau": niveau}), encoding="utf-8")
    if actif:
        (d / "cle").write_text(CLE_TEST.hex(), encoding="utf-8")
    patch = mock.patch.dict(os.environ, {"MYIAFACTORY_CONNAISSANCES": str(d)})
    patch.start()
    test.addCleanup(patch.stop)
    return d


def _connaissances_de_test():
    """Jamais la file ni la clé réelles du poste (`~/MyIAFactory/connaissances`) : un dossier jetable, partage actif au
    niveau standard avec une clé de test, pour que la validation d'une leçon écrive et pousse comme avant."""
    import json
    import os
    import tempfile
    if os.environ.get("MYIAFACTORY_CONNAISSANCES"):
        return
    d = Path(tempfile.mkdtemp(prefix="connaissances-test-"))
    (d / "partage.json").write_text(json.dumps({"actif": True, "niveau": "standard"}), encoding="utf-8")
    (d / "cle").write_text("11" * 32, encoding="utf-8")
    os.environ["MYIAFACTORY_CONNAISSANCES"] = str(d)
    os.environ["MYIAFACTORY_DEPOT_CLE"] = str(d / "pas-de-depot")


_connaissances_de_test()
