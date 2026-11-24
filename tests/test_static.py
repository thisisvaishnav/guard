from guard_cli.ingest.static import analyze_repo


def make(tmp_path, files):
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return analyze_repo(tmp_path)


def test_same_module_and_cross_module_calls(tmp_path):
    r = make(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "def helper():\n    return 1\n\ndef main():\n    return helper()\n",
        "pkg/b.py": "from pkg.a import helper\nimport pkg.a as A\n\ndef use():\n    helper()\n    A.main()\n",
    })
    assert ("pkg/a.py::main", "pkg/a.py::helper") in r.call_edges
    assert ("pkg/b.py::use", "pkg/a.py::helper") in r.call_edges
    assert ("pkg/b.py::use", "pkg/a.py::main") in r.call_edges
    assert ("pkg/b.py", "pkg/a.py") in r.import_edges


def test_self_method_calls(tmp_path):
    r = make(tmp_path, {
        "m.py": "class K:\n    def a(self):\n        return self.b()\n    def b(self):\n        return 1\n",
    })
    assert ("m.py::K.a", "m.py::K.b") in r.call_edges


def test_dynamic_dispatch_is_flagged_not_guessed(tmp_path):
    r = make(tmp_path, {
        "d.py": "def f(o, n):\n    return getattr(o, n)()\n\ndef g():\n    return 1\n",
    })
    flags = {f.id: f.dynamic for f in r.funcs}
    assert flags["d.py::f"] is True
    assert flags["d.py::g"] is False
    assert not r.call_edges  # nothing invented


def test_custom_decorator_flags_dynamic(tmp_path):
    r = make(tmp_path, {
        "x.py": "def deco(fn):\n    return fn\n\n@deco\ndef f():\n    return 1\n\n@staticmethod\ndef s():\n    return 2\n",
    })
    flags = {f.id: f.dynamic for f in r.funcs}
    assert flags["x.py::f"] is True
    assert flags["x.py::s"] is False


def test_test_files_excluded_by_default(tmp_path):
    r = make(tmp_path, {"a.py": "def f(): pass\n", "tests/test_a.py": "def test_f(): pass\n"})
    assert [f.id for f in r.funcs] == ["a.py::f"]


def test_syntax_errors_are_reported_not_fatal(tmp_path):
    r = make(tmp_path, {"ok.py": "def f(): pass\n", "bad.py": "def (:\n"})
    assert len(r.parse_errors) == 1 and len(r.funcs) == 1
