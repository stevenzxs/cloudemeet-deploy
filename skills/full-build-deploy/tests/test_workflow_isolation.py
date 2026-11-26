import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / 'skills/full-build-deploy'
WORKFLOWS = REPO / ".github" / "workflows"


class WorkflowContractTests(unittest.TestCase):
    def test_revision_gate_uses_skill_tools_and_precedes_allocation(self):
        workflow = (WORKFLOWS / "revision-allocation.yml").read_text(encoding="utf-8")
        self.assertIn("skills/full-build-deploy/tools/tls_contract.py", workflow)
        self.assertIn("skills/full-build-deploy/tools/allocate-workflow.py", workflow)
        self.assertIn("steps.origin.outputs.contract", workflow)
        self.assertIn("EXPECTED_ORIGIN_CONTRACT", workflow)
        allocator = (ROOT / "tools/allocate-workflow.py").read_text(encoding="utf-8")
        self.assertIn("origin_contract=", allocator)
        self.assertLess(workflow.index("Normalize user origin"), workflow.index("Allocate or verify inherited parent record"))
        self.assertNotIn("build-tools/", workflow[:workflow.index("Verify revision contract after persistent allocation")])

    def test_package_script_verifies_repository_manifest_from_repository_root(self):
        script = (ROOT / "scripts/package.sh").read_text(encoding="utf-8")
        self.assertRegex(script, r"\(cd\s+\"\$repo/\.\./\.\.\";\s*sha256sum -c skills/full-build-deploy/inputs\.sha256\)")

    def test_build_workflows_verify_the_current_skill_manifest(self):
        for name in ("revision-allocation.yml", "build-package.yml", "publish-release.yml"):
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("sha256sum -c skills/full-build-deploy/inputs.sha256", workflow, name)
        manifest = (ROOT / "inputs.sha256").read_text(encoding="utf-8")
        self.assertIn("skills/full-build-deploy/scripts/package.sh", manifest)
        self.assertIn("skills/full-build-deploy/tools/clients/build-clients.cjs", manifest)
        self.assertIn(".github/workflows/build-package.yml", manifest)

    def test_client_batch_config_is_shared_origin_source_for_build_and_audit(self):
        workflow = (WORKFLOWS / "build-clients.yml").read_text(encoding="utf-8")
        self.assertIn("--env-file", workflow)
        self.assertIn("batch-origin.json", workflow)
        self.assertIn("EXPECTED_ORIGIN", workflow)
        self.assertIn("skills/full-build-deploy/tools/clients/build-clients.cjs", workflow)
        self.assertIn("--origin-contract", workflow)
        self.assertIn("needs.version.outputs.origin_contract", workflow)
        self.assertNotIn("deploy/build-tools/", workflow)

    def test_joint_dispatch_has_correctly_indented_dynamic_origin_descriptions(self):
        workflow = (WORKFLOWS / "build-joint.yml").read_text(encoding="utf-8")
        self.assertIn("        description: Approved TLS mode for this batch's user-supplied origin", workflow)
        self.assertIn("        description: User-supplied HTTP(S) origin for this batch (DNS name or IP)", workflow)

    def test_package_workflow_consumes_allocated_origin_and_skill_closure(self):
        workflow=(WORKFLOWS/'build-package.yml').read_text(encoding='utf-8')
        self.assertIn('needs.version.outputs.origin_contract',workflow)
        self.assertIn('ORIGIN_CONTRACT_JSON',workflow)
        self.assertIn('skills/full-build-deploy/scripts/package.sh assemble',workflow)
        self.assertNotIn('build-tools/',workflow)

    def test_release_workflow_uses_skill_owned_tools(self):
        workflow=(WORKFLOWS/'publish-release.yml').read_text(encoding='utf-8')
        self.assertNotIn('build-tools/',workflow)
        self.assertIn('skills/full-build-deploy/tools/joint-release.py',workflow)

    def test_skill_runtime_files_do_not_reference_shared_build_closure(self):
        roots = (ROOT / "tools", ROOT / "scripts", ROOT / "docker", ROOT / "runtime")
        forbidden = ("build-tools/", "deploy/config/", "repo/'config/", "repo/'patches/",
                     "root/'build-tools/", "root/'patches/", "Path('build-tools/")
        offenders = []
        for base in roots:
            for path in base.rglob("*"):
                if path.is_file() and path.suffix in (".py", ".cjs", ".js", ".sh", ".Dockerfile"):
                    content = path.read_text(encoding="utf-8", errors="replace")
                    for needle in forbidden:
                        if needle in content:
                            offenders.append(f"{path.relative_to(ROOT)}: {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
