"""Tests for the gate's own scripts. Standard library only.

    python -m unittest discover -s tests -v

They build throwaway repos in a temp folder and run checks.py, enforce.py and
prepare.sh against them, the way the workflow does. gitleaks isn't needed:
the secret scan is pointed at a stand-in.
"""
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(os.path.dirname(HERE), "files", "github")
SCRIPTS = os.path.join(KIT, "ai-review")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


checks = load("checks")


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def write(root, rel, text=""):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class InTempDir(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.dir = tempfile.mkdtemp(prefix="gate-test-")
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.dir, ignore_errors=True)


class IgnoreListTests(unittest.TestCase):
    def test_vercelignore_patterns(self):
        ig = checks.IgnoreList(["/.github", "*.md", "/docs", "*.ps1", "# comment", ""])
        self.assertTrue(ig.matches(".github/workflows/ai-review.yml"))
        self.assertTrue(ig.matches("README.md"))
        self.assertTrue(ig.matches("blog/notes/plan.md"))
        self.assertTrue(ig.matches("docs/how.html"))
        self.assertFalse(ig.matches("blog/docs/page.html"))  # /docs is anchored to the root
        self.assertFalse(ig.matches("index.html"))

    def test_negation_and_double_star(self):
        ig = checks.IgnoreList(["data/**", "!data/public.csv"])
        self.assertTrue(ig.matches("data/leads.csv"))
        self.assertFalse(ig.matches("data/public.csv"))


class ClassifyTests(unittest.TestCase):
    def sev(self, path):
        c = checks.classify(path)
        return c[0] if c else None

    def test_secret_files(self):
        for p in (".env", "config/.env.production", "deploy.pem", "service-account.json",
                  "gcp_service_account.json", "access_token.txt", "token.json", "bank-access.txt",
                  "id_ed25519"):
            self.assertEqual(self.sev(p), "critical", p)

    def test_examples_and_code_are_not_secrets(self):
        for p in (".env.example", "refresh-token.js", "src/tokens.py", "index.html", "app.css",
                  "data-access.py", "public-access.html"):
            self.assertNotEqual(self.sev(p), "critical", p)

    def test_notes_data_and_scripts(self):
        self.assertEqual(self.sev("app.db"), "critical")
        self.assertEqual(self.sev(".github/ai-review/CONTEXT.md"), "high")
        self.assertEqual(self.sev("README.md"), "high")
        self.assertEqual(self.sev("docs/plan.html"), "high")
        self.assertEqual(self.sev("export.csv"), "medium")
        self.assertEqual(self.sev("deploy.ps1"), "medium")
        self.assertEqual(self.sev("backup.zip"), "medium")
        self.assertIsNone(self.sev("img/logo.svg"))


class DetectHostTests(InTempDir):
    def test_hosts(self):
        cases = [
            ({"vercel.json": "{}", "index.html": ""}, "vercel-static"),
            ({"vercel.json": '{"outputDirectory": "site"}'}, "vercel-output"),
            ({".vercelignore": "", "package.json": '{"scripts": {"build": "next build"}}'}, "vercel-build"),
            ({"Procfile": "web: python app.py"}, "railway"),
            ({"requirements.txt": "flask==3.0.3"}, "server"),
            ({"index.html": ""}, "vercel-static"),
            ({"tool.py": ""}, "none"),
        ]
        for files, want in cases:
            with self.subTest(want=want, files=list(files)):
                for name in os.listdir("."):
                    os.remove(name)
                for name, text in files.items():
                    write(".", name, text)
                host, _ = checks.detect_host(list(files), {})
                self.assertEqual(host, want)


class SurfaceTests(InTempDir):
    def run_surface(self, files, cfg=None):
        for rel, text in files.items():
            write(".", rel, text)
        return checks.check_surface(sorted(files), cfg or {})

    def test_static_site_with_vercelignore_is_clean(self):
        found, notes = self.run_surface({
            "index.html": "<h1>hi</h1>", "README.md": "notes", ".vercelignore": "/.github\n*.md\n",
            ".github/ai-review/CONTEXT.md": "weak spots"})
        self.assertEqual(found, [])
        self.assertIn("Host: vercel-static.", notes)

    def test_static_site_without_vercelignore_publishes_notes(self):
        found, _ = self.run_surface({"index.html": "", "README.md": "", ".github/ai-review/CONTEXT.md": ""})
        sevs = sorted(f["severity"] for f in found)
        self.assertEqual(sevs, ["high", "high"])

    def test_publish_allow_list(self):
        found, _ = self.run_surface({"index.html": "", ".vercelignore": "", "data/public.csv": "a,b"},
                                    {"publish": ["data/public.csv"]})
        self.assertEqual(found, [])

    def test_committed_secret_on_a_server_app(self):
        found, _ = self.run_surface({"requirements.txt": "flask==3.0.3", "app.py": "", ".env": "KEY=1"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "high")
        self.assertIn("Secret file committed", found[0]["title"])

    def test_server_that_publishes_its_whole_folder(self):
        found, notes = self.run_surface({"package.json": '{"scripts": {"start": "node server.js"}}',
                                         "server.js": "app.use(express.static(__dirname));",
                                         "NOTES.md": ""})
        self.assertTrue(any("whole repository" in n for n in notes))
        self.assertEqual([f["severity"] for f in found], ["high"])


class EnforceTests(InTempDir):
    def run_enforce(self, checks_result, ai=None, settings=None, extra_env=None):
        os.makedirs(".ai-review-run", exist_ok=True)
        if checks_result is not None:
            with open(".ai-review-run/checks.json", "w", encoding="utf-8") as fh:
                json.dump(checks_result, fh)
        if settings is not None:
            write(".", ".github/ai-review/surface.json", json.dumps(settings))
        summary = os.path.join(self.dir, "summary.md")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "GH_"))}
        env.update({"GITHUB_WORKSPACE": self.dir, "GITHUB_STEP_SUMMARY": summary, "REVIEW_RANGE": "abc..def"})
        if ai is None:
            env["AI_SKIPPED"] = "true"
        else:
            env["AI_SKIPPED"] = "false"
            env["REVIEW_JSON"] = ai if isinstance(ai, str) else json.dumps(ai)
        env.update(extra_env or {})
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "enforce.py")],
                              env=env, capture_output=True, text=True)
        text = ""
        if os.path.exists(summary):
            with open(summary, encoding="utf-8") as fh:
                text = fh.read()
        return proc.returncode, text

    @staticmethod
    def finding(sev):
        return {"source": "surface", "severity": sev, "category": "deploy-surface", "file": "x.md",
                "line": 0, "title": f"a {sev} thing", "detail": "d", "fix": "f", "fingerprint": "fp" + sev}

    def test_clean_run_passes(self):
        code, text = self.run_enforce({"findings": [], "notes": ["Host: none."]})
        self.assertEqual(code, 0)
        self.assertIn("## AI Review: Approved", text)

    def test_high_finding_holds_the_deploy(self):
        code, text = self.run_enforce({"findings": [self.finding("high")], "notes": []})
        self.assertEqual(code, 1)
        self.assertIn("Deploy held", text)

    def test_missing_checks_fail_closed(self):
        code, text = self.run_enforce(None)
        self.assertEqual(code, 1)
        self.assertIn("didn't finish", text)

    def test_ai_block_verdict_and_unreadable_verdict(self):
        code, _ = self.run_enforce({"findings": [], "notes": []},
                                   ai={"verdict": "block", "summary": "no", "findings": []})
        self.assertEqual(code, 1)
        code, text = self.run_enforce({"findings": [], "notes": []}, ai="not json")
        self.assertEqual(code, 1)
        self.assertIn("could not be read", text)

    def test_medium_passes_and_issues_need_a_token(self):
        code, text = self.run_enforce({"findings": [self.finding("medium")], "notes": []})
        self.assertEqual(code, 0)
        self.assertIn("Issues: skipped (no repository token", text)

    def test_issues_can_be_switched_off(self):
        code, text = self.run_enforce({"findings": [self.finding("medium")], "notes": []},
                                      settings={"issues": False},
                                      extra_env={"GITHUB_REPOSITORY": "o/r", "GH_TOKEN": "x"})
        self.assertEqual(code, 0)
        self.assertIn("Issues: off for this repo", text)


class PrepareTests(InTempDir):
    def setUp(self):
        super().setUp()
        # Runner files live beside the repo, not in it, so commits only hold the test's changes.
        self.side = tempfile.mkdtemp(prefix="gate-runner-")
        fake_gh = os.path.join(self.side, "gh")
        with open(fake_gh, "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")  # no run history, as on a repo's first push
        os.chmod(fake_gh, os.stat(fake_gh).st_mode | stat.S_IEXEC)
        self.path = self.side + os.pathsep + os.environ.get("PATH", "")
        git(self.dir, "init", "-q", "-b", "main")
        shutil.copytree(KIT, os.path.join(self.dir, ".github"))
        write(self.dir, ".gitignore", ".ai-review-run/\n")
        write(self.dir, "index.html", "<h1>one</h1>")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "first")

    def tearDown(self):
        shutil.rmtree(self.side, ignore_errors=True)
        super().tearDown()

    def run_prepare(self, scope="last-push", before=""):
        out, summary = os.path.join(self.side, "out"), os.path.join(self.side, "summary")
        open(out, "w").close()
        env = dict(os.environ, PATH=self.path, GITHUB_WORKSPACE=self.dir, GITHUB_OUTPUT=out,
                   GITHUB_STEP_SUMMARY=summary, GITHUB_SHA=git(self.dir, "rev-parse", "HEAD").strip(),
                   GITHUB_REF_NAME="main", GITHUB_REPOSITORY="o/r", REVIEW_SCOPE=scope, PUSH_BEFORE=before)
        subprocess.run(["bash", ".github/ai-review/prepare.sh"], cwd=self.dir, env=env,
                       check=True, capture_output=True, text=True)
        with open(out, encoding="utf-8") as fh:
            pairs = [line.split("=", 1) for line in fh.read().splitlines() if "=" in line]
        return dict(pairs)

    def test_first_commit_reviews_the_whole_repo(self):
        res = self.run_prepare()
        self.assertEqual(res["mode"], "whole")
        self.assertEqual(res["skip"], "false")
        with open(os.path.join(self.dir, ".ai-review-run", "prompt.md"), encoding="utf-8") as fh:
            prompt = fh.read()
        self.assertIn("Review the whole repository", prompt)

    def test_manual_whole_repo_run(self):
        self.assertEqual(self.run_prepare(scope="whole-repo")["mode"], "whole")

    def test_code_change_is_reviewed_as_a_diff(self):
        before = git(self.dir, "rev-parse", "HEAD").strip()
        write(self.dir, "app.js", "console.log(1)")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "code")
        res = self.run_prepare(before=before)
        self.assertEqual((res["mode"], res["skip"], res["base"]), ("diff", "false", before))

    def test_gate_only_and_media_only_pushes_skip_the_ai(self):
        for rel in (".github/ai-review/CONTEXT.md", "img/photo.jpg"):
            with self.subTest(rel=rel):
                before = git(self.dir, "rev-parse", "HEAD").strip()
                write(self.dir, rel, "x" + rel)
                git(self.dir, "add", "-A")
                git(self.dir, "commit", "-q", "-m", rel)
                self.assertEqual(self.run_prepare(before=before)["skip"], "true")


if __name__ == "__main__":
    unittest.main()
